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
import hashlib
import uuid

import flask

import mytral
from mytral import app_config
from mytral import app_logger
from mytral import app_user_ds as ds
from mytral import athlete_metrics as athlete_metrics_mod
from mytral import charts
from mytral.backends import entities as entities_mod
from mytral.blobstore import activity_service as blob_svc_module
from mytral.metrics import irm3d
from mytral.metrics import irm3d_cache
from mytral.recordings import parquet_converter as parquet_converter_mod
from mytral.routes import COOKIE_MOBILE
from mytral.routes import COOKIE_USER
from mytral.routes import flask_app
from mytral.tasks import _entities as task_entities_mod
from mytral.tasks.do import irm3d_cache_warmup as cache_warmup_task  # noqa: F401


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


def _recording_fingerprint(activity: entities_mod.ActivityEntity) -> str:
    """Compute a stable fingerprint of the activity's power recordings.

    Uses the sorted parquet keys so that any change to the set of
    recordings (addition, removal, or replacement) produces a different
    fingerprint and invalidates the cached strain breakdown.

    Parameters
    ----------
    activity : ActivityEntity
        The activity whose recording state should be fingerprinted.

    Returns
    -------
    str
        Hex-encoded SHA-256 hash, or empty string if the activity has
        no parquet recordings.
    """
    keys = sorted(activity.recorded_parquet_keys.values())
    if not keys:
        return ""
    payload = "|".join(keys)
    return hashlib.sha256(payload.encode("utf-8")).hexdigest()


def _has_running_warmup_task(user_id: str) -> bool:
    """Check if a warmup task is already queued/running for the given user."""
    try:
        all_tasks = mytral.app_task_manager.executor.get_all_tasks(user_id)
        for task in all_tasks:
            if task.task_type == "irm3d_cache_warmup" and task.status in (
                task_entities_mod.TaskStatus.QUEUED,
                task_entities_mod.TaskStatus.RUNNING,
            ):
                return True
    except Exception:
        pass
    return False


def _submit_cache_warmup_task(
    user_id: str,
    model_params: irm3d.PowerModelParams,
) -> str | None:
    """Submit a background task to warm the IRM3D cache.

    Returns the task ID if submitted, None if a task is already running
    or submission fails.
    """
    if _has_running_warmup_task(user_id):
        app_logger.info("IRM3D cache warmup: task already running, skipping submit")
        return None

    try:
        task_entity = task_entities_mod.TaskEntity(
            key=str(uuid.uuid4()),
            user_id=user_id,
            task_type="irm3d_cache_warmup",
            status=task_entities_mod.TaskStatus.QUEUED,
            created_at=datetime.datetime.now(),
            started_at=None,
            completed_at=None,
            error_message=None,
            error_type=None,
            error_traceback=None,
            progress=0,
            parameters={
                "user_id": user_id,
                "cp_watts": model_params.cp_watts,
                "w_prime_joules": model_params.w_prime_joules,
                "pmax_watts": model_params.pmax_watts,
            },
            is_cancelled=False,
            result_route="insight_irm3d",
            result_route_kwargs={},
        )
        task_id = mytral.app_task_manager.executor.submit(task_entity)
        app_logger.info(
            f"IRM3D cache warmup: submitted task {task_id} "
            f"(CP={model_params.cp_watts:.0f} W "
            f"W\u2032={model_params.w_prime_joules:.0f} J "
            f"Pmax={model_params.pmax_watts:.0f} W)"
        )
        return task_id
    except Exception as exc:
        app_logger.error(f"IRM3D cache warmup: failed to submit task: {exc}")
        return None


def _workout_strain_from_cache_entry(
    cached_entry: dict,
) -> irm3d.WorkoutStrainBreakdown:
    """Deserialize a cached entry into a WorkoutStrainBreakdown.

    The entry is either a flat dict (legacy, pre-fingerprint cache) or
    a ``{"recording_fingerprint": "...", "data": {...}}`` wrapper.
    """
    # accept both legacy flat entries and new wrapped entries
    strain_dict = cached_entry.get("data", cached_entry)
    return irm3d.WorkoutStrainBreakdown(
        activity_key=strain_dict["activity_key"],
        date=strain_dict["date"],
        ss_total=strain_dict["ss_total"],
        ss_cp=strain_dict["ss_cp"],
        ss_w_prime=strain_dict["ss_w_prime"],
        ss_pmax=strain_dict["ss_pmax"],
        min_mpa_watts=strain_dict["min_mpa_watts"],
        max_power_watts=strain_dict["max_power_watts"],
        near_limit_seconds=strain_dict["near_limit_seconds"],
        samples=strain_dict["samples"],
    )


