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
import datetime
import math

import flask

from mytral import app_logger
from mytral import app_user_ds as ds
from mytral import charts
from mytral import ff
from mytral import settings as user_settings
from mytral import stats
from mytral.backends import entities as entities_mod
from mytral.metrics import banister
from mytral.routes import COOKIE_MOBILE
from mytral.routes import COOKIE_USER
from mytral.routes import flask_app


def _trimp_activity_date(activity: entities_mod.ActivityEntity) -> datetime.date | None:
    """Return activity date if valid."""
    try:
        return datetime.date(activity.when_year, activity.when_month, activity.when_day)
    except ValueError:
        return None


def _resolve_trimp_rest_hr(
    activity: entities_mod.ActivityEntity,
    last_known_rest_hr: float,
    default_rest_hr: float,
) -> float:
    """Resolve resting HR for TRIMP computation."""
    if activity.min_hr and activity.min_hr > 0:
        return float(activity.min_hr)
    if last_known_rest_hr > 0:
        return float(last_known_rest_hr)
    return float(default_rest_hr)


def _resolve_trimp_max_hr(
    activity: entities_mod.ActivityEntity,
    profile_max_hr_fallback: float,
    age_based_max_hr_fallback: float,
) -> float:
    """Resolve max HR for TRIMP computation."""
    if activity.max_hr and activity.max_hr > 0:
        return float(activity.max_hr)
    if profile_max_hr_fallback > 0:
        return float(profile_max_hr_fallback)
    return float(age_based_max_hr_fallback)


def _calc_activity_trimp(
    activity: entities_mod.ActivityEntity,
    hr_rest: float,
    hr_max: float,
    is_man: bool,
) -> float | None:
    """Calculate TRIMP for one activity."""
    if activity.duration_seconds <= 0:
        return None
    if activity.avg_hr <= 0:
        return None
    if hr_max <= hr_rest:
        return None

    duration_min = float(activity.duration_seconds) / 60.0
    hrr = (float(activity.avg_hr) - hr_rest) / (hr_max - hr_rest)
    hrr = max(0.0, min(1.0, hrr))

    if is_man:
        y_factor = 0.65 * math.exp(1.92 * hrr)
    else:
        y_factor = 0.86 * math.exp(1.67 * hrr)

    return duration_min * hrr * y_factor


def _calc_daily_trimp_rows(
    activities: list[entities_mod.ActivityEntity],
    user_profile: user_settings.UserProfile,
    resting_hr_fallback: float,
    profile_max_hr_fallback: float,
) -> list[dict]:
    """Build daily TRIMP rows with ATRIMP/CTRIMP/BTRIMP (legacy symmetric EMA).

    Kept for backward compatibility — the legacy view and existing tests
    depend on this function. When TRIMP_ROCKS is enabled, the route layer
    uses ``get_banister_rows()`` instead.
    """
    if not activities:
        return []

    sorted_activities = sorted(
        activities,
        key=lambda activity: (
            activity.when_year,
            activity.when_month,
            activity.when_day,
            activity.key,
        ),
    )

    daily_trimp: dict[datetime.date, float] = {}
    daily_sessions: dict[datetime.date, int] = {}
    daily_duration_min: dict[datetime.date, float] = {}

    # gender None/undefined falls back to man
    is_man = user_profile.gender is not False
    age_based_max_hr = max(120.0, 190.0 - float(user_profile.age or 0))
    last_known_rest_hr = float(resting_hr_fallback)

    for activity in sorted_activities:
        activity_date = _trimp_activity_date(activity)
        if activity_date is None:
            continue

        hr_rest = _resolve_trimp_rest_hr(
            activity=activity,
            last_known_rest_hr=last_known_rest_hr,
            default_rest_hr=resting_hr_fallback,
        )
        hr_max = _resolve_trimp_max_hr(
            activity=activity,
            profile_max_hr_fallback=profile_max_hr_fallback,
            age_based_max_hr_fallback=age_based_max_hr,
        )

        trimp_value = _calc_activity_trimp(
            activity=activity,
            hr_rest=hr_rest,
            hr_max=hr_max,
            is_man=is_man,
        )
        if trimp_value is None:
            if activity.min_hr and activity.min_hr > 0:
                last_known_rest_hr = float(activity.min_hr)
            continue

        daily_trimp[activity_date] = daily_trimp.get(activity_date, 0.0) + trimp_value
        daily_sessions[activity_date] = daily_sessions.get(activity_date, 0) + 1
        duration_minutes = float(activity.duration_seconds) / 60.0
        daily_duration_min[activity_date] = (
            daily_duration_min.get(activity_date, 0.0) + duration_minutes
        )

        if activity.min_hr and activity.min_hr > 0:
            last_known_rest_hr = float(activity.min_hr)

    if not daily_trimp:
        return []

    first_day = min(daily_trimp.keys())
    last_day = max(daily_trimp.keys())

    daily_rows: list[dict] = []
    current_day = first_day
    previous_atrimp = None
    previous_ctrimp = None

    while current_day <= last_day:
        trimp_value = daily_trimp.get(current_day, 0.0)
        if previous_atrimp is None:
            atrimp = trimp_value
            ctrimp = trimp_value
        else:
            atrimp = previous_atrimp + ((trimp_value - previous_atrimp) / 7.0)
            ctrimp = previous_ctrimp + ((trimp_value - previous_ctrimp) / 42.0)
        btrimp = ctrimp - atrimp

        daily_rows.append(
            {
                "date": current_day,
                "trimp": trimp_value,
                "atrimp": atrimp,
                "ctrimp": ctrimp,
                "btrimp": btrimp,
                "sessions": daily_sessions.get(current_day, 0),
                "duration_min": daily_duration_min.get(current_day, 0.0),
            }
        )

        previous_atrimp = atrimp
        previous_ctrimp = ctrimp
        current_day += datetime.timedelta(days=1)

    return daily_rows


