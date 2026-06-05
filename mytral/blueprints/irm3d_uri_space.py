# MyTraL: my trailing log
#
# Copyright (C) 2015-2026 Martin Dvorak <martin.dvorak@mindforger.com>
#
# This program is free software: you can redistribute it and/or modify
# it under the terms of the GNU Affero General Public License as published by
# the Free Software Foundation, either version 3 of the License, or
# (at your option) any later version.
#
# This program is distributed in the hope that it will be useful,
# but WITHOUT ANY WARRANTY; without even the implied warranty of
# MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the
# GNU Affero General Public License for more details.
#
# You should have received a copy of the GNU Affero General Public License
# along with this program. If not, see <http://www.gnu.org/licenses/>.
import dataclasses
import datetime

import flask

import mytral
from mytral import app_config
from mytral import app_user_ds as ds
from mytral import athlete_metrics as athlete_metrics_mod
from mytral import charts
from mytral.backends import entities as entities_mod
from mytral.blobstore import activity_service as blob_svc_module
from mytral.metrics import irm3d
from mytral.recordings import parquet_converter as parquet_converter_mod
from mytral.routes import COOKIE_MOBILE
from mytral.routes import COOKIE_USER
from mytral.routes import flask_app


def _blob_service() -> blob_svc_module.ActivityBlobService:
    """Return an ActivityBlobService bound to global blob store."""
    return blob_svc_module.ActivityBlobService(
        store=mytral.app_blobstore,
        dataset=ds,
        config=app_config,
    )


def _activity_date(activity: entities_mod.ActivityEntity) -> datetime.date | None:
    """Resolve valid activity date."""
    try:
        return datetime.date(activity.when_year, activity.when_month, activity.when_day)
    except ValueError:
        return None


def _latest_weight_kg(activities: list[entities_mod.ActivityEntity]) -> float:
    """Return latest non-zero activity weight."""
    for activity in reversed(activities):
        if activity.weight and activity.weight > 0:
            return float(activity.weight)
    return 0.0


def _resolve_power_model_params(
    activities: list[entities_mod.ActivityEntity],
    athlete_metrics,
) -> irm3d.PowerModelParams | None:
    """Resolve CP/W′/Pmax parameters for 3D IRM."""
    cp_watts = float(
        athlete_metrics.e_critical_power
        or athlete_metrics.critical_power
        or athlete_metrics.e_ftp
        or athlete_metrics.ftp
        or 0.0
    )
    if cp_watts <= 0:
        return None

    w_prime_joules = float(
        athlete_metrics.e_w_prime_joules
        or athlete_metrics.w_prime_joules
        or irm3d.DEFAULT_W_PRIME_JOULES
    )
    estimated_pmax = athlete_metrics_mod.estimate_pmax_from_activities(
        activities=activities,
        fallback_cp_watts=cp_watts,
    )
    pmax_watts = float(
        athlete_metrics.e_p_max_watts or athlete_metrics.p_max_watts or estimated_pmax
    )
    pmax_watts = max(
        pmax_watts,
        cp_watts * 1.1,
        irm3d.DEFAULT_MIN_PMAX_WATTS,
    )
    return irm3d.PowerModelParams(
        cp_watts=cp_watts,
        w_prime_joules=w_prime_joules,
        pmax_watts=pmax_watts,
    )


def _load_activity_recording(
    blob_svc: blob_svc_module.ActivityBlobService,
    user_id: str,
    activity: entities_mod.ActivityEntity,
):
    """Load first available parquet recording with power for an activity."""
    for recorded_entry in activity.recorded_blob_keys:
        source_blob_key = entities_mod.recording_blob_uuid(recorded_entry)
        if source_blob_key not in activity.recorded_parquet_keys:
            continue

        result_pair = blob_svc.open_parquet(
            user_id=user_id,
            activity_key=activity.key,
            source_blob_key=source_blob_key,
        )
        if result_pair is None:
            continue
        parquet_stream, _ = result_pair
        parquet_bytes = parquet_stream.read()
        if not parquet_bytes:
            continue
        recording = parquet_converter_mod.load_parquet(parquet_bytes)
        if recording.has_power:
            return recording
    return None


def _compute_workout_rows(
    activities: list[entities_mod.ActivityEntity],
    user_id: str,
    model_params: irm3d.PowerModelParams,
) -> list[irm3d.WorkoutStrainBreakdown]:
    """Compute workout-level strain rows from activity recordings."""
    blob_svc = _blob_service()
    workout_rows: list[irm3d.WorkoutStrainBreakdown] = []

    sorted_activities = sorted(
        activities,
        key=lambda activity: (
            activity.when_year,
            activity.when_month,
            activity.when_day,
            activity.key,
        ),
    )
    for activity in sorted_activities:
        activity_date = _activity_date(activity)
        if activity_date is None:
            continue
        recording = _load_activity_recording(
            blob_svc=blob_svc,
            user_id=user_id,
            activity=activity,
        )
        if recording is None:
            continue

        workout_row = irm3d.compute_workout_strain_from_recording(
            recording_data=recording,
            model_params=model_params,
            activity_key=activity.key,
            activity_date=activity_date,
        )
        if workout_row is not None:
            workout_rows.append(workout_row)
    return workout_rows


@flask_app.route("/insight/irm3d")
def insight_irm3d():
    """Render 3D impulse-response metrics for CP/W′/Pmax."""
    user_id = flask.session.get(COOKIE_USER)
    if not user_id:
        return flask.redirect(flask.url_for("login"))

    user_profile = ds.profile(user_id)
    activities = ds.list_activities(
        user_id=user_id,
        dataset_name=user_profile.dataset_name,
        sort_by_when=True,
        skip_future=True,
    )

    athlete_metrics_mod.resolve(
        athlete_metrics=user_profile.athlete_metrics,
        user_profile=user_profile,
        activities=activities,
        weight_kg=_latest_weight_kg(activities=activities),
    )

    model_params = _resolve_power_model_params(
        activities=activities,
        athlete_metrics=user_profile.athlete_metrics,
    )
    if model_params is None:
        workout_rows = []
        daily_rows = []
        state_rows = []
    else:
        workout_rows = _compute_workout_rows(
            activities=activities,
            user_id=user_id,
            model_params=model_params,
        )
        daily_rows = irm3d.aggregate_daily_strain(workout_rows=workout_rows)
        state_rows = irm3d.run_3d_impulse_response(
            daily_rows=daily_rows,
            irm_params=irm3d.Irm3dParams(),
            model_params=model_params,
        )

    daily_rows_dict = [dataclasses.asdict(row) for row in daily_rows]
    state_rows_dict = [dataclasses.asdict(row) for row in state_rows]
    bokeh_script, bokeh_div = charts.irm3d_composite(
        daily_rows=daily_rows_dict,
        state_rows=state_rows_dict,
        is_mobile_view=bool(flask.session.get(COOKIE_MOBILE)),
    )

    latest_day = daily_rows_dict[-1] if daily_rows_dict else None
    latest_state = state_rows_dict[-1] if state_rows_dict else None
    if latest_state is not None:
        latest_state["w_prime_kj"] = latest_state["w_prime_joules"] / 1000.0

    return flask.render_template(
        "insight-irm3d.html",
        user_profile=user_profile,
        div=bokeh_div,
        script=bokeh_script,
        latest_day=latest_day,
        latest_state=latest_state,
        total_activities=len(activities),
        analyzed_workouts=len(workout_rows),
    )