def _compute_workout_rows_with_cache(
    activities: list[entities_mod.ActivityEntity],
    user_id: str,
    model_params: irm3d.PowerModelParams,
    user_data_dir: str,
) -> list[irm3d.WorkoutStrainBreakdown]:
    """Compute workout-level strain rows with file-based caching.

    Only recomputes strain for activities that are not present in the
    cache or whose model_params hash has changed. Cached results are
    reused for unchanged activities.
    """
    params_hash = irm3d_cache.compute_model_params_hash(model_params)
    file_cache = irm3d_cache.Irm3dFileCache(user_data_dir)

    cached_data = file_cache.load()
    cached_hash = cached_data.get("model_params_hash", "") if cached_data else ""
    cached_strains: dict[str, dict] = (
        cached_data.get("workout_strains", {}) if cached_data else {}
    )

    # if model params changed, invalidate entire cache
    if cached_hash != params_hash:
        if cached_hash:
            app_logger.info(
                f"IRM3D cache: model params changed ({cached_hash[:8]}... → "
                f"{params_hash[:8]}...), invalidating cache"
            )
        else:
            app_logger.info("IRM3D cache: no existing cache, computing from scratch")
        cached_strains = {}

    blob_svc = _blob_service()
    workout_rows: list[irm3d.WorkoutStrainBreakdown] = []
    cache_hits = 0
    cache_misses = 0

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

        # try cache first — verify recording fingerprint matches
        cached_entry = cached_strains.get(activity.key)
        if cached_entry is not None:
            fingerprint = _recording_fingerprint(activity)
            if fingerprint and fingerprint == cached_entry.get(
                "recording_fingerprint", ""
            ):
                workout_rows.append(_workout_strain_from_cache_entry(cached_entry))
                cache_hits += 1
                continue
            # fingerprint mismatch or missing — fall through to recompute

        # cache miss — compute from recording
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
            fingerprint = _recording_fingerprint(activity)
            cached_strains[activity.key] = {
                "recording_fingerprint": fingerprint,
                "data": dataclasses.asdict(workout_row),
            }
            cache_misses += 1

    # persist updated cache (only write if there were changes)
    if cache_misses > 0 or cached_hash != params_hash:
        file_cache.save(
            {
                "model_params_hash": params_hash,
                "workout_strains": cached_strains,
            }
        )
        app_logger.info(
            f"IRM3D cache saved: {cache_hits} hits, {cache_misses} misses, "
            f"{len(workout_rows)} total workouts"
        )
    else:
        app_logger.info(
            f"IRM3D cache: {cache_hits} hits, 0 misses — no recomputation needed"
        )

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
        cache_warming = False
        warmup_task_id = None
    else:
        user_data_dir = str(ds.user_dir(user_id))
        params_hash = irm3d_cache.compute_model_params_hash(model_params)
        file_cache = irm3d_cache.Irm3dFileCache(user_data_dir)
        cached_data = file_cache.load()
        cached_hash = cached_data.get("model_params_hash", "") if cached_data else ""

        cache_valid = cached_data is not None and cached_hash == params_hash

        if cache_valid:
            # cache hit — fast path
            cache_warming = False
            warmup_task_id = None
            workout_rows = _compute_workout_rows_with_cache(
                activities=activities,
                user_id=user_id,
                model_params=model_params,
                user_data_dir=user_data_dir,
            )
            daily_rows = irm3d.aggregate_daily_strain(workout_rows=workout_rows)
            state_rows = irm3d.run_3d_impulse_response(
                daily_rows=daily_rows,
                irm_params=irm3d.Irm3dParams(),
                model_params=model_params,
            )
        else:
            # cold cache — submit background task, render with placeholder
            cache_warming = True
            warmup_task_id = _submit_cache_warmup_task(
                user_id=user_id,
                model_params=model_params,
            )
            workout_rows = []
            daily_rows = []
            state_rows = []

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
        cache_warming=cache_warming,
        warmup_task_id=warmup_task_id,
    )