def _build_daily_trimp_map(
    activities: list[entities_mod.ActivityEntity],
    user_profile: user_settings.UserProfile,
    resting_hr_fallback: float,
    profile_max_hr_fallback: float,
) -> dict[datetime.date, float]:
    """Build a date→daily TRIMP sum map from activities.

    Used by ``get_banister_rows()`` to feed the Banister model.
    """
    daily_trimp: dict[datetime.date, float] = {}
    is_man = user_profile.gender is not False
    age_based_max_hr = max(120.0, 190.0 - float(user_profile.age or 0))
    last_known_rest_hr = float(resting_hr_fallback)

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
        activity_date = _trimp_activity_date(activity)
        if activity_date is None:
            continue

        hr_rest = _resolve_trimp_rest_hr(
            activity=activity,
            last_known_rest_hr=last_known_rest_hr,
            default_rest_hr=resting_hr_fallback,
        )
        hr_max = _resolve_trimp_max_hr(
            activity=activity,
            profile_max_hr_fallback=profile_max_hr_fallback,
            age_based_max_hr_fallback=age_based_max_hr,
        )

        trimp_value = _calc_activity_trimp(
            activity=activity,
            hr_rest=hr_rest,
            hr_max=hr_max,
            is_man=is_man,
        )
        if trimp_value is None:
            if activity.min_hr and activity.min_hr > 0:
                last_known_rest_hr = float(activity.min_hr)
            continue

        daily_trimp[activity_date] = daily_trimp.get(activity_date, 0.0) + trimp_value

        if activity.min_hr and activity.min_hr > 0:
            last_known_rest_hr = float(activity.min_hr)

    return daily_trimp


def _daily_trimp_map_to_sorted_pairs(
    daily_trimp: dict[datetime.date, float],
) -> list[tuple[datetime.date, float]]:
    """Convert a date→TRIMP map to a gap-filled sorted list of (date, trimp) pairs."""
    if not daily_trimp:
        return []

    first_day = min(daily_trimp.keys())
    last_day = max(daily_trimp.keys())
    pairs: list[tuple[datetime.date, float]] = []
    current_day = first_day
    while current_day <= last_day:
        pairs.append((current_day, daily_trimp.get(current_day, 0.0)))
        current_day += datetime.timedelta(days=1)
    return pairs


def get_banister_rows(user_id: str) -> list[banister.BanisterRow]:
    """Get cached Banister rows for a user, computing on cache miss.

    Parameters
    ----------
    user_id : str
        User ID.

    Returns
    -------
    list[BanisterRow]
        Banister model rows.
    """
    user_cache = ds.cache.user(user_id)
    cached = user_cache.banister_rows()
    if cached is not None:
        return cached

    user_profile = ds.profile(user_id)
    activities = ds.list_activities(
        user_id=user_id,
        dataset_name=user_profile.dataset_name,
        sort_by_when=True,
        skip_future=True,
    )
    profile_stats = stats.UserProfileStats.from_entity(
        user_profile=user_profile,
        activities=activities,
        logger=app_logger,
    )

    daily_trimp_map = _build_daily_trimp_map(
        activities=activities,
        user_profile=user_profile,
        resting_hr_fallback=float(profile_stats.resting_hr or 60.0),
        profile_max_hr_fallback=float(user_profile.athlete_metrics.e_max_hr or 0.0),
    )
    pairs = _daily_trimp_map_to_sorted_pairs(daily_trimp_map)
    rows = banister.run(pairs)
    user_cache.set_banister_rows(rows)
    return rows


@flask_app.route("/insight/trimp")
def insight_trimp():
    """Render TRIMP composite insight chart."""
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
    profile_stats = stats.UserProfileStats.from_entity(
        user_profile=user_profile,
        activities=activities,
        logger=app_logger,
    )

    is_mobile = bool(flask.session.get(COOKIE_MOBILE))

    if ff.can("TRIMP_ROCKS"):
        banister_rows = get_banister_rows(user_id)
        banister_params = banister.BanisterParams()
        projection = banister.project(banister_rows, days=56, params=banister_params)
        annotations = banister.annotate(banister_rows)
        insights = banister.compute_insights(
            rows=banister_rows,
            projection=projection,
            annotations=annotations,
        )

        bokeh_script, bokeh_div = charts.trimp_composite(
            daily_rows=banister_rows,
            is_mobile_view=is_mobile,
            params=banister_params,
            projection=projection,
            annotations=annotations,
        )

        trend_script, trend_div = charts.trimp_banister_trend(
            banister_rows=banister_rows,
            is_mobile_view=is_mobile,
            annotations=annotations,
        )

        boxplot_script, boxplot_div = charts.trimp_banister_boxplots(
            banister_rows=banister_rows,
            is_mobile_view=is_mobile,
        )

        latest_row = banister_rows[-1] if banister_rows else None

        return flask.render_template(
            "insight-trimp.html",
            user_profile=user_profile,
            div=bokeh_div,
            script=bokeh_script,
            trend_div=trend_div,
            trend_script=trend_script,
            boxplot_div=boxplot_div,
            boxplot_script=boxplot_script,
            latest_row=latest_row,
            banister_rows=banister_rows,
            projection=projection,
            annotations=annotations,
            insights=insights,
            ff=ff,
        )

    # legacy path (TRIMP_ROCKS off)
    daily_rows = _calc_daily_trimp_rows(
        activities=activities,
        user_profile=user_profile,
        resting_hr_fallback=float(profile_stats.resting_hr or 60.0),
        profile_max_hr_fallback=float(user_profile.athlete_metrics.e_max_hr or 0.0),
    )

    bokeh_script, bokeh_div = charts.trimp_composite(
        daily_rows=daily_rows,
        is_mobile_view=is_mobile,
    )

    latest_row = daily_rows[-1] if daily_rows else None

    return flask.render_template(
        "insight-trimp.html",
        user_profile=user_profile,
        div=bokeh_div,
        script=bokeh_script,
        latest_row=latest_row,
        ff=ff,
    )


@flask_app.route("/app/activities/<key>/analysis-trimp")
def activity_trimp_analysis(key: str):
    """Render per-activity TRIMP-based (Banister) analysis page."""
    user_id = flask.session.get(COOKIE_USER)
    if not user_id:
        return flask.redirect(flask.url_for("login"))

    user_profile = ds.profile(user_id)

    activity = ds.get_activity(
        user_id=user_id, dataset_name=user_profile.dataset_name, key=key
    )
    if activity is None:
        flask.flash("Activity not found.", "error")
        return flask.redirect(flask.url_for("list_activities_year", year=0))

    banister_rows = get_banister_rows(user_id)
    banister_params = banister.BanisterParams()
    projection = banister.project(banister_rows, days=56, params=banister_params)

    impact = banister.analyze_activity(
        activity=activity,
        rows=banister_rows,
        projection=projection,
    )

    # slice rows around the activity date for the mini-chart
    activity_date = datetime.date(
        activity.when_year, activity.when_month, activity.when_day
    )
    window_start = activity_date - datetime.timedelta(days=14)
    window_end = activity_date + datetime.timedelta(days=14)
    window_rows = [r for r in banister_rows if window_start <= r.date <= window_end]

    is_mobile = bool(flask.session.get(COOKIE_MOBILE))
    bokeh_script, bokeh_div = charts.trimp_composite(
        daily_rows=window_rows,
        is_mobile_view=is_mobile,
        params=banister_params,
        highlight_date=activity_date,
    )

    # average daily TRIMP across all training days with TRIMP > 0
    active_days = [r for r in banister_rows if r.trimp > 0]
    avg_daily_trimp = (
        sum(r.trimp for r in active_days) / len(active_days) if active_days else 0.0
    )
    vs_avg = (
        impact.post_row.trimp / avg_daily_trimp
        if impact.post_row and avg_daily_trimp > 0
        else None
    )

    activity_types = ds.list_activity_types(user_id=user_id)

    return flask.render_template(
        "activity-analysis-trimp.html",
        user_profile=user_profile,
        activity_entity=activity,
        activity_types=activity_types,
        div=bokeh_div,
        script=bokeh_script,
        banister_rows=banister_rows,
        window_rows=window_rows,
        projection=projection,
        impact=impact,
        avg_daily_trimp=avg_daily_trimp,
        vs_avg=vs_avg,
        ff=ff,
    )
