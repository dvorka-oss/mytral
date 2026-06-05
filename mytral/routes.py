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
import calendar
import copy
import dataclasses
import datetime
import functools
import json
import traceback
import uuid

import bleach
import flask
import flask_cors
import markdown
import markupsafe
import structlog
from bokeh.embed import components as bokeh_components

import mytral
from mytral import app_config
from mytral import app_ds
from mytral import app_logger
from mytral import app_task_manager
from mytral import app_user_ds as ds
from mytral import athlete_metrics as am_module
from mytral import blobstore as blob_pkg
from mytral import cals
from mytral import charts
from mytral import commons
from mytral import ff
from mytral import forms
from mytral import insights
from mytral import ninjas
from mytral import notifications as notif_mod
from mytral import onboarding
from mytral import settings as user_settings
from mytral import stats
from mytral import utils
from mytral import version
from mytral import views
from mytral.backends import entities as entities_mod
from mytral.blobstore import activity_service as blob_svc_module
from mytral.middleware import sync_guard as sync_guard_module
from mytral.recordings import gpx_extractor
from mytral.tasks import _entities as task_entities
from mytral.tasks import do

#
# constants
#

COOKIE_USER = "mytral_user"
COOKIE_TOKEN = "mytral_token"
# cookie which indicates that the user is using mobile device,
# the resolution is detected on login and stored in session the cookie,
# empty value means that the user is not using mobile device
COOKIE_MOBILE = "mytral_mobile"
# aspects
ASPECT_LIST = "list"
ASPECT_WEIGHT = "weight"
ASPECT_INSIGHTS = "insights"

#
# tasks
#


# ensure that Python runtime loads all tasks
def __discover_tasks():
    import importlib
    import pkgutil

    for loader, module_name, is_pkg in pkgutil.walk_packages(
        do.__path__, do.__name__ + "."
    ):
        importlib.import_module(module_name)


__discover_tasks()


#
# application
#


def _blob_service() -> blob_svc_module.ActivityBlobService:
    """Return an ActivityBlobService bound to the global store and dataset."""
    return blob_svc_module.ActivityBlobService(
        store=mytral.app_blobstore,
        dataset=ds,
        config=app_config,
    )


def _bbox_from_points(points: list[tuple[float, float]]) -> list[float]:
    """Compute map bounds from ordered GPS points."""
    latitudes = [point[0] for point in points]
    longitudes = [point[1] for point in points]
    return [
        min(latitudes),
        min(longitudes),
        max(latitudes),
        max(longitudes),
    ]


def _activity_map_data(
    user_id: str,
    activity: entities_mod.ActivityEntity,
    blob_svc: blob_svc_module.ActivityBlobService,
    *,
    include_detail: bool,
) -> dict | None:
    """Return first GPX map payload for an activity."""
    if not activity.recorded_blob_keys:
        return None

    for entry in activity.recorded_blob_keys:
        ext = entities_mod.recording_ext(entry)
        if ext not in (".gpx", ".tcx"):
            continue

        blob_uuid = entities_mod.recording_blob_uuid(entry)
        try:
            meta = blob_svc.ensure_gpx_map_data(
                user_id=user_id,
                activity_key=activity.key,
                blob_key=blob_uuid,
            )
        except (blob_pkg.BlobStoreError, blob_pkg.BlobValidationError):
            app_logger.warning(
                "Failed to resolve GPX map payload",
                user_id=user_id,
                activity_key=activity.key,
                blob_key=blob_uuid,
                traceback=traceback.format_exc(),
            )
            return None

        if not meta.summary_polyline:
            return None

        bbox = list(meta.summary_bbox) if meta.summary_bbox is not None else None
        detail_points: list[tuple[float, float]] | None = None
        profile_points: list[tuple[float, float]] = list(meta.elevation_profile or [])
        if include_detail:
            if meta.full_polyline:
                try:
                    detail_points = gpx_extractor.decode_polyline(meta.full_polyline)
                except (RuntimeError, ValueError):
                    app_logger.warning(
                        "Failed to decode GPX detail polyline",
                        user_id=user_id,
                        activity_key=activity.key,
                        blob_key=blob_uuid,
                        traceback=traceback.format_exc(),
                    )
                    return None
            else:
                try:
                    detail_points = gpx_extractor.decode_polyline(meta.summary_polyline)
                except (RuntimeError, ValueError):
                    return None

            if bbox is None:
                bbox = _bbox_from_points(points=detail_points)

        if bbox is None:
            try:
                summary_points = gpx_extractor.decode_polyline(meta.summary_polyline)
            except (RuntimeError, ValueError):
                return None
            if not summary_points:
                return None
            bbox = _bbox_from_points(points=summary_points)

        payload = {
            "blob_uuid": blob_uuid,
            "summary_polyline": meta.summary_polyline,
            "full_polyline": meta.full_polyline,
            "summary_bbox": bbox,
            "track_point_count": meta.track_point_count,
            "profile_points": profile_points,
        }
        if include_detail:
            payload["detail_points"] = detail_points or []
        return payload

    return None


# allowed HTML elements for the Markdown Jinja2 filter
_MD_ALLOWED_TAGS = [
    "p",
    "br",
    "strong",
    "em",
    "u",
    "s",
    "h1",
    "h2",
    "h3",
    "h4",
    "h5",
    "h6",
    "ul",
    "ol",
    "li",
    "blockquote",
    "code",
    "pre",
    "hr",
    "table",
    "thead",
    "tbody",
    "tr",
    "th",
    "td",
    "a",
    "img",
]
_MD_ALLOWED_ATTRIBUTES: dict = {
    "a": ["href", "title"],
    "img": ["src", "alt", "title"],
    "th": ["align"],
    "td": ["align"],
}
_MD_ALLOWED_PROTOCOLS = ["http", "https", "mailto"]

flask_app = flask.Flask(__name__.split(".")[0])
flask_cors.CORS(flask_app, origins=app_config.cors_origins)
# Flask secret key: https://flask.palletsprojects.com/en/stable/config/#SECRET_KEY
flask_app.config["SECRET_KEY"] = app_config.signing_key

# register task manager on Flask app and start the timeout watchdog
app_task_manager.init_app(flask_app, task_timeout_s=app_config.task_timeout)

# make application RD_ONLY if activities sync is in progress
sync_guard_module.register_sync_guard(flask_app)
sync_guard_module.inject_sync_status(flask_app)

#
# Flask app decorators
#


# custom Jinja2 filters
@flask_app.template_filter("zfill")
def zfill_filter(value, width=2):
    """Zero-fill a number to specified width."""
    return str(value).zfill(width)


@flask_app.template_filter("ellipsis")
def ellipsis_filter(value, threshold=35):
    """Truncate text in the middle with ellipsis.

    Parameters
    ----------
    value : str
        The text to truncate.
    threshold : int
        Length threshold above which truncation is applied (default: 35).

    Returns
    -------
    str
        Original text if shorter than threshold, otherwise truncated with
        ellipsis in the middle.
    """
    text = str(value)
    if len(text) <= threshold:
        return text
    half_len = (threshold - 3) // 2
    return f"{text[:half_len]}...{text[-half_len:]}"


# logging decorators
@flask_app.before_request
def _bind_request_context() -> None:
    """Bind per-request structured-log fields into the contextvars store.

    Fields bound here appear automatically on every log event emitted during
    the lifetime of the request, regardless of which module emits them.
    """
    structlog.contextvars.clear_contextvars()
    structlog.contextvars.bind_contextvars(
        request_id=str(uuid.uuid4()),
        method=flask.request.method,
        path=flask.request.path,
        remote_addr=flask.request.remote_addr,
        user_id=flask.session.get(COOKIE_USER, ""),
    )


@flask_app.after_request
def _log_response(response: flask.Response) -> flask.Response:
    """Emit a single structured access-log line per request via structlog.

    Replaces werkzeug's stdlib access log (which is suppressed in run.py) so
    that every request produces exactly one ``"request"`` event in the same
    structured log stream as the application logs.  The event carries the same
    per-request context fields bound by ``_bind_request_context`` plus the
    HTTP response status code.
    """
    app_logger.info("request", status=response.status_code)
    return response


@flask_app.teardown_request
def _clear_request_context(exc: BaseException | None) -> None:
    """Remove all per-request context vars after the request finishes."""
    structlog.contextvars.clear_contextvars()


@flask_app.template_filter("tag_to_color")
def tag_to_color_filter(tag):
    """Generate consistent color for a tag."""
    return utils.tag_to_color(tag)


@functools.lru_cache(maxsize=512)
def _render_markdown(text: str) -> markupsafe.Markup:
    """Render and sanitise Markdown to HTML; result is cached by input string."""
    html = markdown.markdown(text, extensions=["nl2br", "tables"])
    clean = bleach.clean(
        html,
        tags=_MD_ALLOWED_TAGS,
        attributes=_MD_ALLOWED_ATTRIBUTES,
        protocols=_MD_ALLOWED_PROTOCOLS,
        strip=True,
    )
    return markupsafe.Markup(clean)


@flask_app.template_filter("markdown")
def markdown_filter(text):
    """Convert Markdown text to sanitised HTML.

    Parameters
    ----------
    text : str | None
        Raw Markdown input from user.

    Returns
    -------
    markupsafe.Markup
        Sanitised HTML safe for direct rendering.
    """
    if not text:
        return markupsafe.Markup("")
    return _render_markdown(text)


#
# Context processors
#


@flask_app.context_processor
def inject_version():
    """inject app_version into all templates."""
    return dict(app_version=version.__version__)


@flask_app.context_processor
def inject_task_info():
    """Inject running task count into all templates."""
    user_id = flask.session.get(COOKIE_USER)
    if user_id:
        # get running tasks from executor (in-memory) not storage (files)
        all_tasks = app_task_manager.executor.get_all_tasks(user_id)
        running_tasks = [
            t for t in all_tasks if t.status == task_entities.TaskStatus.RUNNING
        ]
        return {"running_tasks_count": len(running_tasks)}
    return {"running_tasks_count": 0}


@flask_app.context_processor
def inject_notifications():
    """Inject notifications into all templates.

    Reads both persistent notifications from storage and flash messages
    from the session, combining them into one list. Flash messages are
    also persisted to storage so they survive across requests.
    """
    user_id = flask.session.get(COOKIE_USER)
    if user_id:
        notif_storage = notif_mod.store
        notif_list = notif_storage.list(user_id)

        # consume flash messages and store them
        flash_messages = flask.get_flashed_messages(with_categories=True)
        for category, message in flash_messages:
            notif_storage.add(
                user_id=user_id,
                category=category,
                message=message,
            )

        # refresh list after storing flash messages
        if flash_messages:
            notif_list = notif_storage.list(user_id)

        # compute badge color: green=info only, red=errors only, orange=mixed
        error_count = sum(1 for n in notif_list if n.category in ("error",))
        if notif_list and error_count == len(notif_list):
            badge_color = "red"
        elif notif_list and error_count == 0:
            badge_color = "green"
        elif notif_list:
            badge_color = "orange"
        else:
            badge_color = "green"

        return {
            "notification_count": len(notif_list),
            "notifications": notif_list,
            "notification_badge_color": badge_color,
            "clear_notifications_form": forms.ClearNotificationsForm(),
        }
    return {
        "notification_count": 0,
        "notifications": [],
        "notification_badge_color": "green",
        "clear_notifications_form": forms.ClearNotificationsForm(),
    }


@flask_app.context_processor
def inject_feature_flags():
    """Inject feature flags into all templates."""
    return dict(ff=ff)


@flask_app.context_processor
def inject_today():
    """Inject today's date into all templates."""
    return dict(today=datetime.date.today())


def _parse_positive_int_param(value: str) -> int:
    """Parse a URL integer parameter, aborting with 400 on invalid input.

    Parameters
    ----------
    value : str
        Raw string value from the URL path.

    Returns
    -------
    int
        Parsed integer, guaranteed to be >= 1.

    """
    result = 0
    try:
        result = int(value)
    except (ValueError, TypeError):
        flask.abort(400)
    if result < 1:
        flask.abort(400)
    return result


def _sanitize_download_name(name: str) -> str:
    """Strip characters that enable HTTP response splitting from a filename.

    Removes CR (\\r), LF (\\n), and NUL (\\x00) to prevent header injection, and
    strips path separators so the browser sees only a plain filename.

    Parameters
    ----------
    name : str
        Candidate download filename, typically from user-supplied metadata.

    Returns
    -------
    str
        Sanitized filename safe to use as ``Content-Disposition`` attachment name.
    """
    # remove header-injection characters and path components
    safe = name.translate(str.maketrans("", "", "\r\n\x00/\\"))
    return safe or "download"


#
# URI space
#


@flask_app.route("/home")
@flask_app.route("/")
def home():
    user_id = flask.session.get(COOKIE_USER)
    if not user_id:
        return flask.redirect(flask.url_for("login"))
    user_profile = ds.profile(user_id)

    ds_stats = ds.activities_stats(
        user_id=user_id,
        dataset_name=user_profile.dataset_name,
        include_meta=True,
    )

    activity_types = ds.list_activity_types(user_id=user_id)
    is_mobile = bool(flask.session.get(COOKIE_MOBILE))

    if len(ds_stats.years) > 1:
        bokeh_script, bokeh_div = charts.fig_grid_2_html(
            charts.total_km_per_year(
                ds_stats=ds_stats,
                activity_types=activity_types,
                is_mobile_view=is_mobile,
            )
        )
    elif len(ds_stats.years) == 1:
        cal_heatmap = ds.activity_type_heatmap(
            user_id=user_id, dataset_name=user_profile.dataset_name
        )
        year = ds_stats.year_max
        x = list(range(1, 54))
        y = [
            int(cal_heatmap.week_stats[year].get(w, {}).get("meters", 0) / 1000.0)
            for w in x
        ]
        bokeh_script, bokeh_div = charts.year_kms_per_week(
            x=x, y=y, is_mobile_view=is_mobile
        )
    else:
        bokeh_script, bokeh_div = charts.fig_grid_2_html(
            charts.total_km_per_year(
                ds_stats=ds_stats,
                activity_types=activity_types,
                is_mobile_view=is_mobile,
            )
        )

    # calculate all-time statistics for the dashboard
    all_activities = list(
        ds.all_activities(
            user_id=user_id,
            dataset_name=user_profile.dataset_name,
        ).values()
    )

    bokeh_month_cmp_script, bokeh_month_cmp_div = charts.last_vs_this_month(
        aspect=commons.StatsAspect.DURATION,
        user_id=user_id,
        ds=ds,
        is_mobile_view=is_mobile,
    )

    bokeh_week_cmp_script, bokeh_week_cmp_div = charts.last_vs_this_week_homepage(
        aspect=commons.StatsAspect.DURATION,
        activities=all_activities,
        activity_types=activity_types,
        is_mobile_view=is_mobile,
    )

    # radar plot for 3 years
    radar_script, radar_div = charts.radar_plot(
        user_id=user_id,
        ds=ds,
        is_mobile_view=is_mobile,
    )

    # find fastest activity (best pace)
    dashboard_fastest_activity = None
    dashboard_fastest_pace = float("inf")
    for a in all_activities:
        if a.distance > 0 and a.duration_seconds > 0:
            pace = a.duration_seconds / (a.distance / 1000)  # seconds per km
            if pace < dashboard_fastest_pace:
                dashboard_fastest_pace = pace
                dashboard_fastest_activity = a

    # find longest activity by distance
    dashboard_longest_activity = (
        max(all_activities, key=lambda x: x.distance, default=None)
        if all_activities
        else None
    )

    # find most intense activity (by heart rate or watts)
    dashboard_most_intense_activity = None
    dashboard_highest_intensity = 0
    for a in all_activities:
        # normalize watts
        intensity_score = max(a.avg_hr or 0.0, (a.avg_watts or 0.0) / 10.0)
        if intensity_score > dashboard_highest_intensity:
            dashboard_highest_intensity = intensity_score
            dashboard_most_intense_activity = a

    # find activity with most elevation gain
    dashboard_highest_elevation_activity = (
        max(all_activities, key=lambda x: x.elevation_gain, default=None)
        if all_activities
        else None
    )

    # onboarding
    onboarding_active = onboarding.is_onboarding_active(user_profile)
    onboarding_state = None
    checklist_items = []

    if onboarding_active:
        # auto-check progress
        onboarding_state = onboarding.auto_check_progress(user_id, user_profile)
        user_profile.onboarding_state = onboarding_state
        ds.update_profile(user_profile)

        # get display items
        checklist_items = onboarding.get_checklist_display_items(onboarding_state)

    # chart - always render dashboard
    return flask.render_template(
        "home.html",
        user_profile=user_profile,
        stats=ds_stats,
        div=bokeh_div,
        script=bokeh_script,
        month_cmp_div=bokeh_month_cmp_div,
        month_cmp_script=bokeh_month_cmp_script,
        week_cmp_div=bokeh_week_cmp_div,
        week_cmp_script=bokeh_week_cmp_script,
        radar_div=radar_div,
        radar_script=radar_script,
        is_mobile=is_mobile,
        activity_types=activity_types,
        # dashboard statistics
        dashboard_fastest_activity=dashboard_fastest_activity,
        dashboard_longest_activity=dashboard_longest_activity,
        dashboard_most_intense_activity=dashboard_most_intense_activity,
        dashboard_highest_elevation_activity=dashboard_highest_elevation_activity,
        # onboarding
        onboarding_active=onboarding_active,
        onboarding_state=onboarding_state,
        checklist_items=checklist_items,
    )


@flask_app.route("/vs/this/last")
def this_vs_last():
    user_id = flask.session.get(COOKIE_USER)
    if not user_id:
        return flask.redirect(flask.url_for("login"))
    user_profile = ds.profile(user_id)

    # stats for the last year
    year = ds.activities_stats(
        user_id=user_id, dataset_name=user_profile.dataset_name
    ).year_max

    if not year:
        return flask.redirect(flask.url_for("home"))

    aspect_arg = flask.request.args.get("aspect")
    if aspect_arg is None:
        aspect = commons.StatsAspect.DISTANCE
    else:
        try:
            aspect = commons.StatsAspect[aspect_arg.upper()]
        except KeyError:
            flask.abort(400)

    period_arg = flask.request.args.get("period")
    if period_arg is None:
        period = commons.StatsPeriod.WEEK
    else:
        try:
            period = commons.StatsPeriod[period_arg.upper()]
        except KeyError:
            flask.abort(400)

    # chart
    if commons.StatsPeriod.YEAR == period:
        bokeh_script, bokeh_div = charts.last_vs_this_year(
            aspect=aspect,
            user_id=user_id,
            ds=ds,
            is_mobile_view=bool(flask.session.get(COOKIE_MOBILE)),
        )
    elif commons.StatsPeriod.MONTH == period:
        bokeh_script, bokeh_div = charts.last_vs_this_month(
            aspect=aspect,
            user_id=user_id,
            ds=ds,
            is_mobile_view=bool(flask.session.get(COOKIE_MOBILE)),
        )
    else:
        cal_heatmap = views.CalendarHeatmap(
            from_year=int(year),
            to_year=int(year),
            user_profile=user_profile,
            activity_types=ds.list_activity_types(user_id),
            logger=app_logger,
        )
        cal_heatmap.build_activity_type_heatmap(
            activities=ds.list_activities(
                user_id=user_id,
                dataset_name=user_profile.dataset_name,
                skip_meta=False,
            ),
        )

        bokeh_script, bokeh_div = charts.last_vs_this_week(
            heatmap=cal_heatmap,
            aspect=aspect,
            is_mobile_view=bool(flask.session.get(COOKIE_MOBILE)),
        )

    return flask.render_template(
        "this-vs-last.html",
        user_profile=user_profile,
        div=bokeh_div,
        script=bokeh_script,
    )


@flask_app.route("/insight/active-in-week")
def insight_active_in_week():
    user_id = flask.session.get(COOKIE_USER)
    if not user_id:
        return flask.redirect(flask.url_for("login"))
    user_profile = ds.profile(user_id)

    # stats for the last year
    year = ds.activities_stats(
        user_id=user_id, dataset_name=user_profile.dataset_name
    ).year_max
    if not year:
        return flask.redirect(flask.url_for("home"))

    activities = ds.list_activities(
        user_id=user_id, dataset_name=user_profile.dataset_name, skip_future=True
    )
    activities_weekdays = {
        a.key: cals.WEEKDAY_INDEX_2_STR.get(
            calendar.weekday(a.when_year, a.when_month, a.when_day), ""
        )
        for a in activities
    }

    # chart
    bokeh_script, bokeh_div = charts.active_in_week(
        activities=activities,
        activities_weekdays=activities_weekdays,
        activity_types=ds.list_activity_types(user_id),
        is_mobile_view=bool(flask.session.get(COOKIE_MOBILE)),
    )

    return flask.render_template(
        "active-in-week.html",
        user_profile=user_profile,
        div=bokeh_div,
        script=bokeh_script,
    )


@flask_app.route("/insight/weight")
def insight_weight():
    user_id = flask.session.get(COOKIE_USER)
    if not user_id:
        return flask.redirect(flask.url_for("login"))
    user_profile = ds.profile(user_id)

    fig = charts.weight_per_week(
        activities=ds.list_activities(
            user_id=user_id,
            dataset_name=user_profile.dataset_name,
            sort_by_when=True,
            skip_future=True,
        ),
        is_mobile_view=bool(flask.session.get(COOKIE_MOBILE)),
    )

    bokeh_script, bokeh_div = bokeh_components(fig)

    return flask.render_template(
        "weight.html",
        user_profile=user_profile,
        div=bokeh_div,
        script=bokeh_script,
    )


@flask_app.route("/insight/resting-hr")
def insight_resting_hr():
    user_id = flask.session.get(COOKIE_USER)
    if not user_id:
        return flask.redirect(flask.url_for("login"))
    user_profile = ds.profile(user_id)

    fig = charts.resting_hr_per_week(
        activities=ds.list_activities(
            user_id=user_id,
            dataset_name=user_profile.dataset_name,
            sort_by_when=True,
            skip_future=True,
        ),
        is_mobile_view=bool(flask.session.get(COOKIE_MOBILE)),
    )

    bokeh_script, bokeh_div = bokeh_components(fig)

    return flask.render_template(
        "resting-hr.html",
        user_profile=user_profile,
        div=bokeh_div,
        script=bokeh_script,
    )


@flask_app.route("/insight/predictions")
def insight_predictions():
    user_id = flask.session.get(COOKIE_USER)
    if not user_id:
        return flask.redirect(flask.url_for("login"))
    user_profile = ds.profile(user_id)

    cal_heatmap = ds.activity_type_heatmap(
        user_id=user_id, dataset_name=user_profile.dataset_name
    )

    all_acts = ds.all_activities(
        user_id=user_id,
        dataset_name=user_profile.dataset_name,
    )

    on_the_same_day = insights.OnTheSameDay(
        today=datetime.date.today(),
        heatmap=cal_heatmap,
        profile_stats=stats.UserProfileStats.from_entity(
            user_profile=user_profile,
            activities=list(all_acts.values()),
            logger=app_logger,
        ),
        symptoms=ds.list_symptoms(user_id=user_id),
    )

    icl_predictions = _compute_icl_predictions(user_profile, all_acts)

    return flask.render_template(
        "predictions.html",
        user_profile=user_profile,
        insights=on_the_same_day,
        icl_predictions=icl_predictions,
    )


def _compute_icl_predictions(user_profile, all_acts: dict) -> dict | None:
    """Compute ICL predictions when the feature is enabled.

    Returns ``None`` when ICL is disabled or the ``tabpfn`` package is not
    installed; otherwise returns a dict with one key per use case.

    Parameters
    ----------
    user_profile : UserProfile
        The current user profile (provides icl_settings).
    all_acts : dict
        All activity entities keyed by activity key.

    Returns
    -------
    dict | None
        Prediction results or None when ICL is not active.
    """
    icl_cfg = user_profile.icl_settings
    if not icl_cfg.enabled:
        return None

    try:
        from mytral.ml.icl import features as icl_features
        from mytral.ml.icl.predictions import anomaly as icl_anomaly
        from mytral.ml.icl.predictions import fatigue as icl_fatigue
        from mytral.ml.icl.predictions import performance as icl_performance
        from mytral.ml.icl.predictions import rest_day as icl_rest_day
        from mytral.ml.icl.predictions import sick as icl_sick
    except ImportError:
        return None

    activities_json = icl_features.build_activities_json_for_icl(all_acts)

    illness_risk = (
        icl_sick.IclSickPredictor().predict(activities_json)
        if icl_cfg.enable_illness_risk
        else None
    )
    fatigue = (
        icl_fatigue.IclFatiguePredictor().predict(activities_json)
        if icl_cfg.enable_fatigue
        else None
    )
    performance = (
        icl_performance.IclPerformancePredictor().predict(activities_json)
        if icl_cfg.enable_performance
        else None
    )
    rest_day = (
        icl_rest_day.IclRestDayPredictor().predict(activities_json)
        if icl_cfg.enable_rest_day
        else None
    )
    anomaly = (
        icl_anomaly.IclAnomalyPredictor().predict(activities_json)
        if icl_cfg.enable_anomaly
        else None
    )

    return {
        "illness_risk": illness_risk,
        "fatigue": fatigue,
        "performance": performance,
        "rest_day": rest_day,
        "anomaly": anomaly,
    }


@flask_app.route("/insight/lifetime-totals")
def insight_lifetime_totals():
    user_id = flask.session.get(COOKIE_USER)
    if not user_id:
        return flask.redirect(flask.url_for("login"))
    user_profile = ds.profile(user_id)

    ds_stats = ds.activities_stats(
        user_id=user_id, dataset_name=user_profile.dataset_name
    )

    return flask.render_template(
        "lifetime-totals.html",
        user_profile=user_profile,
        stats=ds_stats,
        activity_types=ds.list_activity_types(user_id=user_id),
    )


@flask_app.route("/insight/yoy-performance")
def insight_yoy_performance():
    user_id = flask.session.get(COOKIE_USER)
    if not user_id:
        return flask.redirect(flask.url_for("login"))
    user_profile = ds.profile(user_id)

    ds_stats = ds.activities_stats(
        user_id=user_id,
        dataset_name=user_profile.dataset_name,
        include_meta=True,
    )

    # default to chart view
    aspect = flask.request.args.get("aspect", "chart")

    bokeh_script, bokeh_div = None, None
    if aspect != "list" and len(ds_stats.years) > 1:
        bokeh_script, bokeh_div = charts.year_over_year_performance(
            ds_stats=ds_stats,
            is_mobile_view=bool(flask.session.get(COOKIE_MOBILE)),
        )

    return flask.render_template(
        "insight-yoy-performance.html",
        user_profile=user_profile,
        stats=ds_stats,
        div=bokeh_div,
        script=bokeh_script,
        aspect=aspect,
    )


@flask_app.route("/insight/activity-type-stats")
def insight_sport_stats():
    user_id = flask.session.get(COOKIE_USER)
    if not user_id:
        return flask.redirect(flask.url_for("login"))
    user_profile = ds.profile(user_id)

    ds_stats = ds.activities_stats(
        user_id=user_id,
        dataset_name=user_profile.dataset_name,
        include_meta=True,
    )

    return flask.render_template(
        "insight-activity-type-stats.html",
        user_profile=user_profile,
        stats=ds_stats,
        activity_types=ds.list_activity_types(user_id=user_id),
    )


@flask_app.route("/insight/gear-performance")
def insight_gear_performance():
    user_id = flask.session.get(COOKIE_USER)
    if not user_id:
        return flask.redirect(flask.url_for("login"))
    user_profile = ds.profile(user_id)

    ds_stats = ds.activities_stats(
        user_id=user_id,
        dataset_name=user_profile.dataset_name,
        include_meta=True,
    )

    return flask.render_template(
        "insight-gear-performance.html",
        user_profile=user_profile,
        stats=ds_stats,
        user_gear=ds.list_gear(user_id=user_id),
    )


@flask_app.route("/doc/technical")
def doc_technical():
    user_id = flask.session.get(COOKIE_USER)
    if not user_id:
        return flask.redirect(flask.url_for("login"))

    return flask.render_template(
        "doc-technical-documentation.html", user_profile=ds.profile(user_id)
    )


@flask_app.route("/doc/resources")
def doc_resources():
    user_id = flask.session.get(COOKIE_USER)
    if not user_id:
        return flask.redirect(flask.url_for("login"))

    return flask.render_template("doc-resources.html", user_profile=ds.profile(user_id))


@flask_app.route("/doc/project-history")
def doc_project_history():
    user_id = flask.session.get(COOKIE_USER)
    if not user_id:
        return flask.redirect(flask.url_for("login"))

    return flask.render_template(
        "doc-project-history.html", user_profile=ds.profile(user_id)
    )


@flask_app.route("/about")
def about():
    user_id = flask.session.get(COOKIE_USER)
    if not user_id:
        return flask.redirect(flask.url_for("login"))

    return flask.render_template("about.html", user_profile=ds.profile(user_id))


#
# Task management routes
#


@flask_app.route("/tasks")
def tasks_list():
    """List all tasks for the current user."""
    user_id = flask.session.get(COOKIE_USER)
    if not user_id:
        return flask.redirect(flask.url_for("login"))

    all_tasks = app_task_manager.executor.get_all_tasks(user_id)
    running_tasks_count = sum(
        1 for t in all_tasks if t.status == task_entities.TaskStatus.RUNNING
    )
    return flask.render_template(
        "tasks-list.html",
        user_profile=ds.profile(user_id),
        tasks=all_tasks,
        running_tasks_count=running_tasks_count,
        cleanup_form=forms.CleanupTasksForm(),
        hello_world_form=forms.SubmitHelloWorldForm(),
        delete_form=forms.DeleteTaskForm(),
    )


@flask_app.route("/tasks/<task_id>")
def task_detail(task_id):
    """View task details."""
    user_id = flask.session.get(COOKIE_USER)
    if not user_id:
        return flask.redirect(flask.url_for("login"))

    task = app_task_manager.executor.get_status(task_id, user_id)
    logs = app_task_manager.executor.get_logs(task_id, user_id, tail=1000)

    return flask.render_template(
        "tasks-detail.html",
        user_profile=ds.profile(user_id),
        task=task,
        logs=logs,
        cancel_form=forms.CancelTaskForm(),
        delete_form=forms.DeleteTaskForm(),
        now=datetime.datetime.now(),
    )


@flask_app.route("/tasks/<task_id>/delete", methods=["POST"])
def task_delete(task_id):
    """Delete a finished (completed/failed) task."""
    user_id = flask.session.get(COOKIE_USER)
    if not user_id:
        return flask.redirect(flask.url_for("login"))

    form = forms.DeleteTaskForm()
    if not form.validate_on_submit():
        flask.abort(403)

    try:
        # verify task is finished before deletion
        task = app_task_manager.executor.get_status(task_id, user_id)
        if task.status not in [
            task_entities.TaskStatus.COMPLETED,
            task_entities.TaskStatus.FAILED,
        ]:
            flask.flash("Cannot delete a task that is still running or queued", "error")
            return flask.redirect(flask.url_for("task_detail", task_id=task_id))

        app_task_manager.storage.delete_task(user_id, task_id)
        flask.flash("Task deleted successfully", "success")
    except Exception as e:
        flask.flash(f"Failed to delete task: {str(e)}", "error")

    return flask.redirect(flask.url_for("tasks_list"))


@flask_app.route("/tasks/<task_id>/download-log")
def task_download_log(task_id):
    """Download task log as a text file."""
    user_id = flask.session.get(COOKIE_USER)
    if not user_id:
        return flask.redirect(flask.url_for("login"))

    logs = app_task_manager.executor.get_logs(task_id, user_id, tail=10000)
    content = "\n".join(logs)
    return flask.Response(
        content,
        mimetype="text/plain",
        headers={"Content-Disposition": f"attachment; filename=task-{task_id[:8]}.log"},
    )


@flask_app.route("/api/tasks/status")
def api_tasks_status():
    """Get all tasks status (JSON for AJAX polling)."""
    user_id = flask.session.get(COOKIE_USER)
    if not user_id:
        return flask.jsonify({"error": "Not authenticated"}), 401

    all_tasks = app_task_manager.executor.get_all_tasks(user_id)
    running_tasks = [
        t for t in all_tasks if t.status == task_entities.TaskStatus.RUNNING
    ]

    return flask.jsonify(
        {
            "tasks": [t.to_dict() for t in all_tasks],
            "running_count": len(running_tasks),
        }
    )


@flask_app.route("/api/tasks/<task_id>")
def api_task_status(task_id):
    """Get task details (JSON)."""
    user_id = flask.session.get(COOKIE_USER)
    if not user_id:
        return flask.jsonify({"error": "Not authenticated"}), 401

    try:
        task = app_task_manager.executor.get_status(task_id, user_id)
        return flask.jsonify(task.to_dict())
    except Exception as e:
        return flask.jsonify({"error": str(e)}), 404


@flask_app.route("/api/tasks/<task_id>/logs")
def api_task_logs(task_id):
    """Get task logs (JSON, paginated)."""
    user_id = flask.session.get(COOKIE_USER)
    if not user_id:
        return flask.jsonify({"error": "Not authenticated"}), 401

    tail = flask.request.args.get("tail", default=100, type=int)

    try:
        logs = app_task_manager.executor.get_logs(task_id, user_id, tail=tail)
        return flask.jsonify({"logs": logs})
    except Exception as e:
        return flask.jsonify({"error": str(e)}), 404


@flask_app.route("/tasks/<task_id>/cancel", methods=["POST"])
def task_cancel(task_id):
    """Cancel a running task."""
    user_id = flask.session.get(COOKIE_USER)
    if not user_id:
        return flask.redirect(flask.url_for("login"))

    form = forms.CancelTaskForm()
    if not form.validate_on_submit():
        flask.abort(403)

    success = app_task_manager.executor.cancel(task_id, user_id)
    if success:
        flask.flash("Task cancellation requested", "info")
    else:
        flask.flash("Task could not be cancelled", "error")

    return flask.redirect(flask.url_for("task_detail", task_id=task_id))


@flask_app.route("/tasks/hello-world", methods=["POST"])
def task_submit_hello_world():
    """Submit Hello World task (for testing)."""
    user_id = flask.session.get(COOKIE_USER)
    if not user_id:
        return flask.redirect(flask.url_for("login"))

    form = forms.SubmitHelloWorldForm()
    if not form.validate_on_submit():
        flask.abort(403)

    # create task entity
    task_entity = task_entities.TaskEntity(
        key=str(uuid.uuid4()),
        user_id=user_id,
        task_type="hello_world",
        status=task_entities.TaskStatus.QUEUED,
        created_at=datetime.datetime.now(),
        started_at=None,
        completed_at=None,
        error_message=None,
        error_type=None,
        error_traceback=None,
        progress=0,
        parameters={},
        is_cancelled=False,
        result_route="calendar_year",
        result_route_kwargs={"year": 2025},
    )

    # submit task
    try:
        task_id = app_task_manager.executor.submit(task_entity)
        flask.flash(f"Hello World task submitted: {task_id}", "success")
        return flask.redirect(flask.url_for("task_detail", task_id=task_id))
    except Exception as e:
        app_logger.error(
            f"[Tasks] unable to submit task: {e}\n{traceback.format_exc()}",
            task_type=task_entity.task_type,
            traceback=traceback.format_exc(),
        )
        flask.flash(f"Failed to submit task: {str(e)}", "error")
        return flask.redirect(flask.url_for("tasks_list"))


@flask_app.route("/tasks/cleanup", methods=["POST"])
def tasks_cleanup():
    """Delete all finished (completed/failed) tasks."""
    user_id = flask.session.get(COOKIE_USER)
    if not user_id:
        return flask.redirect(flask.url_for("login"))

    form = forms.CleanupTasksForm()
    if not form.validate_on_submit():
        flask.abort(403)

    try:
        deleted_count = app_task_manager.storage.cleanup_finished_tasks(user_id)
        flask.flash(f"Deleted {deleted_count} finished task(s)", "success")
    except Exception as e:
        flask.flash(f"Failed to cleanup tasks: {str(e)}", "error")

    return flask.redirect(flask.url_for("tasks_list"))


@flask_app.route("/notifications/clear", methods=["POST"])
def notifications_clear():
    """Clear all notifications for the current user."""
    user_id = flask.session.get(COOKIE_USER)
    if not user_id:
        return flask.redirect(flask.url_for("login"))

    form = forms.ClearNotificationsForm()
    if not form.validate_on_submit():
        flask.abort(403)

    notif_storage = notif_mod.store
    notif_storage.clear_all(user_id)

    # redirect back to the page the user came from
    referrer = flask.request.referrer
    if referrer:
        return flask.redirect(referrer)
    return flask.redirect(flask.url_for("home"))


def _avatar_service() -> blob_pkg.AvatarBlobService:
    """Return an AvatarBlobService bound to the global store."""
    return blob_pkg.AvatarBlobService(store=mytral.app_blobstore)


@flask_app.route("/profile/avatar/upload", methods=["POST"])
def upload_user_avatar():
    """Upload and replace the current user's avatar photo."""
    user_id = flask.session.get(COOKIE_USER)
    if not user_id:
        return flask.redirect(flask.url_for("login"))

    form = forms.UploadAvatarForm(prefix="ua")
    if not form.validate_on_submit():
        msg = "Avatar upload form validation failed"
        app_logger.error(msg, user_id=user_id, traceback=traceback.format_exc())
        flask.flash(message=msg, category="error")
        return flask.redirect(flask.url_for("profile_update"))

    f = form.photo.data
    raw = f.stream.read()
    ext = "." + (f.filename.rsplit(".", 1)[-1] if "." in f.filename else "jpg")

    svc = _avatar_service()
    user_profile = ds.profile(user_id)
    old_blob_key = user_profile.avatar_blob_key

    try:
        meta = svc.upload_user_avatar(user_id=user_id, data=raw, extension=ext)
    except (blob_pkg.BlobValidationError, blob_pkg.BlobStoreError) as exc:
        msg = f"Avatar upload failed: {exc}"
        app_logger.error(msg, user_id=user_id, traceback=traceback.format_exc())
        flask.flash(message=msg, category="error")
        return flask.redirect(flask.url_for("profile_update"))

    # persist new key before deleting old blob to avoid data loss
    user_profile.avatar_blob_key = meta.blob_key
    ds.update_profile(user_profile)

    if old_blob_key:
        try:
            svc.delete_avatar(user_id=user_id, blob_key=old_blob_key)
        except Exception:
            pass  # old blob cleanup is best-effort

    flask.flash(message="Avatar updated.", category="success")
    return flask.redirect(flask.url_for("profile_update"))


@flask_app.route("/profile/avatar/delete", methods=["POST"])
def delete_user_avatar():
    """Remove the current user's avatar photo."""
    user_id = flask.session.get(COOKIE_USER)
    if not user_id:
        return flask.redirect(flask.url_for("login"))

    form = forms.DeleteAvatarForm(prefix="da")
    if not form.validate_on_submit():
        flask.flash(message="Delete avatar form validation failed.", category="error")
        return flask.redirect(flask.url_for("profile_update"))

    user_profile = ds.profile(user_id)
    blob_key = user_profile.avatar_blob_key
    if blob_key:
        svc = _avatar_service()
        user_profile.avatar_blob_key = ""
        ds.update_profile(user_profile)
        try:
            svc.delete_avatar(user_id=user_id, blob_key=blob_key)
        except Exception:
            pass  # best-effort

    flask.flash(message="Avatar removed.", category="success")
    return flask.redirect(flask.url_for("profile_update"))


@flask_app.route("/profile/avatar", methods=["GET"])
def get_user_avatar():
    """Serve the user's full-size (200×200) avatar JPEG."""
    user_id = flask.session.get(COOKIE_USER)
    if not user_id:
        flask.abort(404)

    user_profile = ds.profile(user_id)
    blob_key = user_profile.avatar_blob_key
    if not blob_key:
        flask.abort(404)

    svc = _avatar_service()
    try:
        stream = svc.open_user_avatar(user_id=user_id, blob_key=blob_key)
        return flask.send_file(stream, mimetype="image/jpeg")
    except blob_pkg.BlobNotFoundError:
        flask.abort(404)


@flask_app.route("/profile/avatar/thumbnail", methods=["GET"])
def get_user_avatar_thumbnail():
    """Serve the user's 40×40 avatar thumbnail JPEG."""
    user_id = flask.session.get(COOKIE_USER)
    if not user_id:
        flask.abort(404)

    user_profile = ds.profile(user_id)
    blob_key = user_profile.avatar_blob_key
    if not blob_key:
        flask.abort(404)

    svc = _avatar_service()
    try:
        stream = svc.open_user_avatar(
            user_id=user_id, blob_key=blob_key, thumbnail=True
        )
        return flask.send_file(stream, mimetype="image/jpeg")
    except blob_pkg.BlobNotFoundError:
        flask.abort(404)


@flask_app.route("/athlete/metrics", methods=["GET"])
def athlete_metrics():
    """View athlete metrics (set values and resolved estimates)."""
    user_id = flask.session.get(COOKIE_USER)
    if not user_id:
        return flask.redirect(flask.url_for("login"))

    user_profile = ds.profile(user_id)
    dataset_name = user_profile.dataset_name
    all_activities = ds.all_activities(user_id=user_id, dataset_name=dataset_name)

    profile_stats = stats.UserProfileStats.from_entity(
        user_profile=user_profile,
        activities=list(all_activities.values()),
        logger=app_logger,
    )

    form = forms.AthleteMetricsForm()
    form.max_hr.data = user_profile.athlete_metrics.max_hr
    form.anaerobic_threshold_hr.data = (
        user_profile.athlete_metrics.anaerobic_threshold_hr
    )
    form.aerobic_threshold_hr.data = user_profile.athlete_metrics.aerobic_threshold_hr
    form.ftp.data = user_profile.athlete_metrics.ftp
    form.vo2max.data = user_profile.athlete_metrics.vo2max
    form.hrv_rmssd.data = user_profile.athlete_metrics.hrv_rmssd
    form.fat_max.data = user_profile.athlete_metrics.fat_max

    return flask.render_template(
        "athlete-metrics-get.html",
        user_profile=user_profile,
        form=form,
        stats=profile_stats,
    )


@flask_app.route("/athlete/metrics/update", methods=["GET", "POST"])
def athlete_metrics_update():
    """Edit athlete metrics."""
    user_id = flask.session.get(COOKIE_USER)
    if not user_id:
        return flask.redirect(flask.url_for("login"))

    user_profile = ds.profile(user_id)

    if flask.request.method == "GET":
        dataset_name = user_profile.dataset_name
        all_activities = ds.all_activities(user_id=user_id, dataset_name=dataset_name)
        profile_stats = stats.UserProfileStats.from_entity(
            user_profile=user_profile,
            activities=list(all_activities.values()),
            logger=app_logger,
        )

        form = forms.AthleteMetricsForm()
        form.max_hr.data = user_profile.athlete_metrics.max_hr
        form.anaerobic_threshold_hr.data = (
            user_profile.athlete_metrics.anaerobic_threshold_hr
        )
        form.aerobic_threshold_hr.data = (
            user_profile.athlete_metrics.aerobic_threshold_hr
        )
        form.ftp.data = user_profile.athlete_metrics.ftp
        form.vo2max.data = user_profile.athlete_metrics.vo2max
        form.hrv_rmssd.data = user_profile.athlete_metrics.hrv_rmssd
        form.fat_max.data = user_profile.athlete_metrics.fat_max
        form.z1_high.data = user_profile.athlete_metrics.z1_high
        form.z2_high.data = user_profile.athlete_metrics.z2_high
        form.z3_high.data = user_profile.athlete_metrics.z3_high
        form.z4_high.data = user_profile.athlete_metrics.z4_high
        form.birthday_year.data = user_profile.born_year
        form.birthday_month.data = user_profile.born_month
        form.birthday_day.data = user_profile.born_day
        form.height.data = user_profile.height

        return flask.render_template(
            "athlete-metrics-update.html",
            user_profile=user_profile,
            form=form,
            stats=profile_stats,
        )

    if flask.request.method == "POST":
        form = forms.AthleteMetricsForm()
        try:
            if form.validate_on_submit():
                user_profile.athlete_metrics.max_hr = int(form.max_hr.data or 0)
                user_profile.athlete_metrics.anaerobic_threshold_hr = int(
                    form.anaerobic_threshold_hr.data or 0
                )
                user_profile.athlete_metrics.aerobic_threshold_hr = int(
                    form.aerobic_threshold_hr.data or 0
                )
                user_profile.athlete_metrics.ftp = float(form.ftp.data or 0.0)
                user_profile.athlete_metrics.vo2max = float(form.vo2max.data or 0.0)
                user_profile.athlete_metrics.hrv_rmssd = float(
                    form.hrv_rmssd.data or 0.0
                )
                user_profile.athlete_metrics.fat_max = float(form.fat_max.data or 0.0)
                user_profile.athlete_metrics.z1_high = int(form.z1_high.data or 0)
                user_profile.athlete_metrics.z2_high = int(form.z2_high.data or 0)
                user_profile.athlete_metrics.z3_high = int(form.z3_high.data or 0)
                user_profile.athlete_metrics.z4_high = int(form.z4_high.data or 0)

                if (
                    form.birthday_year.data
                    and form.birthday_month.data
                    and form.birthday_day.data
                ):
                    user_profile.born_year = int(form.birthday_year.data)
                    user_profile.born_month = int(form.birthday_month.data)
                    user_profile.born_day = int(form.birthday_day.data)
                    user_profile.refresh_age()

                if form.height.data:
                    user_profile.height = float(form.height.data)

                ds.update_profile(user_profile=user_profile)
                ds.cache_evict(user_id=user_id)

                flask.flash(
                    message="Athlete metrics updated successfully", category="success"
                )
                return flask.redirect(flask.url_for("athlete_metrics"))

            # log and surface field-level validation errors
            invalid_fields = []
            for field_name, field_errors in form.errors.items():
                field = getattr(form, field_name, None)
                label = field.label.text if field and field.label else field_name
                for error in field_errors:
                    app_logger.warning(
                        "athlete_metrics_update(): validation error - field=%s "
                        "label=%r error=%s",
                        field_name,
                        label,
                        error,
                    )
                invalid_fields.append(label or field_name)

            if invalid_fields:
                flask.flash(
                    message=(
                        f"Invalid metrics data — please fix: "
                        f"{', '.join(invalid_fields)}"
                    ),
                    category="error",
                )
            else:
                flask.flash(message="Invalid metrics data", category="error")

        except Exception:
            app_logger.error("athlete_metrics_update: unexpected error during POST")
            flask.flash(
                message="An unexpected error occurred while saving metrics",
                category="error",
            )

        # re-render the form in-place so field errors are visible
        dataset_name = user_profile.dataset_name
        all_activities = ds.all_activities(user_id=user_id, dataset_name=dataset_name)
        profile_stats = stats.UserProfileStats.from_entity(
            user_profile=user_profile,
            activities=list(all_activities.values()),
            logger=app_logger,
        )
        return flask.render_template(
            "athlete-metrics-update.html",
            user_profile=user_profile,
            form=form,
            stats=profile_stats,
        ), 422

    flask.flash(message="Unsupported HTTP method", category="error")
    return flask.redirect(flask.url_for("athlete_metrics"))


@flask_app.route("/onboarding/dismiss", methods=["POST"])
def onboarding_dismiss():
    """Dismiss onboarding permanently."""
    user_id = flask.session.get(COOKIE_USER)
    if not user_id:
        return flask.redirect(flask.url_for("login"))

    from mytral import onboarding as ob

    user_profile = ds.profile(user_id)
    ob.dismiss_onboarding(user_profile)
    ds.update_profile(user_profile)

    flask.flash(message="Onboarding dismissed", category="success")
    return flask.redirect(flask.url_for("home"))


@flask_app.route("/onboarding/reset", methods=["POST"])
def onboarding_reset():
    """Reset onboarding to initial state."""
    user_id = flask.session.get(COOKIE_USER)
    if not user_id:
        return flask.redirect(flask.url_for("login"))

    from mytral import onboarding as ob

    user_profile = ds.profile(user_id)
    ob.reset_onboarding(user_profile)
    ds.update_profile(user_profile)

    flask.flash(message="Onboarding restarted", category="success")
    return flask.redirect(flask.url_for("home"))


@flask_app.route("/settings", methods=["GET", "POST"])
def settings():
    user_id = flask.session.get(COOKIE_USER)
    if not user_id:
        return flask.redirect(flask.url_for("login"))

    if flask.request.method == "POST":
        form = forms.SettingsForm()
        if form.validate_on_submit():
            app_logger.info(
                f"[Settings] POST action: {flask.request.form.get('action')}"
            )

            # CREATE new dataset
            if flask.request.form.get("action") == "Add":
                new_ds_name = app_ds.create_dataset_name(form.new_dataset_file.data)

                user_profile = ds.profile(user_id)
                if new_ds_name in user_profile.dataset_names:
                    flask.flash(
                        message=(
                            f"Unable to create activities dataset '{new_ds_name}' - "
                            f"it already exists"
                        ),
                        category="error",
                    )
                    return flask.redirect(flask.url_for("settings"))

                try:
                    ds.create_activities_dataset(
                        user_id=user_id,
                        dataset_name=new_ds_name,
                    )
                except Exception as ex:
                    flask.flash(
                        message=(
                            f"Unable to create activities dataset '{new_ds_name}': {ex}"
                        ),
                        category="error",
                    )
                    return flask.redirect(flask.url_for("settings"))

                # set new dataset as the current
                user_profile.dataset_name = new_ds_name
                user_profile.dataset_names.append(new_ds_name)
                ds.update_profile(user_profile=user_profile)

                ds.cache_evict(user_id=user_id)

                return flask.redirect(flask.url_for("home"))

            # EVICT user cache
            elif flask.request.form.get("action") == "EvictUserCache":
                ds.cache_evict(user_id=user_id)
                return flask.redirect(flask.url_for("home"))

            # DELETE dataset
            elif flask.request.form.get("action") == "Delete":
                ds_name_2_delete = form.data_files.data

                user_profile = ds.profile(user_id)

                if len(user_profile.dataset_names) <= 1:
                    flask.flash(
                        message=(
                            f"Error deleting dataset '{ds_name_2_delete}' - there is "
                            f"no other dataset - at least one must be kept"
                        ),
                        category="error",
                    )
                    return flask.redirect(flask.url_for("settings"))

                if ds_name_2_delete not in user_profile.dataset_names:
                    flask.flash(
                        message=(
                            f"Error deleting dataset '{ds_name_2_delete}' - it "
                            f"does not exist for user {user_id}"
                        ),
                        category="error",
                    )
                    return flask.redirect(flask.url_for("settings"))

                # delete all blobs for all activities in the dataset
                blob_svc = _blob_service()
                activities = ds.list_activities(
                    user_id=user_id, dataset_name=ds_name_2_delete
                )
                for a in activities:
                    try:
                        blob_svc.delete_all_activity_blobs(
                            user_id=user_id, activity_key=a.key
                        )
                    except Exception as exc:
                        app_logger.warning(
                            f"Failed to delete blobs for activity {a.key}: {exc}"
                        )

                ds.delete_activities_dataset(
                    user_id=user_id, dataset_name=ds_name_2_delete
                )

                user_profile.dataset_names.remove(ds_name_2_delete)
                if user_profile.dataset_name == ds_name_2_delete:
                    user_profile.dataset_name = user_profile.dataset_names[0]
                ds.update_profile(user_profile=user_profile)

                ds.cache_evict(user_id=user_id)

                return flask.redirect(flask.url_for("settings"))

            # SET dataset - modify user profile ~ change the current dataset
            ds_2_set = form.data_files.data
            user_profile = ds.profile(user_id)
            if ds_2_set not in user_profile.dataset_names:
                flask.flash(
                    message=(
                        f"Error setting dataset '{ds_2_set}' - it does not exist for "
                        f"user {user_id}"
                    ),
                    category="error",
                )
                return flask.redirect(flask.url_for("settings"))
            user_profile.dataset_name = ds_2_set
            ds.update_profile(user_profile)

            ds.cache_evict(user_id=user_id)

            return flask.redirect(flask.url_for("home"))

        flask.flash(message="Error saving settings", category="error")
        return flask.redirect(flask.url_for("home"))

    elif flask.request.method == "GET":
        user_profile = ds.profile(user_id)
        form = forms.SettingsForm()
        form.data_files.choices = [(f, f) for f in user_profile.dataset_names]
        form.data_files.default = user_profile.dataset_name
        form.data_files.process(form.data_files.default)

        dataset_name = user_profile.dataset_name
        all_activities = ds.all_activities(user_id=user_id, dataset_name=dataset_name)

        dataset_stats = stats.UserInventoryStats(
            activities_count=len(all_activities),
            gear_count=len(ds.list_gear(user_id).gear_by_key),
            goals_count=len(ds.list_goals(user_id).goals_by_key),
            exercises_count=len(ds.list_exercises(user_id).exercise_by_key),
            laps_count=len(ds.list_laps(user_id).lap_by_key),
            symptoms_count=len(ds.list_symptoms(user_id).symptoms_by_key),
            outfits_count=len(ds.list_outfits(user_id).outfits_by_key),
            activity_types_count=len(
                ds.list_activity_types(user_id).activity_types_by_key
            ),
        )

        user_data_dir = ds.user_dir(user_id)
        total_bytes = sum(
            f.stat().st_size for f in user_data_dir.rglob("*") if f.is_file()
        )
        dataset_stats.dataset_size_mb = round(total_bytes / (1024 * 1024), 3)

        app_logger.debug(f"MyTraL CACHE size: {ds.cache.memory_size():,} B")

        return flask.render_template(
            "settings.html",
            user_profile=user_profile,
            dataset_stats=dataset_stats,
            form=form,
        )

    else:
        flask.flash(
            message=f"Settings error - unsupported method: {flask.request.method}",
            category="error",
        )
        return flask.redirect(flask.url_for("home"))


@flask_app.route("/settings/gear/merge/strava", methods=["GET"])
def settings_gear_merge_strava():
    """Merge Strava gear to user profile gear."""
    user_id = flask.session.get(COOKIE_USER)
    if not user_id:
        return flask.redirect(flask.url_for("login"))

    # load strava gear
    gear_strava = ds.list_strava_gear(user_id=user_id)

    # map: Strava gear ID -> Strava gear
    strava_gear_dict = {}
    if gear_strava:
        for g in gear_strava.gears:
            g_id = str(g["id"])
            strava_gear_dict[g_id] = g

    # load user gear
    dataset_name = ds.profile(user_id).dataset_name
    gear = ds.list_gear(user_id=user_id, dataset_name=dataset_name)

    # extend user gear with Strava gear
    # collect already-known raw Strava IDs (e.g. "b12345")
    known_strava_gear_keys = set()
    for ug in gear.gear.values():
        strava_id = ug.get_external_id("strava")
        if strava_id and strava_id in strava_gear_dict:
            known_strava_gear_keys.add(strava_id)
    unknown_strava_gear_keys = set()
    for kg in gear_strava.gears:
        strava_id = str(kg["id"])
        if strava_id not in known_strava_gear_keys:
            unknown_strava_gear_keys.add(strava_id)

    # add unknown Strava gear to user gear
    for g_id in unknown_strava_gear_keys:
        g = strava_gear_dict.get(g_id)
        if not g:
            raise ValueError(f"Strava gear not found: '{g_id}'")

        # IMPROVE: this saves all gears on every iteration - introduce bulk
        # create_gears([...]) on ds API
        ds.create_gear(
            user_id=user_id,
            dataset_name=dataset_name,
            gear=user_settings.Gear(
                activity_type_key="",  # TODO set it properly
                name=g.get(user_settings.StravaUserGear.KEY_NAME, "Gear"),
                vendor=g.get(user_settings.StravaUserGear.KEY_BRAND_NAME, ""),
                model=g.get(user_settings.StravaUserGear.KEY_MODEL_NAME, ""),
                size="",
                # since ... is calculated from the activities
                comment=g.get(user_settings.StravaUserGear.KEY_DESCRIPTION, ""),
                retired=g.get(user_settings.StravaUserGear.KEY_RETIRED, False),
                is_default=False,
                external_id_map={"strava": g_id},
                # TODO notification distance - nice feature add it - when you need new
                # key ... generated automatically
            ),
        )

    return flask.redirect(flask.url_for("settings_gear_list"))


def _create_activity(
    activity_type: str, year: str = "", month: str = "", day: str = ""
):
    """Create new activity:

    - GET: render blank form
    - POST:
      - action add-exercise:
        create activity in DB (to persist and get key) and redirect to add exercise
        page
      - action add-symptom:
        create activity in DB (to persist and get key) and redirect to add sickness
        symptom page
      - DEFAULT action:
        create activity in DB and redirect to activity detail view
    """
    user_id = flask.session.get(COOKIE_USER)
    if not user_id:
        return flask.redirect(flask.url_for("login"))

    form = forms.CreateActivityForm()
    # activity_type_key choices
    sport_choices = ds.list_activity_types(user_id).choices()
    form.activity_type_key.choices = sport_choices
    form.activity_type_key.default = sport_choices[0][0]
    # gear choices
    gear_choices = ds.list_gear(
        user_id=user_id, dataset_name=ds.profile(user_id).dataset_name
    ).choices()
    form.gears.choices = sorted(gear_choices, key=lambda x: x[1].lower())
    # outfit choices
    outfit_choices = [("", "")] + [
        (o.key, o.name) for o in ds.list_outfits(user_id).outfits
    ]
    form.outfit.choices = sorted(outfit_choices, key=lambda x: x[1].lower())

    if flask.request.method == "POST":
        # persist activity both in case of create or adding exercise / symptom
        if form.validate_on_submit():
            entity = forms.from_activity_form(form=form, ds=ds, user_id=user_id)
            entity.name = entity.name or entity.activity_type_key
            entity = ds.create_activity(
                user_id=user_id,
                dataset_name=ds.profile(user_id).dataset_name,
                entity=entity,
            )

            if flask.request.form.get("action") == "Add Exercise":
                # activity is persisted -> use its key to add exercise to it
                return flask.redirect(
                    flask.url_for(
                        "create_activity_add_exercise",
                        key=entity.key,
                    ),
                )
            elif flask.request.form.get("action") == "Add Symptom":
                # activity is persisted -> use its key to add symptom to it
                return flask.redirect(
                    flask.url_for(
                        "create_activity_add_symptom",
                        key=entity.key,
                    ),
                )
            elif flask.request.form.get("action") == "Add Lap":
                # activity is persisted -> use its key to add lap to it
                return flask.redirect(
                    flask.url_for(
                        "create_activity_add_lap",
                        key=entity.key,
                    ),
                )
            elif flask.request.form.get("action") == "Add Photo":
                # activity is persisted -> redirect to photo upload
                return flask.redirect(
                    flask.url_for(
                        "upload_activity_photos",
                        activity_key=entity.key,
                    ),
                )
            elif flask.request.form.get("action") == "Add GPX":
                # activity is persisted -> redirect to recording upload
                return flask.redirect(
                    flask.url_for(
                        "get_activity",
                        key=entity.key,
                    ),
                )
            else:
                # default dispatch: view created activity
                flask.flash(message="Activity created", category="success")
                return flask.redirect(
                    flask.url_for(
                        "get_activity",
                        key=entity.key,
                    )
                )
        else:
            flask.flash(message="Activity creation error", category="error")
            # ... error will be rendered by the return statement below

    elif flask.request.method == "GET":
        # fields
        form.name.default = activity_type if activity_type != "any" else ""
        form.name.process(form.name.default)
        form.formula.default = "2*" if activity_type == "Sauna" else ""
        form.formula.process(form.formula.default)
        form.activity_type_key.default = activity_type if activity_type != "any" else ""
        form.activity_type_key.process(form.activity_type_key.default)

        if year:
            form.when_year.data = int(year)
        if month:
            form.when_month.data = int(month)
        if day:
            form.when_day.data = int(day)

    else:
        flask.flash(
            message=(
                f"Activity creation error - unsupported method: {flask.request.method}"
            ),
            category="error",
        )
        return flask.redirect(flask.url_for("home"))

    match activity_type:
        case commons.AT_SICK:
            template = "activity-create-sick.html"
        case commons.AT_PHYSIO:
            template = "activity-create-physio.html"
        case commons.AT_MEDITATION:
            template = "activity-create-meditation.html"
        case commons.AT_COMMENT:
            # TODO strip down and/or if/else the template
            template = "activity-create-comment.html"
            form.when_hour.data = 1
            form.when_minute.data = 0
            form.when_second.data = 0
        case _:
            template = "activity-create.html"

    return flask.render_template(
        template,
        user_profile=ds.profile(user_id),
        activity_type=activity_type,
        form=form,
        is_mobile=flask.session.get(COOKIE_MOBILE),
    )


@flask_app.route("/app/activities/create/physiotherapy", methods=["GET", "POST"])
def create_activity_physio():
    return _create_activity(commons.AT_PHYSIO)


@flask_app.route("/app/activities/create/comment", methods=["GET", "POST"])
def create_activity_comment():
    return _create_activity(commons.AT_COMMENT)


@flask_app.route(
    "/app/activities/create/comment/<year>/<month>/<day>", methods=["GET", "POST"]
)
def create_activity_comment_for_date(year, month, day):
    return _create_activity(commons.AT_COMMENT, year=year, month=month, day=day)


@flask_app.route("/app/activities/create/meditation", methods=["GET", "POST"])
def create_activity_meditation():
    return _create_activity(commons.AT_MEDITATION)


@flask_app.route("/app/activities/create/run", methods=["GET", "POST"])
def create_activity_run():
    return _create_activity(commons.AT_RUN)


@flask_app.route("/app/activities/create/row", methods=["GET", "POST"])
def create_activity_row():
    return _create_activity(commons.AT_ROW)


@flask_app.route("/app/activities/create/ride", methods=["GET", "POST"])
def create_activity_ride():
    return _create_activity(commons.AT_RIDE)


@flask_app.route("/app/activities/create/sauna", methods=["GET", "POST"])
def create_activity_sauna():
    return _create_activity(commons.AT_SAUNA)


@flask_app.route("/app/activities/create/sick", methods=["GET", "POST"])
def create_activity_sick():
    return _create_activity(commons.AT_SICK)


@flask_app.route("/app/activities/create/any", methods=["GET", "POST"])
def create_activity_any():
    return _create_activity("any")


@flask_app.route(
    "/app/activities/create/any/<year>/<month>/<day>", methods=["GET", "POST"]
)
def create_activity_any_for_date(year, month, day):
    return _create_activity("any", year=year, month=month, day=day)


@flask_app.route("/app/activities/create", methods=["GET"])
def create_activity():
    user_id = flask.session.get(COOKIE_USER)
    if not user_id:
        return flask.redirect(flask.url_for("login"))

    return flask.render_template(
        "activity-create-type.html", user_profile=ds.profile(user_id)
    )


@flask_app.route("/app/activities/create/date/<year>/<month>/<day>", methods=["GET"])
def create_activity_for_date(year, month, day):
    user_id = flask.session.get(COOKIE_USER)
    if not user_id:
        return flask.redirect(flask.url_for("login"))

    return flask.render_template(
        "activity-create-type.html",
        user_profile=ds.profile(user_id),
        year=year,
        month=month,
        day=day,
    )


@flask_app.route("/app/activities/<key>/exercise", methods=["GET", "POST"])
def create_activity_add_exercise(key):
    """Add new exercise to given activity.

    - GET: render blank form which has activity key as hidden field
    - POST: add exercise to activity (based on its key) and redirect to activity detail

    """
    user_id = flask.session.get(COOKIE_USER)
    if not user_id:
        return flask.redirect(flask.url_for("login"))

    if flask.request.method == "POST":
        form = forms.AddActivityExerciseForm()
        if form.validate_on_submit():
            exercise_entity = forms.from_activity_exercise_form(form)

            if not key:
                flask.flash(
                    message=(
                        "Exercise add to activity error - missing parent activity key"
                    ),
                    category="error",
                )
            else:
                user_profile = ds.profile(user_id)
                activity_entity = ds.get_activity(
                    user_id=user_id,
                    dataset_name=user_profile.dataset_name,
                    key=key,
                )
                activity_entity.exercises.append(exercise_entity)
                ds.update_activity(
                    user_id=user_id,
                    dataset_name=user_profile.dataset_name,
                    entity=activity_entity,
                )

                flask.flash(message="Exercise added", category="success")
                return flask.redirect(flask.url_for("update_activity", key=key))
        else:
            flask.flash(
                message="Exercise creation error - submit failed to be validated",
                category="error",
            )

    elif flask.request.method == "GET":
        form = forms.AddActivityExerciseForm()
        form.activity_key.data = key
        form.exercise_name.choices = [
            (e.key, e.name) for e in ds.list_exercises(user_id).exercise_by_key.values()
        ]
        form.exercise_name.default = (
            ds.list_exercises(user_id).default_exercise().key
            if not ds.list_exercises(user_id).empty()
            else ""
        )
        form.exercise_name.process(form.exercise_name.default)

    else:
        flask.flash(
            message="Exercise add to activity error - unsupported method",
            category="error",
        )
        return flask.redirect(flask.url_for("home"))

    return flask.render_template(
        "exercise-add.html",
        user_profile=ds.profile(user_id),
        exercises=ds.list_exercises(user_id),
        form=form,
    )


@flask_app.route("/app/activities/<key>/symptom", methods=["GET", "POST"])
def create_activity_add_symptom(key):
    """Add new sickness symptom to given activity.

    - GET: render blank form which has activity key as hidden field
    - POST: add symptom to activity (based on its key) and redirect to activity detail

    """
    user_id = flask.session.get(COOKIE_USER)
    if not user_id:
        return flask.redirect(flask.url_for("login"))

    if flask.request.method == "POST":
        form = forms.AddActivitySymptomForm()
        if form.validate_on_submit():
            symptom_entity = forms.from_activity_symptom_form(form)

            if not key:
                flask.flash(
                    message=(
                        "Sickness symptom add to activity error - missing parent "
                        "activity key"
                    ),
                    category="error",
                )
            else:
                user_profile = ds.profile(user_id)

                activity_entity = ds.get_activity(
                    user_id=user_id,
                    dataset_name=user_profile.dataset_name,
                    key=key,
                )
                activity_entity.sickness_symptoms.append(symptom_entity)
                ds.update_activity(
                    user_id=user_id,
                    dataset_name=user_profile.dataset_name,
                    entity=activity_entity,
                )

                flask.flash(message="Sickness symptom added", category="success")
                return flask.redirect(
                    flask.url_for(
                        "update_activity",
                        key=key,
                    )
                )
        else:
            flask.flash(
                message=(
                    "Sickness symptom add to activity error - submit failed to be "
                    "validated"
                ),
                category="error",
            )

    elif flask.request.method == "GET":
        form = forms.AddActivitySymptomForm()
        form.activity_key.data = key

        form.symptom.choices = [
            (s.key, s.name) for s in ds.list_symptoms(user_id).symptoms_by_key.values()
        ]
        form.symptom.default = (
            ds.list_symptoms(user_id).default_symptom().key
            if not ds.list_symptoms(user_id).empty()
            else ""
        )
        form.symptom.process(form.symptom.default)

    else:
        flask.flash(
            message="Sickness symptom add to activity error - unsupported method",
            category="error",
        )
        return flask.redirect(flask.url_for("home"))

    return flask.render_template(
        "symptom-add.html",
        user_profile=ds.profile(user_id),
        form=form,
    )


@flask_app.route("/app/activities/<key>/lap", methods=["GET", "POST"])
def create_activity_add_lap(key):
    """Add new lap to given activity.

    - GET: render blank form which has activity key as hidden field
    - POST: add lap to activity (based on its key) and redirect to activity detail

    """
    user_id = flask.session.get(COOKIE_USER)
    if not user_id:
        return flask.redirect(flask.url_for("login"))

    if flask.request.method == "POST":
        form = forms.AddActivityLapForm()
        if form.validate_on_submit():
            lap_entity = forms.from_activity_lap_form(form)

            if not key:
                flask.flash(
                    message="Lap add to activity error - missing parent activity key",
                    category="error",
                )
            else:
                activity_entity = ds.get_activity(
                    user_id=user_id,
                    dataset_name=ds.profile(user_id).dataset_name,
                    key=key,
                )

                # set order for new lap
                if activity_entity.laps:
                    lap_entity.order = (
                        max(lap.order for lap in activity_entity.laps) + 1
                    )
                else:
                    lap_entity.order = 1

                # fill in defaults from lap type if not provided
                if lap_entity.distance == 0 or lap_entity.duration == 0:
                    laps = ds.list_laps(user_id)
                    lap_type = laps.lap_by_name.get(lap_entity.name)
                    if lap_type:
                        if lap_entity.distance == 0:
                            lap_entity.distance = lap_type.default_distance
                        if lap_entity.duration == 0:
                            lap_entity.duration = lap_type.default_duration

                activity_entity.laps.append(lap_entity)
                ds.update_activity(
                    user_id=user_id,
                    dataset_name=ds.profile(user_id).dataset_name,
                    entity=activity_entity,
                )

                flask.flash(message="Lap added", category="success")
                return flask.redirect(flask.url_for("update_activity", key=key))
        else:
            flask.flash(
                message="Lap creation error - submit failed to be validated",
                category="error",
            )

    elif flask.request.method == "GET":
        form = forms.AddActivityLapForm()
        form.activity_key.data = key
        form.lap_name.choices = [
            (lap.name, lap.name) for lap in ds.list_laps(user_id).lap_by_key.values()
        ]
        form.lap_name.default = (
            ds.list_laps(user_id).default_lap().name
            if not ds.list_laps(user_id).empty()
            else ""
        )
        form.lap_name.process(form.lap_name.default)

    else:
        flask.flash(
            message="Lap add to activity error - unsupported method",
            category="error",
        )
        return flask.redirect(flask.url_for("home"))

    return flask.render_template(
        "lap-add.html",
        user_profile=ds.profile(user_id),
        laps=ds.list_laps(user_id),
        form=form,
    )


@flask_app.route(
    "/app/activities/<activity_key>/lap/<int:lap_index>/update", methods=["GET", "POST"]
)
def update_activity_lap(activity_key, lap_index):
    """Update lap in activity."""
    user_id = flask.session.get(COOKIE_USER)
    if not user_id:
        return flask.redirect(flask.url_for("login"))

    if flask.request.method == "POST":
        form = forms.UpdateActivityLapForm()
        if form.validate_on_submit():
            lap_entity = forms.from_activity_lap_form(form)

            activity_entity = ds.get_activity(
                user_id=user_id,
                dataset_name=ds.profile(user_id).dataset_name,
                key=activity_key,
            )

            if 0 <= lap_index < len(activity_entity.laps):
                # preserve order
                lap_entity.order = activity_entity.laps[lap_index].order
                activity_entity.laps[lap_index] = lap_entity

                ds.update_activity(
                    user_id=user_id,
                    dataset_name=ds.profile(user_id).dataset_name,
                    entity=activity_entity,
                )
                flask.flash(message="Lap updated", category="success")
                return flask.redirect(
                    flask.url_for("update_activity", key=activity_key)
                )
            else:
                flask.flash(
                    message="Lap update error - invalid index", category="error"
                )
        else:
            flask.flash(
                message="Lap update error - submit failed to be validated",
                category="error",
            )

    elif flask.request.method == "GET":
        activity_entity = ds.get_activity(
            user_id=user_id,
            dataset_name=ds.profile(user_id).dataset_name,
            key=activity_key,
        )

        if 0 <= lap_index < len(activity_entity.laps):
            lap = activity_entity.laps[lap_index]
            form = forms.UpdateActivityLapForm()
            form.activity_key.data = activity_key
            form.order.data = lap.order
            form.lap_name.choices = [
                (lap_item.name, lap_item.name)
                for lap_item in ds.list_laps(user_id).lap_by_key.values()
            ]
            form.lap_name.data = lap.name
            form.distance.data = lap.distance or 0
            total_seconds = lap.duration or 0
            form.hours.data = total_seconds // 3600
            form.minutes.data = (total_seconds % 3600) // 60
            form.seconds.data = total_seconds % 60
            form.comment.data = lap.comment or ""
            form.ranked.data = lap.ranked
        else:
            flask.flash(message="Lap update error - invalid index", category="error")
            return flask.redirect(flask.url_for("update_activity", key=activity_key))

    else:
        flask.flash(message="Lap update error - unsupported method", category="error")
        return flask.redirect(flask.url_for("home"))

    return flask.render_template(
        "lap-update.html",
        user_profile=ds.profile(user_id),
        laps=ds.list_laps(user_id),
        form=form,
    )


@flask_app.route(
    "/app/activities/<activity_key>/lap/<int:lap_index>/delete", methods=["POST"]
)
def delete_activity_lap(activity_key, lap_index):
    """Delete lap from activity."""
    user_id = flask.session.get(COOKIE_USER)
    if not user_id:
        return flask.redirect(flask.url_for("login"))

    activity_entity = ds.get_activity(
        user_id=user_id,
        dataset_name=ds.profile(user_id).dataset_name,
        key=activity_key,
    )

    if 0 <= lap_index < len(activity_entity.laps):
        del activity_entity.laps[lap_index]
        # reorder remaining laps
        for i, lap in enumerate(activity_entity.laps):
            lap.order = i + 1

        ds.update_activity(
            user_id=user_id,
            dataset_name=ds.profile(user_id).dataset_name,
            entity=activity_entity,
        )
        flask.flash(message="Lap deleted", category="success")
    else:
        flask.flash(message="Lap delete error - invalid index", category="error")

    return flask.redirect(flask.url_for("update_activity", key=activity_key))


@flask_app.route(
    "/app/activities/<activity_key>/lap/<int:lap_index>/move/<direction>",
    methods=["POST"],
)
def move_activity_lap(activity_key, lap_index, direction):
    """Move lap up or down in the order."""
    user_id = flask.session.get(COOKIE_USER)
    if not user_id:
        return flask.redirect(flask.url_for("login"))

    activity_entity = ds.get_activity(
        user_id=user_id,
        dataset_name=ds.profile(user_id).dataset_name,
        key=activity_key,
    )

    if 0 <= lap_index < len(activity_entity.laps):
        if direction == "up" and lap_index > 0:
            # swap with previous
            activity_entity.laps[lap_index], activity_entity.laps[lap_index - 1] = (
                activity_entity.laps[lap_index - 1],
                activity_entity.laps[lap_index],
            )
            flask.flash(message="Lap moved up", category="success")
        elif direction == "down" and lap_index < len(activity_entity.laps) - 1:
            # swap with next
            activity_entity.laps[lap_index], activity_entity.laps[lap_index + 1] = (
                activity_entity.laps[lap_index + 1],
                activity_entity.laps[lap_index],
            )
            flask.flash(message="Lap moved down", category="success")

        # reorder all laps
        for i, lap in enumerate(activity_entity.laps):
            lap.order = i + 1

        ds.update_activity(
            user_id=user_id,
            dataset_name=ds.profile(user_id).dataset_name,
            entity=activity_entity,
        )
    else:
        flask.flash(message="Lap move error - invalid index", category="error")

    return flask.redirect(flask.url_for("update_activity", key=activity_key))


def _update_activity(key: str, template: str):
    user_id = flask.session.get(COOKIE_USER)
    if not user_id:
        return flask.redirect(flask.url_for("login"))

    # fetch db_entity upfront so it is available for both GET and POST fail render
    db_entity = ds.get_activity(
        user_id=user_id, dataset_name=ds.profile(user_id).dataset_name, key=key
    )

    form = forms.UpdateActivityForm()

    form.activity_type_key.choices = ds.list_activity_types(user_id).choices()
    # select choices: [(value, name)]
    gear_choices = ds.list_gear(
        user_id=user_id, dataset_name=ds.profile(user_id).dataset_name
    ).choices()
    form.gears.choices = sorted(gear_choices, key=lambda x: x[1].lower())
    outfit_choices = [("", "")] + [
        (o.key, o.name) for o in ds.list_outfits(user_id).outfits
    ]
    form.outfit.choices = sorted(outfit_choices, key=lambda x: x[1].lower())

    if flask.request.method == "GET":
        form.when_year.data = db_entity.when_year
        form.when_month.data = db_entity.when_month
        form.when_day.data = db_entity.when_day
        form.when_hour.data = db_entity.when_hour
        form.when_minute.data = db_entity.when_minute
        form.when_second.data = db_entity.when_second
        form.name.data = db_entity.name or db_entity.activity_type_key
        form.description.data = db_entity.description
        form.where.data = db_entity.where
        form.activity_type_key.data = db_entity.activity_type_key
        form.intensity.data = db_entity.intensity
        form.gears.data = (
            db_entity.gears
            if hasattr(db_entity, "gears")
            else ([db_entity.gear] if db_entity.gear else [])
        )
        form.outfit.data = db_entity.outfit if hasattr(db_entity, "outfit") else ""
        form.formula.data = db_entity.formula

        # exercises
        if db_entity.exercises:
            for e in db_entity.exercises:
                exercise_form = forms.AddActivityExerciseForm()
                exercise_form.exercise_name = e.name or ""
                exercise_form.weight = e.weight or 0.0
                exercise_form.series = e.series or 0
                exercise_form.repetitions = e.repetitions or 0
                exercise_form.duration = e.duration or 0
                exercise_form.rest = e.rest or 0
                form.exercises.append_entry(exercise_form)

        # symptoms
        if db_entity.sickness_symptoms:
            for s in db_entity.sickness_symptoms:
                symptom_form = forms.AddActivitySymptomForm()
                symptom_form.symptom = s.symptom or ""
                symptom_form.side = s.side or ""
                symptom_form.body_part = s.body_part or ""
                symptom_form.health = s.health or 0
                form.sickness_symptoms.append_entry(symptom_form)

        # laps
        if hasattr(db_entity, "laps") and db_entity.laps:
            for lap in db_entity.laps:
                lap_form = forms.AddActivityLapForm()
                lap_form.lap_name = lap.name or ""
                lap_form.distance = lap.distance or 0
                total_seconds = lap.duration or 0
                lap_form.hours = total_seconds // 3600
                lap_form.minutes = (total_seconds % 3600) // 60
                lap_form.seconds = total_seconds % 60
                lap_form.comment = lap.comment or ""
                form.laps.append_entry(lap_form)

        form.hours.data = db_entity.hours
        form.minutes.data = db_entity.minutes
        form.seconds.data = db_entity.seconds
        form.distance.data = db_entity.distance
        form.warm_up.data = db_entity.warm_up
        form.cool_down.data = db_entity.cool_down
        form.commute.data = db_entity.commute
        form.ranked.data = db_entity.ranked
        form.race.data = db_entity.race
        form.kcal.data = int(db_entity.kcal)
        form.max_speed.data = float(db_entity.max_speed)
        form.elevation_gain.data = db_entity.elevation_gain
        form.elevation_min.data = db_entity.elevation_min
        form.elevation_max.data = db_entity.elevation_max
        form.avg_watts.data = int(db_entity.avg_watts)
        form.max_watts.data = int(db_entity.max_watts)
        form.avg_cadence.data = int(db_entity.avg_cadence)
        form.max_cadence.data = int(db_entity.max_cadence)
        form.avg_hr.data = int(db_entity.avg_hr)
        form.max_hr.data = int(db_entity.max_hr)
        form.min_hr.data = int(db_entity.min_hr)
        form.weight.data = db_entity.weight
        form.cost.data = db_entity.cost
        form.weather.data = db_entity.weather
        form.temperature.data = db_entity.temperature
        form.fitness_score.data = db_entity.fitness_score
        form.src.data = db_entity.src
        form.src_descriptor.data = db_entity.src_descriptor
        form.src_key.data = db_entity.src_key
        form.src_url.data = db_entity.src_url
        form.sort_code.data = db_entity.sort_code
        form.workout_sort_code.data = db_entity.workout_sort_code

    elif flask.request.method == "POST":
        if form.validate_on_submit():
            entity = forms.from_activity_form(
                form=form, ds=ds, user_id=user_id
            )  # ... w/o exercises

            entity.key = key
            entity.exercises = db_entity.exercises
            entity.sickness_symptoms = db_entity.sickness_symptoms
            # IMPROVE: auto upgrade from pre-laps datasets - remove hasattr() in future
            entity.laps = db_entity.laps if hasattr(db_entity, "laps") else []
            # preserve blob references set by the blobstore (not part of activity form)
            entity.recorded_blob_keys = list(db_entity.recorded_blob_keys)
            entity.recorded_parquet_keys = dict(db_entity.recorded_parquet_keys)
            entity.photo_blob_keys = list(db_entity.photo_blob_keys)
            entity.highlight_photo_blob_key = db_entity.highlight_photo_blob_key

            action = flask.request.form.get("action", "")

            # handle inline lap operations before saving
            if action.startswith("Delete Lap "):
                try:
                    lap_index = int(action.split()[-1])
                    if 0 <= lap_index < len(entity.laps):
                        del entity.laps[lap_index]
                        for i, lap in enumerate(entity.laps):
                            lap.order = i + 1
                except (ValueError, IndexError):
                    pass
            elif action.startswith("Move Lap Up "):
                try:
                    lap_index = int(action.split()[-1])
                    if 0 < lap_index < len(entity.laps):
                        entity.laps[lap_index], entity.laps[lap_index - 1] = (
                            entity.laps[lap_index - 1],
                            entity.laps[lap_index],
                        )
                        for i, lap in enumerate(entity.laps):
                            lap.order = i + 1
                except (ValueError, IndexError):
                    pass
            elif action.startswith("Move Lap Down "):
                try:
                    lap_index = int(action.split()[-1])
                    if 0 <= lap_index < len(entity.laps) - 1:
                        entity.laps[lap_index], entity.laps[lap_index + 1] = (
                            entity.laps[lap_index + 1],
                            entity.laps[lap_index],
                        )
                        for i, lap in enumerate(entity.laps):
                            lap.order = i + 1
                except (ValueError, IndexError):
                    pass

            ds.update_activity(
                user_id=user_id,
                dataset_name=ds.profile(user_id).dataset_name,
                entity=entity,
            )

            if action == "Add Exercise":
                # activity is persisted -> use its key to add exercise to it
                return flask.redirect(
                    flask.url_for(
                        "create_activity_add_exercise",
                        key=entity.key,
                    ),
                )
            if action == "Add Symptom":
                # activity is persisted -> use its key to add symptom to it
                return flask.redirect(
                    flask.url_for(
                        "create_activity_add_symptom",
                        key=entity.key,
                    ),
                )
            if action == "Add Lap":
                # activity is persisted -> use its key to add lap to it
                return flask.redirect(
                    flask.url_for(
                        "create_activity_add_lap",
                        key=entity.key,
                    ),
                )

            # save-and-navigate: save main form then redirect to sub-entity edit/del URL
            next_url = flask.request.form.get("next_url", "").strip()
            if next_url and next_url.startswith("/"):
                return flask.redirect(next_url)

            if action.startswith("Delete Lap "):
                flask.flash(message="Lap deleted", category="success")
                return flask.redirect(flask.url_for("update_activity", key=key))
            if action.startswith("Move Lap "):
                flask.flash(message="Lap moved", category="success")
                return flask.redirect(flask.url_for("update_activity", key=key))

            flask.flash(message="Activity updated", category="success")
            return flask.redirect(
                flask.url_for(
                    "get_activity",
                    key=key,
                )
            )

        flask.flash(message="Activity update error", category="error")

    else:
        flask.flash(
            message="Activity update error - unsupported method", category="error"
        )
        return flask.redirect(flask.url_for("home"))

    blob_svc = _blob_service()
    try:
        recordings_metadata = []
        for entry in db_entity.recorded_blob_keys:
            entry_uuid = entities_mod.recording_blob_uuid(entry)
            meta = blob_svc.get_recording(
                user_id=user_id, activity_key=key, blob_key=entry_uuid
            )
            if meta:
                recordings_metadata.append(
                    {
                        "blob_uuid": entry_uuid,
                        "ext": entities_mod.recording_ext(entry),
                        "name": meta.name,
                        "original_file_name": meta.original_file_name,
                        "size_bytes": meta.size_bytes,
                        "description": meta.description,
                        "has_parquet": entry_uuid in db_entity.recorded_parquet_keys,
                    }
                )
    except Exception:
        app_logger.error(
            "Unexpected error fetching recordings metadata", activity_key=key
        )
        recordings_metadata = []
    try:
        photo_list = blob_svc.list_photos(user_id=user_id, activity_key=key)
    except blob_pkg.BlobStoreError:
        photo_list = []
    except Exception:
        app_logger.error("Unexpected error listing photos", activity_key=key)
        raise

    return flask.render_template(
        template,
        user_profile=ds.profile(user_id),
        form=form,
        db_entity=db_entity,
        symptoms=ds.list_symptoms(user_id),
        exercises=ds.list_exercises(user_id),
        laps=ds.list_laps(user_id),
        key=key,
        is_mobile=flask.session.get(COOKIE_MOBILE),
        recordings_metadata=recordings_metadata,
        photo_list=photo_list,
    )


@flask_app.route("/app/activities/<key>/update-all", methods=["GET", "POST"])
def update_activity(key):
    return _update_activity(key=key, template="activity-update-all.html")


@flask_app.route("/app/activities/<key>/update-sick", methods=["GET", "POST"])
def update_activity_sick(key):
    return _update_activity(key=key, template="activity-update.html")


@flask_app.route("/app/activities/<key>/clone-to-new", methods=["GET", "POST"])
def clone_to_new_activity(key):
    user_id = flask.session.get(COOKIE_USER)
    if not user_id:
        return flask.redirect(flask.url_for("login"))

    user_profile = ds.profile(user_id)

    db_entity = ds.get_activity(
        user_id=user_id, dataset_name=user_profile.dataset_name, key=key
    )

    if flask.request.method == "GET":
        new_entity = copy.deepcopy(db_entity)

        new_entity.key = ds.create_key()

        ds.create_activity(
            user_id=user_id,
            dataset_name=user_profile.dataset_name,
            entity=new_entity,
        )

        flask.flash(message="Activity cloned to date range", category="success")
        return flask.redirect(flask.url_for("update_activity", key=new_entity.key))

    # else
    flask.flash(message="Activity update error - unsupported method", category="error")
    return flask.redirect(flask.url_for("home"))


@flask_app.route("/app/activities/<key>/extend-to-range", methods=["GET", "POST"])
def extend_to_date_range(key):
    user_id = flask.session.get(COOKIE_USER)
    if not user_id:
        return flask.redirect(flask.url_for("login"))

    db_entity = ds.get_activity(
        user_id=user_id, dataset_name=ds.profile(user_id).dataset_name, key=key
    )

    form = forms.ExtendToDateRangeActivityForm()

    if flask.request.method == "GET":
        form.from_year.data = db_entity.when_year
        form.from_month.data = db_entity.when_month
        form.from_day.data = db_entity.when_day

        form.to_year.data = db_entity.when_year
        form.to_month.data = db_entity.when_month
        form.to_day.data = db_entity.when_day

        return flask.render_template(
            "activity-extend-date-range.html",
            user_profile=ds.profile(user_id),
            form=form,
            key=key,
        )

    elif flask.request.method == "POST":
        if form.validate_on_submit():
            start_date = datetime.date(
                year=form.from_year.data,
                month=form.from_month.data,
                day=form.from_day.data,
            )
            end_date = datetime.date(
                year=form.to_year.data, month=form.to_month.data, day=form.to_day.data
            )

            if start_date > end_date:
                flask.flash(
                    message="Activity update error - end date before start date",
                    category="error",
                )
                return flask.redirect(flask.url_for("home"))

            current_date = start_date + datetime.timedelta(days=1)
            while current_date <= end_date:
                new_entity = copy.deepcopy(db_entity)

                new_entity.key = ""
                new_entity.when_year = current_date.year
                new_entity.when_month = current_date.month
                new_entity.when_day = current_date.day

                ds.create_activity(
                    user_id=user_id,
                    dataset_name=ds.profile(user_id).dataset_name,
                    entity=new_entity,
                )

                current_date += datetime.timedelta(days=1)

            flask.flash(message="Activity cloned to date range", category="success")
            return flask.redirect(flask.url_for("home"))

        flask.flash(
            message="Activity update error - unable to validate the form",
            category="error",
        )

    else:
        flask.flash(
            message=(
                f"Activity update error - unsupported method: {flask.request.method}"
            ),
            category="error",
        )

    return flask.redirect(flask.url_for("home"))


@flask_app.route("/app/activities/<key>/exercises/<index>", methods=["GET", "POST"])
def update_exercise(key, index):
    user_id = flask.session.get(COOKIE_USER)
    if not user_id:
        return flask.redirect(flask.url_for("login"))

    app_logger.info(f"Update exercise in activity: {key}[{index}]")

    index = _parse_positive_int_param(index)

    if flask.request.method == "POST":
        form = forms.UpdateActivityExerciseForm()
        form.activity_key.data = key
        if form.series.data == 0 and form.repetitions.data > 0:
            form.series.data = 1
        if form.validate_on_submit():
            entity = ds.get_activity(
                user_id=user_id, dataset_name=ds.profile(user_id).dataset_name, key=key
            )
            if len(entity.exercises) >= index:
                exercise_entity = entity.exercises[index - 1]
                exercise_entity.name = form.exercise_name.data
                exercise_entity.weight = form.weight.data
                exercise_entity.series = form.series.data
                exercise_entity.repetitions = form.repetitions.data
                exercise_entity.duration = form.duration.data
                exercise_entity.rest = form.rest.data
                ds.update_activity(
                    user_id=user_id,
                    dataset_name=ds.profile(user_id).dataset_name,
                    entity=entity,
                )

                flask.flash(message="Exercise updated", category="success")
                return flask.redirect(flask.url_for("update_activity", key=key))
            else:
                flask.flash(
                    message="Exercise edit error - out of index", category="error"
                )
                return flask.redirect(flask.url_for("home"))
        else:
            flask.flash(
                message="Exercise edit error - form validation error", category="error"
            )
            return flask.redirect(flask.url_for("home"))

    elif flask.request.method == "GET":
        entity = ds.get_activity(
            user_id=user_id, dataset_name=ds.profile(user_id).dataset_name, key=key
        )
        if len(entity.exercises) >= index:
            exercise_entity = entity.exercises[index - 1]
            default_exercise = exercise_entity.name

            form = forms.UpdateActivityExerciseForm()
            form.exercise_name.choices = [
                (e.key, e.name)
                for e in ds.list_exercises(user_id).exercise_by_key.values()
            ]
            form.exercise_name.default = (
                default_exercise
                or ds.list_exercises(user_id).default_exercise().key
                or ""
            )
            form.exercise_name.process(form.exercise_name.default)
            form.weight.data = exercise_entity.weight
            form.repetitions.data = exercise_entity.repetitions
            form.series.data = exercise_entity.series
            form.duration.data = exercise_entity.duration
            form.rest.data = exercise_entity.rest
        else:
            flask.flash(message="Exercise edit error - out of index", category="error")
            return flask.redirect(flask.url_for("home"))

        return flask.render_template(
            "exercise-update.html",
            user_profile=ds.profile(user_id),
            key=key,
            index=index,
            form=form,
            exercises=ds.list_exercises(user_id),
        )

    else:
        flask.flash(
            message="Exercise edit error - unsupported method", category="error"
        )
        return flask.redirect(flask.url_for("home"))


@flask_app.route(
    "/app/activities/<key>/exercises/<index>/delete", methods=["GET", "POST"]
)
def delete_exercise(key, index):
    user_id = flask.session.get(COOKIE_USER)
    if not user_id:
        return flask.redirect(flask.url_for("login"))
    user_profile = ds.profile(user_id)

    app_logger.debug(f"Delete exercise {key} {index}")

    form = forms.DeleteActivityForm()

    if flask.request.method == "POST":
        if form.validate_on_submit():
            entity = ds.get_activity(
                user_id=user_id, dataset_name=user_profile.dataset_name, key=key
            )
            index = _parse_positive_int_param(index)
            if len(entity.exercises) >= index:
                entity.exercises.pop(index - 1)
                ds.update_activity(
                    user_id=user_id,
                    dataset_name=user_profile.dataset_name,
                    entity=entity,
                )

            flask.flash(message="Exercise deleted", category="success")
            return flask.redirect(flask.url_for("update_activity", key=key))

        flask.flash(message="Exercise delete error", category="error")

    return flask.render_template(
        "exercise-delete.html",
        user_profile=user_profile,
        key=key,
        index=index,
        form=form,
        name=ds.get_activity(
            user_id=user_id, dataset_name=user_profile.dataset_name, key=key
        )
        .exercises[int(index) - 1]
        .name,
    )


@flask_app.route("/app/activities/<key>/symptoms/<index>", methods=["GET", "POST"])
def update_symptom(key, index):
    user_id = flask.session.get(COOKIE_USER)
    if not user_id:
        return flask.redirect(flask.url_for("login"))
    user_profile = ds.profile(user_id)

    app_logger.debug(f"Update symptom: {key}[{index}]")

    index = _parse_positive_int_param(index)

    if flask.request.method == "POST":
        form = forms.UpdateActivitySymptomForm()
        form.activity_key.data = key
        if form.validate_on_submit():
            entity = ds.get_activity(
                user_id=user_id, dataset_name=user_profile.dataset_name, key=key
            )
            if len(entity.sickness_symptoms) >= index:
                symptom_entity = entity.sickness_symptoms[index - 1]
                symptom_entity.symptom = form.symptom.data
                symptom_entity.side = form.side.data
                symptom_entity.body_part = form.body_part.data
                symptom_entity.health = form.health.data
                ds.update_activity(
                    user_id=user_id,
                    dataset_name=user_profile.dataset_name,
                    entity=entity,
                )

                flask.flash(message="Symptom updated", category="success")
                return flask.redirect(flask.url_for("update_activity", key=key))
            else:
                flask.flash(
                    message="Symptom edit error - out of index", category="error"
                )
                return flask.redirect(flask.url_for("home"))
        else:
            flask.flash(
                message="Symptom edit error - form validation error", category="error"
            )
            return flask.redirect(flask.url_for("home"))

    elif flask.request.method == "GET":
        entity = ds.get_activity(
            user_id=user_id, dataset_name=user_profile.dataset_name, key=key
        )
        if len(entity.sickness_symptoms) >= index:
            symptom_entity = entity.sickness_symptoms[index - 1]
            default_symptom = symptom_entity.symptom

            form = forms.UpdateActivitySymptomForm()

            form.symptom.choices = [
                (s.key, s.name)
                for s in ds.list_symptoms(user_id).symptoms_by_key.values()
            ]
            form.symptom.default = (
                default_symptom or ds.list_symptoms(user_id).default_symptom().key
            )
            form.symptom.process(form.symptom.default)
            form.side.data = symptom_entity.side
            form.body_part.data = symptom_entity.body_part
            form.health.data = symptom_entity.health
        else:
            flask.flash(message="Symptom edit error - out of index", category="error")
            return flask.redirect(flask.url_for("home"))

        return flask.render_template(
            "symptom-update.html",
            user_profile=user_profile,
            key=key,
            index=index,
            form=form,
        )

    else:
        flask.flash(message="Symptom edit error - unsupported method", category="error")
        return flask.redirect(flask.url_for("home"))


@flask_app.route(
    "/app/activities/<key>/symptoms/<index>/delete", methods=["GET", "POST"]
)
def delete_symptom(key, index):
    user_id = flask.session.get(COOKIE_USER)
    if not user_id:
        return flask.redirect(flask.url_for("login"))
    user_profile = ds.profile(user_id)

    app_logger.debug(f"Delete symptom {key} {index}")

    form = forms.DeleteActivityForm()

    if flask.request.method == "POST":
        if form.validate_on_submit():
            entity = ds.get_activity(
                user_id=user_id, dataset_name=user_profile.dataset_name, key=key
            )
            index = _parse_positive_int_param(index)
            if len(entity.sickness_symptoms) >= index:
                entity.sickness_symptoms.pop(index - 1)
                ds.update_activity(
                    user_id=user_id,
                    dataset_name=user_profile.dataset_name,
                    entity=entity,
                )

            flask.flash(message="Symptom deleted", category="success")
            return flask.redirect(flask.url_for("update_activity", key=key))

        flask.flash(message="Symptom delete error", category="error")

    return flask.render_template(
        "symptom-delete.html",
        user_profile=user_profile,
        key=key,
        index=index,
        form=form,
        name=ds.get_activity(
            user_id=user_id, dataset_name=user_profile.dataset_name, key=key
        )
        .sickness_symptoms[int(index) - 1]
        .symptom,
    )


@flask_app.route("/app/activities/<key>/delete", methods=["GET", "POST"])
def delete_activity(key):
    user_id = flask.session.get(COOKIE_USER)
    if not user_id:
        return flask.redirect(flask.url_for("login"))
    user_profile = ds.profile(user_id)

    form = forms.DeleteActivityForm()

    if flask.request.method == "POST":
        if form.validate_on_submit():
            db_entity = ds.get_activity(
                user_id=user_id, dataset_name=user_profile.dataset_name, key=key
            )
            _blob_service().delete_all_activity_blobs(user_id=user_id, activity_key=key)
            ds.delete_activity(
                user_id=user_id, dataset_name=user_profile.dataset_name, key=key
            )

            flask.flash(message="Activity deleted", category="success")
            return flask.redirect(
                flask.url_for(
                    "list_activities_for_date",
                    year=db_entity.when_year,
                    month=db_entity.when_month,
                    day=db_entity.when_day,
                )
            )

        flask.flash(message="Activity delete error", category="error")

    return flask.render_template(
        "activity-delete.html",
        user_profile=user_profile,
        key=key,
        form=form,
        name=ds.get_activity(
            user_id=user_id, dataset_name=user_profile.dataset_name, key=key
        ).name,
    )


@flask_app.route("/app/activities/<key>", methods=["GET"])
def get_activity(key):
    user_id = flask.session.get(COOKIE_USER)
    if not user_id:
        return flask.redirect(flask.url_for("login"))
    user_profile = ds.profile(user_id)

    dataset_name = user_profile.dataset_name
    a = ds.get_activity(user_id=user_id, dataset_name=dataset_name, key=key)

    week_day = cals.WEEKDAY_INDEX_2_STR.get(
        calendar.weekday(a.when_year, a.when_month, a.when_day), ""
    )

    blob_svc = _blob_service()
    # recordings
    try:
        recordings_metadata = []
        for entry in a.recorded_blob_keys:
            entry_uuid = entities_mod.recording_blob_uuid(entry)
            meta = blob_svc.get_recording(
                user_id=user_id, activity_key=key, blob_key=entry_uuid
            )
            if meta:
                recordings_metadata.append(
                    {
                        "blob_uuid": entry_uuid,
                        "ext": entities_mod.recording_ext(entry),
                        "name": meta.name,
                        "original_file_name": meta.original_file_name,
                        "size_bytes": meta.size_bytes,
                        "description": meta.description,
                        "has_parquet": entry_uuid in a.recorded_parquet_keys,
                    }
                )
    except Exception:
        app_logger.error(
            "Unexpected error fetching recordings metadata", activity_key=key
        )
        recordings_metadata = []
    # photos
    try:
        photo_list = blob_svc.list_photos(user_id=user_id, activity_key=key)
    except blob_pkg.BlobStoreError:
        photo_list = []
    except Exception:
        app_logger.error("Unexpected error listing photos", activity_key=key)
        raise

    activity_map_data = _activity_map_data(
        user_id=user_id,
        activity=a,
        blob_svc=blob_svc,
        include_detail=True,
    )

    (prev_year, prev_month, prev_day) = cals.get_yesterday(
        a.when_year, a.when_month, a.when_day
    )
    (next_year, next_month, next_day) = cals.get_tomorrow(
        a.when_year, a.when_month, a.when_day
    )

    # FROM is used to pass basic in
    form = forms.EmptyForm()

    return flask.render_template(
        "activity-get.html",
        user_profile=user_profile,
        activity_entity=a,
        symptoms=ds.list_symptoms(user_id, dataset_name=dataset_name),
        exercises=ds.list_exercises(user_id, dataset_name=dataset_name),
        laps=ds.list_laps(user_id, dataset_name=dataset_name),
        activity_types=ds.list_activity_types(user_id=user_id),
        gear=ds.list_gear(user_id=user_id, dataset_name=user_profile.dataset_name),
        outfits=ds.list_outfits(user_id=user_id),
        week_day=week_day,
        recordings_metadata=recordings_metadata,
        photo_list=photo_list,
        prev_year=prev_year,
        prev_month=prev_month,
        prev_day=prev_day,
        next_year=next_year,
        next_month=next_month,
        next_day=next_day,
        activity_map_data=activity_map_data,
        form=form,
    )


@flask_app.route("/app/activities/<key>/analysis", methods=["GET"])
def get_activity_analysis(key):
    user_id = flask.session.get(COOKIE_USER)
    if not user_id:
        return flask.redirect(flask.url_for("login"))
    user_profile = ds.profile(user_id)

    dataset_name = user_profile.dataset_name
    a = ds.get_activity(user_id=user_id, dataset_name=dataset_name, key=key)

    blob_svc = _blob_service()

    # build recordings metadata list for the selector
    recordings_metadata = []
    for entry in a.recorded_blob_keys:
        entry_uuid = entities_mod.recording_blob_uuid(entry)
        meta = blob_svc.get_recording(
            user_id=user_id, activity_key=key, blob_key=entry_uuid
        )
        if meta:
            recordings_metadata.append(
                {
                    "blob_uuid": entry_uuid,
                    "ext": entities_mod.recording_ext(entry),
                    "name": meta.name,
                    "original_file_name": meta.original_file_name,
                    "has_parquet": entry_uuid in a.recorded_parquet_keys,
                }
            )

    # select the recording to analyse (default to first recording in the list)
    selected_blob_uuid = flask.request.args.get("blob_uuid")
    if not selected_blob_uuid and recordings_metadata:
        selected_blob_uuid = recordings_metadata[0]["blob_uuid"]

    fit_chart_script, fit_chart_div = None, None
    fit_ridge_script, fit_ridge_div = None, None
    hr_zones_script, hr_zones_div = None, None
    cadence_hist_script, cadence_hist_div = None, None
    power_zones_script, power_zones_div = None, None
    power_curve_script, power_curve_div = None, None
    power_ts_script, power_ts_div = None, None
    hr_ts_script, hr_ts_div = None, None
    speed_cadence_ts_script, speed_cadence_ts_div = None, None
    parquet_available = False

    if selected_blob_uuid and selected_blob_uuid in a.recorded_parquet_keys:
        try:
            from mytral.recordings import parquet_converter as parquet_converter_mod

            result_pair = blob_svc.open_parquet(
                user_id=user_id,
                activity_key=key,
                source_blob_key=selected_blob_uuid,
            )
            if result_pair is not None:
                parquet_stream, _ = result_pair
                parquet_bytes = parquet_stream.read()
                recording = parquet_converter_mod.load_parquet(parquet_bytes)
                parquet_available = True

                # load all activities for FTP estimation
                all_activities = list(
                    ds.all_activities(
                        user_id=user_id, dataset_name=dataset_name
                    ).values()
                )

                am_module.resolve(
                    athlete_metrics=user_profile.athlete_metrics,
                    user_profile=user_profile,
                    activities=all_activities,
                    weight_kg=0.0,
                )
                (
                    result,
                    ridge_result,
                    hr_zones_result,
                    cadence_hist_result,
                    power_zones_result,
                    power_curve_result,
                    power_ts_result,
                    hr_ts_result,
                    speed_cadence_ts_result,
                ) = charts.activity_fit_charts(
                    recording,
                    athlete_metrics=user_profile.athlete_metrics,
                )
                if result is not None:
                    fit_chart_script, fit_chart_div = result
                if ridge_result is not None:
                    fit_ridge_script, fit_ridge_div = ridge_result
                if hr_zones_result is not None:
                    hr_zones_script, hr_zones_div = hr_zones_result
                if cadence_hist_result is not None:
                    cadence_hist_script, cadence_hist_div = cadence_hist_result
                if power_zones_result is not None:
                    power_zones_script, power_zones_div = power_zones_result
                if power_curve_result is not None:
                    power_curve_script, power_curve_div = power_curve_result
                if power_ts_result is not None:
                    power_ts_script, power_ts_div = power_ts_result
                if hr_ts_result is not None:
                    hr_ts_script, hr_ts_div = hr_ts_result
                if speed_cadence_ts_result is not None:
                    speed_cadence_ts_script, speed_cadence_ts_div = (
                        speed_cadence_ts_result
                    )
        except Exception:
            app_logger.error("Failed to render recording chart", activity_key=key)

    return flask.render_template(
        "activity-analysis.html",
        user_profile=user_profile,
        activity_entity=a,
        activity_types=ds.list_activity_types(user_id=user_id),
        recordings_metadata=recordings_metadata,
        selected_blob_uuid=selected_blob_uuid,
        parquet_available=parquet_available,
        fit_chart_script=fit_chart_script,
        fit_chart_div=fit_chart_div,
        fit_ridge_script=fit_ridge_script,
        fit_ridge_div=fit_ridge_div,
        hr_zones_script=hr_zones_script,
        hr_zones_div=hr_zones_div,
        cadence_hist_script=cadence_hist_script,
        cadence_hist_div=cadence_hist_div,
        power_zones_script=power_zones_script,
        power_zones_div=power_zones_div,
        power_curve_script=power_curve_script,
        power_curve_div=power_curve_div,
        power_ts_script=power_ts_script,
        power_ts_div=power_ts_div,
        hr_ts_script=hr_ts_script,
        hr_ts_div=hr_ts_div,
        speed_cadence_ts_script=speed_cadence_ts_script,
        speed_cadence_ts_div=speed_cadence_ts_div,
    )


@flask_app.route("/activities/year/<year>")
def list_activities_year(year):
    user_id = flask.session.get(COOKIE_USER)
    if not user_id:
        return flask.redirect(flask.url_for("login"))
    user_profile = ds.profile(user_id)

    # redirect to valid year
    try:
        year_int = int(year)
    except ValueError:
        flask.abort(400)

    if not year_int:
        year_int = ds.activities_stats(
            user_id=user_id,
            dataset_name=user_profile.dataset_name,
            include_meta=True,
        ).year_max
        if year_int:
            return flask.redirect(f"/activities/year/{year_int}")
        else:
            return flask.redirect(flask.url_for("home"))

    # load only activities for given year
    activities = ds.list_activities(
        user_id=user_id,
        dataset_name=user_profile.dataset_name,
        filter_year=year_int,
        skip_future=True,
        sort_by_when=True,
    )

    # get filter parameters from query string
    filter_activity_type = flask.request.args.get("activity_type", "")
    filter_gear = flask.request.args.get("gear", "")
    filter_intensity = flask.request.args.get("intensity", "")
    filter_type = flask.request.args.get("type", "")
    filter_source = flask.request.args.get("source", "")
    aspect = flask.request.args.get("aspect", "feed")

    # apply filters
    if filter_activity_type:
        activities = [
            a for a in activities if a.activity_type_key == filter_activity_type
        ]
    if filter_gear:
        activities = [
            a
            for a in activities
            if filter_gear
            in (a.gears if hasattr(a, "gears") else ([a.gear] if a.gear else []))
        ]
    if filter_intensity:
        activities = [a for a in activities if a.intensity == filter_intensity]
    if filter_type:
        if filter_type == "commute":
            activities = [a for a in activities if a.commute]
        elif filter_type == "warm-up":
            activities = [a for a in activities if a.warm_up]
        elif filter_type == "cool-down":
            activities = [a for a in activities if a.cool_down]
        elif filter_type == "race":
            activities = [a for a in activities if a.race]
        elif filter_type == "ranked":
            activities = [a for a in activities if a.ranked]
    if filter_source:
        activities = [a for a in activities if a.src == filter_source]

    # get sort parameters
    sort_by = flask.request.args.get("sort", "when")
    sort_order = flask.request.args.get("order", "desc")

    # apply sorting
    match sort_by:
        case "name":
            activities = sorted(activities, key=lambda a: a.name or "")
        case "gear":
            activities = sorted(
                activities,
                key=lambda a: (
                    ",".join(a.gears) if hasattr(a, "gears") else (a.gear or "")
                ),
            )
        case "activity_type":
            activities = sorted(activities, key=lambda a: a.activity_type_key or "")
        case "duration":
            activities = sorted(
                activities, key=lambda a: a.hours * 3600 + a.minutes * 60 + a.seconds
            )
        case "distance":
            activities = sorted(activities, key=lambda a: a.distance)
        case "elevation":
            activities = sorted(activities, key=lambda a: a.elevation_gain)
        case "pace":
            activities = sorted(activities, key=lambda a: a.pace or "99:99")
        case "source":
            activities = sorted(activities, key=lambda a: a.src or "")
        case _:
            activities = sorted(
                activities,
                key=lambda a: (a.when_year, a.when_month, a.when_day, a.sort_code),
            )

    if sort_order == "asc":
        activities = list(activities)
    else:
        activities = list(reversed(activities))

    if flask.request.headers.get("Accept") == "application/json":
        # return JSON data
        return flask.jsonify([dataclasses.asdict(a) for a in activities])

    activities_weekdays = {
        a.key: cals.WEEKDAY_INDEX_2_STR.get(
            calendar.weekday(a.when_year, a.when_month, a.when_day), ""
        )
        for a in activities
    }

    # age at year calculation
    age_at_year = (
        cals.get_age_at(
            born_year=user_profile.born_year,
            born_month=user_profile.born_month,
            born_day=user_profile.born_day,
            year=int(year),
        )
        if year
        else 0
    )

    # get unique values for filter dropdowns
    all_activities = ds.list_activities(
        user_id=user_id,
        dataset_name=user_profile.dataset_name,
        filter_year=int(year),
        skip_future=True,
    )
    unique_activity_types = sorted(
        set(a.activity_type_key for a in all_activities if a.activity_type_key)
    )
    unique_intensities = sorted(set(a.intensity for a in all_activities if a.intensity))
    unique_sources = sorted(set(a.src for a in all_activities if a.src))

    # calculate year statistics for the cards
    year_total_distance = sum(a.distance for a in activities if a.distance)
    year_total_duration_seconds = sum(
        a.duration_seconds for a in activities if a.duration_seconds
    )
    year_total_cost = sum(a.cost for a in activities if a.cost)

    # find fastest activity (best pace)
    year_fastest_activity = None
    year_fastest_pace = float("inf")
    for a in activities:
        if a.distance > 0 and a.duration_seconds > 0:
            pace = a.duration_seconds / (a.distance / 1000)  # seconds per km
            if pace < year_fastest_pace:
                year_fastest_pace = pace
                year_fastest_activity = a

    # find longest activity by distance
    year_longest_activity = (
        max(activities, key=lambda x: x.distance, default=None) if activities else None
    )

    # find most intense activity (by heart rate or watts)
    year_most_intense_activity = None
    year_highest_intensity = 0
    for a in activities:
        intensity_score = max(a.avg_hr or 0, (a.avg_watts or 0) / 10)  # normalize watts
        if intensity_score > year_highest_intensity:
            year_highest_intensity = intensity_score
            year_most_intense_activity = a

    # find activity with most elevation gain
    year_highest_elevation_activity = (
        max(activities, key=lambda x: x.elevation_gain, default=None)
        if activities
        else None
    )

    activity_maps: dict[str, dict] = {}
    if aspect == "feed":
        blob_svc = _blob_service()
        for activity in activities:
            payload = _activity_map_data(
                user_id=user_id,
                activity=activity,
                blob_svc=blob_svc,
                include_detail=False,
            )
            if payload is not None:
                activity_maps[activity.key] = payload

    return flask.render_template(
        "activity-list-year.html",
        user_profile=user_profile,
        activities=activities,
        activity_types=ds.list_activity_types(user_id=user_id),
        activities_weekdays=activities_weekdays,
        gear=ds.list_gear(user_id=user_id, dataset_name=user_profile.dataset_name),
        stats=ds.activities_stats(
            user_id=user_id, dataset_name=user_profile.dataset_name
        ),
        year=int(year),
        years=list(
            reversed(
                [
                    y
                    for y in range(
                        user_profile.born_year,
                        datetime.date.today().year + 1,
                    )
                ]
            )
        ),
        age_at_year=age_at_year,
        current_year=datetime.date.today().year,
        is_mobile=flask.session.get(COOKIE_MOBILE),
        unique_activity_types=unique_activity_types,
        unique_intensities=unique_intensities,
        unique_sources=unique_sources,
        filter_activity_type=filter_activity_type,
        filter_gear=filter_gear,
        filter_intensity=filter_intensity,
        filter_type=filter_type,
        filter_source=filter_source,
        sort_by=sort_by,
        sort_order=sort_order,
        aspect=aspect,
        # year statistics
        year_total_distance=year_total_distance,
        year_total_duration_seconds=year_total_duration_seconds,
        year_total_cost=year_total_cost,
        year_fastest_activity=year_fastest_activity,
        year_longest_activity=year_longest_activity,
        year_most_intense_activity=year_most_intense_activity,
        year_highest_elevation_activity=year_highest_elevation_activity,
        activity_maps=activity_maps,
    )


@flask_app.route("/activities/search")
def search_activities():
    user_id = flask.session.get(COOKIE_USER)
    if not user_id:
        return flask.redirect(flask.url_for("login"))

    q = flask.request.args.get("q", "").strip()
    if not q:
        return flask.redirect(flask.url_for("home"))

    user_profile = ds.profile(user_id)

    # load all activities across all years
    activities = ds.list_activities(
        user_id=user_id,
        dataset_name=user_profile.dataset_name,
        skip_future=True,
        sort_by_when=True,
    )

    # filter by case-insensitive substring match on name and description
    q_lower = q.lower()
    activities = [
        a
        for a in activities
        if q_lower in (a.name or "").lower() or q_lower in (a.description or "").lower()
    ]

    activities_weekdays = {
        a.key: cals.WEEKDAY_INDEX_2_STR.get(
            calendar.weekday(a.when_year, a.when_month, a.when_day), ""
        )
        for a in activities
    }

    return flask.render_template(
        "search-results.html",
        user_profile=user_profile,
        activities=activities,
        activities_weekdays=activities_weekdays,
        activity_types=ds.list_activity_types(user_id=user_id),
        gear=ds.list_gear(user_id=user_id, dataset_name=user_profile.dataset_name),
        is_mobile=flask.session.get(COOKIE_MOBILE),
        q=q,
    )


@flask_app.route("/activities/descriptions")
def list_activities_diary():
    user_id = flask.session.get(COOKIE_USER)
    if not user_id:
        return flask.redirect(flask.url_for("login"))
    user_profile = ds.profile(user_id)

    activities = ds.list_activities(
        user_id=user_id,
        dataset_name=user_profile.dataset_name,
        sort_by_when=True,
    )
    activity_types = ds.list_activity_types(user_id=user_id)
    diary_activities = []
    for a in activities:
        if a.description and activity_types.is_meta(a.activity_type_key):
            diary_activities.append(a)

    if diary_activities:
        activities_weekdays = {
            a.key: cals.WEEKDAY_INDEX_2_STR.get(
                calendar.weekday(a.when_year, a.when_month, a.when_day), ""
            )
            for a in diary_activities
        }

        return flask.render_template(
            "activity-list-diary.html",
            user_profile=user_profile,
            activities=diary_activities,
            activities_weekdays=activities_weekdays,
            activity_types=activity_types,
            is_diary=True,
            is_mobile=flask.session.get(COOKIE_MOBILE),
        )

    return flask.redirect(flask.url_for("home"))


@flask_app.route("/activities/prs")
def list_activities_prs():
    user_id = flask.session.get(COOKIE_USER)
    if not user_id:
        return flask.redirect(flask.url_for("login"))
    user_profile = ds.profile(user_id)

    activities = ds.list_activities(
        user_id=user_id,
        dataset_name=user_profile.dataset_name,
        sort_by_when=True,
    )
    activity_types = ds.list_activity_types(user_id=user_id)

    # get filter parameters from query string
    filter_activity_type = flask.request.args.get("activity_type", "")

    # detect time-trial lap names: fixed duration, varying distance (e.g. "30'")
    # these need different grouping: best = max distance for a given duration
    lap_defs = ds.list_laps(
        user_id=user_id, dataset_name=ds.profile(user_id).dataset_name
    )
    time_trial_lap_names = {
        lap.name
        for lap in lap_defs.lap_by_key.values()
        if lap.default_duration > 0 and lap.default_distance == 0
    }

    # build a unified list of PR entries from ranked activities and ranked laps
    # each entry:
    #   activity type, distance (m), duration (s), when, weekday, key, name, is_lap
    pr_entries = []
    for a in activities:
        weekday = cals.WEEKDAY_INDEX_2_STR.get(
            calendar.weekday(a.when_year, a.when_month, a.when_day), ""
        )
        # ranked activity
        if a.ranked:
            if not filter_activity_type or a.activity_type_key == filter_activity_type:
                pr_entries.append(
                    {
                        "activity_type": a.activity_type_key,
                        "distance": a.distance or 0,
                        "duration": a.hours * 3_600 + a.minutes * 60 + a.seconds,
                        "when": a.when,
                        "weekday": weekday,
                        "key": a.key,
                        "name": a.name,
                        "is_lap": False,
                    }
                )
        # ranked laps within this activity
        for lap in a.laps or []:
            if lap.ranked:
                if (
                    not filter_activity_type
                    or a.activity_type_key == filter_activity_type
                ):
                    pr_entries.append(
                        {
                            "activity_type": a.activity_type_key,
                            "distance": lap.distance or 0,
                            "duration": lap.duration or 0,
                            "when": a.when,
                            "weekday": weekday,
                            "key": a.key,
                            "name": lap.name,
                            "is_lap": True,
                        }
                    )

    if not pr_entries:
        return flask.redirect(flask.url_for("home"))

    # group by activity type; within each activity_type_key handle two kinds of events:
    #   distance-based: fixed distance, varying duration → best = min duration
    #   time-trial:     fixed duration, varying distance → best = max distance
    unique_activity_types = sorted(set(e["activity_type"] for e in pr_entries))
    prs_by_activity_type = {}
    for sport in unique_activity_types:
        sport_entries = [e for e in pr_entries if e["activity_type"] == sport]

        # split by event kind: time-trial laps have fixed duration, varying distance
        def _is_time_trial(e: dict) -> bool:
            return e["is_lap"] and e["name"] in time_trial_lap_names

        time_entries = [e for e in sport_entries if _is_time_trial(e)]
        dist_entries = [e for e in sport_entries if not _is_time_trial(e)]

        # distance-based:
        # sort by (name, distance asc, duration asc); best = fastest per name/distance
        dist_entries.sort(key=lambda e: (e["name"], e["distance"], e["duration"]))
        seen_dist: set = set()
        for entry in dist_entries:
            dist_key = (entry["name"], entry["distance"])
            entry["is_best"] = dist_key not in seen_dist
            seen_dist.add(dist_key)

        # time-trial:
        # sort by (name, duration asc, distance desc); best = longest per name/duration
        time_entries.sort(key=lambda e: (e["name"], e["duration"], -e["distance"]))
        seen_time: set = set()
        for entry in time_entries:
            time_key = (entry["name"], entry["duration"])
            entry["is_best"] = time_key not in seen_time
            seen_time.add(time_key)

        prs_by_activity_type[sport] = time_entries + dist_entries

    return flask.render_template(
        "activity-list-prs.html",
        user_profile=user_profile,
        activity_types=activity_types,
        unique_activity_types=unique_activity_types,
        filter_activity_type=filter_activity_type,
        prs_by_activity_type=prs_by_activity_type,
        is_mobile=flask.session.get(COOKIE_MOBILE),
    )


@flask_app.route("/activities/paces")
def list_activities_paces():
    user_id = flask.session.get(COOKIE_USER)
    if not user_id:
        return flask.redirect(flask.url_for("login"))
    user_profile = ds.profile(user_id)

    # get filter parameters from query string
    filter_activity_type = flask.request.args.get("activity_type", "")
    filter_year = flask.request.args.get("year", "")

    activities = ds.list_activities(
        user_id=user_id,
        dataset_name=user_profile.dataset_name,
        sort_by_when=True,
        filter_year=int(filter_year) if filter_year else None,
    )
    activity_types = ds.list_activity_types(user_id=user_id)

    # get unique activity_types from all distance/endurance activities
    unique_activity_types = sorted(
        set(
            a.activity_type_key
            for a in activities
            if not activity_types.is_meta(a.activity_type_key) and a.distance
        )
    )

    # get available years
    all_activities = ds.list_activities(
        user_id=user_id,
        dataset_name=user_profile.dataset_name,
        sort_by_when=True,
    )
    years = sorted(
        set(
            a.when_year
            for a in all_activities
            if not activity_types.is_meta(a.activity_type_key) and a.distance
        ),
        reverse=True,
    )

    # generate pace chart
    chart_script, chart_div = charts.activity_paces_by_distance(
        activities=activities,
        activity_types=activity_types,
        filter_activity_type=filter_activity_type,
        is_mobile_view=flask.session.get(COOKIE_MOBILE),
    )

    return flask.render_template(
        "activity-paces.html",
        user_profile=user_profile,
        activity_types=activity_types,
        unique_activity_types=unique_activity_types,
        filter_activity_type=filter_activity_type,
        filter_year=filter_year,
        years=years,
        chart_script=chart_script,
        chart_div=chart_div,
        is_mobile=flask.session.get(COOKIE_MOBILE),
    )


@flask_app.route("/activities/races")
def list_activities_races():
    user_id = flask.session.get(COOKIE_USER)
    if not user_id:
        return flask.redirect(flask.url_for("login"))
    user_profile = ds.profile(user_id)

    activities = ds.list_activities(
        user_id=user_id,
        dataset_name=user_profile.dataset_name,
        sort_by_when=True,
    )
    activity_types = ds.list_activity_types(user_id=user_id)

    # get filter parameters from query string
    filter_activity_type = flask.request.args.get("activity_type", "")

    # map: activity_type_key -> [activities ordered by duration seconds]
    race_activities_by_activity_type = {}
    race_activities = []
    for a in activities:
        if a.race:
            # apply activity_type_key filter if specified
            if filter_activity_type and a.activity_type_key != filter_activity_type:
                continue
            race_activities.append(a)
            if a.activity_type_key not in race_activities_by_activity_type:
                race_activities_by_activity_type[a.activity_type_key] = []
            race_activities_by_activity_type[a.activity_type_key].append(a)
    for sport in race_activities_by_activity_type:
        race_activities_by_activity_type[sport].sort(key=lambda x: x.duration_seconds)

    # get unique activity_types from all race activities
    unique_activity_types = sorted(set(a.activity_type_key for a in race_activities))

    # calculate race statistics
    total_races = len(race_activities)
    total_cost = sum(a.cost for a in race_activities if a.cost)
    total_distance = sum(a.distance for a in race_activities if a.distance)
    total_duration_seconds = sum(
        a.duration_seconds for a in race_activities if a.duration_seconds
    )

    # find fastest race (shortest duration with distance > 0)
    fastest_race = None
    fastest_pace = float("inf")
    for a in race_activities:
        if a.distance > 0 and a.duration_seconds > 0:
            pace = a.duration_seconds / (a.distance / 1000)  # seconds per km
            if pace < fastest_pace:
                fastest_pace = pace
                fastest_race = a

    # find longest race by distance
    longest_race = (
        max(race_activities, key=lambda x: x.distance, default=None)
        if race_activities
        else None
    )

    # count races by year
    races_by_year = {}
    for a in race_activities:
        year = a.when_year
        races_by_year[year] = races_by_year.get(year, 0) + 1

    if race_activities_by_activity_type:
        activities_weekdays = {
            a.key: cals.WEEKDAY_INDEX_2_STR.get(
                calendar.weekday(a.when_year, a.when_month, a.when_day), ""
            )
            for a in race_activities
        }

        return flask.render_template(
            "activity-list-races.html",
            user_profile=user_profile,
            activities_by_activity_type=race_activities_by_activity_type,
            activities_weekdays=activities_weekdays,
            activity_types=activity_types,
            unique_activity_types=unique_activity_types,
            filter_activity_type=filter_activity_type,
            is_mobile=flask.session.get(COOKIE_MOBILE),
            # statistics
            total_races=total_races,
            total_cost=total_cost,
            total_distance=total_distance,
            total_duration_seconds=total_duration_seconds,
            fastest_race=fastest_race,
            longest_race=longest_race,
            races_by_year=races_by_year,
            sport_count=len(unique_activity_types),
        )

    return flask.redirect(flask.url_for("home"))


@flask_app.route("/activities/date/<year>/<month>/<day>")
def list_activities_for_date(year, month, day):
    user_id = flask.session.get(COOKIE_USER)
    if not user_id:
        return flask.redirect(flask.url_for("login"))
    user_profile = ds.profile(user_id)

    activities = ds.list_activities(
        user_id=user_id,
        dataset_name=user_profile.dataset_name,
        filter_year=int(year),
        filter_month=int(month),
        filter_day=int(day),
    )

    activities_weekdays = {
        a.key: cals.WEEKDAY_INDEX_2_STR.get(
            calendar.weekday(a.when_year, a.when_month, a.when_day), ""
        )
        for a in activities
    }

    # aggregate muscle groups for day heat-map
    activity_types_registry = ds.list_activity_types(user_id=user_id)
    exercises_registry = ds.list_exercises(
        user_id=user_id,
        dataset_name=ds.profile(user_id).dataset_name,
    )
    muscle_counts: dict[str, int] = {}
    muscle_secondary: set[str] = set()
    for activity in activities:
        # muscles from activity type
        at = activity_types_registry.activity_types_by_key.get(
            activity.activity_type_key
        )
        if at:
            for key in at.muscle_groups or []:
                muscle_counts[key] = muscle_counts.get(key, 0) + 1
            for key in at.muscle_groups_secondary or []:
                muscle_secondary.add(key)
        # muscles from individual exercises inside the activity
        for ex_entity in activity.exercises or []:
            ex = exercises_registry.exercise_by_key.get(
                ex_entity.name
            ) or exercises_registry.exercise_by_name.get(ex_entity.name)
            if ex:
                for key in ex.muscle_groups or []:
                    muscle_counts[key] = muscle_counts.get(key, 0) + 1
                for key in ex.muscle_groups_secondary or []:
                    muscle_secondary.add(key)

    def _intensity_class(count: int) -> str:
        if count >= 10:
            return "state-active intensity-5"
        if count >= 7:
            return "state-active intensity-4"
        if count >= 4:
            return "state-active intensity-3"
        if count >= 2:
            return "state-active intensity-2"
        return "state-active intensity-1"

    # primary muscles: use intensity scale (green); secondary: amber
    # a muscle that appears as both primary and secondary → primary wins
    day_muscle_highlights: dict[str, str] = {}
    for k, v in muscle_counts.items():
        day_muscle_highlights[k] = _intensity_class(v)
    for k in muscle_secondary:
        if k not in day_muscle_highlights:
            day_muscle_highlights[k] = "state-secondary"

    # PREVIOUS / NEXT day navigation
    try:
        (prev_year, prev_month, prev_day) = cals.get_yesterday(
            int(year), int(month), int(day)
        )
    except Exception as ex:
        app_logger.error(f"Unable to get yesterday for given date: {ex}")
        (prev_year, prev_month, prev_day) = (
            cals.FALLBACK_YEAR,
            cals.FALLBACK_MONTH,
            cals.FALLBACK_DAY,
        )

    try:
        (next_year, next_month, next_day) = cals.get_tomorrow(
            int(year), int(month), int(day)
        )
    except Exception as ex:
        app_logger.error(f"Unable to get tomorrow for given date: {ex}")
        (next_year, next_month, next_day) = (
            cals.FALLBACK_YEAR,
            cals.FALLBACK_MONTH,
            cals.FALLBACK_DAY,
        )

    return flask.render_template(
        "day-get.html",
        user_profile=user_profile,
        activities=activities,
        activities_weekdays=activities_weekdays,
        activity_types=activity_types_registry,
        gear=ds.list_gear(user_id=user_id, dataset_name=user_profile.dataset_name),
        stats=ds.activities_stats(
            user_id=user_id,
            dataset_name=user_profile.dataset_name,
            activities=activities,
        ),
        year=year,
        month=month,
        day=day,
        day_muscle_highlights=day_muscle_highlights,
        prev_year=prev_year,
        prev_month=prev_month,
        prev_day=prev_day,
        next_year=next_year,
        next_month=next_month,
        next_day=next_day,
    )


@flask_app.route("/activities/month-day/<month>/<day>")
def list_activities_for_month_day(month, day):
    user_id = flask.session.get(COOKIE_USER)
    if not user_id:
        return flask.redirect(flask.url_for("login"))
    user_profile = ds.profile(user_id)

    activities = ds.list_activities(
        user_id=user_id,
        dataset_name=user_profile.dataset_name,
        filter_month=int(month),
        filter_day=int(day),
        sort_by_when=True,
    )

    # filter only sickness and injury activities
    activities = [a for a in activities if a.activity_type_key in ["sick", "injured"]]

    activities_weekdays = {
        a.key: cals.WEEKDAY_INDEX_2_STR.get(
            calendar.weekday(a.when_year, a.when_month, a.when_day), ""
        )
        for a in activities
    }

    return flask.render_template(
        "activity-list.html",
        user_profile=user_profile,
        activities=activities,
        activities_weekdays=activities_weekdays,
        activity_types=ds.list_activity_types(user_id=user_id),
        gear=ds.list_gear(user_id=user_id, dataset_name=user_profile.dataset_name),
        stats=ds.activities_stats(
            user_id=user_id,
            dataset_name=user_profile.dataset_name,
            activities=activities,
        ),
        month=month,
        day=day,
    )


@flask_app.route("/activities/validation")
def list_activities_validation():
    """List all activities that have data problems (suspicious/invalid values)."""
    user_id = flask.session.get(COOKIE_USER)
    if not user_id:
        return flask.redirect(flask.url_for("login"))
    user_profile = ds.profile(user_id)

    # load all activities for the user across all years
    activities = ds.list_activities(
        user_id=user_id,
        dataset_name=user_profile.dataset_name,
        skip_future=False,
    )

    # validate each activity and collect those with problems
    junkyard: list[tuple[entities_mod.ActivityEntity, list[tuple[str, str]]]] = []
    for a in activities:
        problems = entities_mod.validate_activity(a)
        if problems:
            junkyard.append((a, problems))

    # sort by number of problems descending (most problematic first)
    junkyard.sort(key=lambda item: len(item[1]), reverse=True)

    # compute stats
    total_errors = sum(
        1
        for _, problems in junkyard
        for _, severity in problems
        if severity == entities_mod.SEVERITY_ERROR
    )
    total_warnings = sum(
        1
        for _, problems in junkyard
        for _, severity in problems
        if severity == entities_mod.SEVERITY_WARNING
    )
    total_problems = total_errors + total_warnings
    affected_activities = len(junkyard)

    # compute problem breakdown by category
    # errors come from 2 categories: internal consistency and zero-value anomalies
    internal_errors = sum(
        1
        for _, problems in junkyard
        for msg, severity in problems
        if severity == entities_mod.SEVERITY_ERROR and ">" in msg
    )
    zero_anomalies = sum(
        1
        for _, problems in junkyard
        for msg, severity in problems
        if severity == entities_mod.SEVERITY_ERROR and ">" not in msg
    )
    oor_warnings = total_warnings  # all warnings are out-of-range

    activities_weekdays = {
        a.key: cals.WEEKDAY_INDEX_2_STR.get(
            calendar.weekday(a.when_year, a.when_month, a.when_day), ""
        )
        for a, _ in junkyard
    }

    return flask.render_template(
        "activity-validation.html",
        user_profile=user_profile,
        junkyard=junkyard,
        stats={
            "total_problems": total_problems,
            "total_errors": total_errors,
            "total_warnings": total_warnings,
            "affected_activities": affected_activities,
            "internal_errors": internal_errors,
            "zero_anomalies": zero_anomalies,
            "oor_warnings": oor_warnings,
        },
        activities_weekdays=activities_weekdays,
        activity_types=ds.list_activity_types(user_id=user_id),
        gear=ds.list_gear(user_id=user_id, dataset_name=user_profile.dataset_name),
    )


@flask_app.route("/activities/date/<year>/<month>/<day>/copy", methods=["GET", "POST"])
def copy_day(year, month, day):
    user_id = flask.session.get(COOKIE_USER)
    if not user_id:
        return flask.redirect(flask.url_for("login"))
    user_profile = ds.profile(user_id)

    source_activities = ds.list_activities(
        user_id=user_id,
        dataset_name=user_profile.dataset_name,
        filter_year=int(year),
        filter_month=int(month),
        filter_day=int(day),
    )

    if not source_activities:
        flask.flash("No activities found on this date to copy.", "warning")
        return flask.redirect(
            flask.url_for("list_activities_for_date", year=year, month=month, day=day)
        )

    form = forms.CopyDayForm()

    if form.validate_on_submit():
        target_year = form.target_year.data
        target_month = form.target_month.data
        target_day = form.target_day.data

        try:
            datetime.date(target_year, target_month, target_day)
        except ValueError:
            flask.flash(
                f"Invalid target date: {target_year}/{target_month}/{target_day}",
                "danger",
            )
            return flask.render_template(
                "day-copy.html",
                user_profile=user_profile,
                activities=source_activities,
                activity_types=ds.list_activity_types(user_id=user_id),
                form=form,
                year=year,
                month=month,
                day=day,
            )

        copied_count = 0
        for activity in source_activities:
            new_activity = copy.deepcopy(activity)
            new_activity.when_year = target_year
            new_activity.when_month = target_month
            new_activity.when_day = target_day
            new_activity.when = f"{target_year}-{target_month:02d}-{target_day:02d}"
            new_activity.key = ds.create_key()

            ds.create_activity(
                user_id=user_id,
                dataset_name=user_profile.dataset_name,
                entity=new_activity,
            )
            copied_count += 1

        flask.flash(
            f"Successfully copied {copied_count} "
            f"activit{'ies' if copied_count != 1 else 'y'} to "
            f"{target_year}/{target_month}/{target_day}",
            "success",
        )
        return flask.redirect(
            flask.url_for(
                "list_activities_for_date",
                year=target_year,
                month=target_month,
                day=target_day,
            )
        )

    if flask.request.method == "GET":
        today = datetime.date.today()
        form.target_year.data = today.year
        form.target_month.data = today.month
        form.target_day.data = today.day

    return flask.render_template(
        "day-copy.html",
        user_profile=user_profile,
        activities=source_activities,
        activity_types=ds.list_activity_types(user_id=user_id),
        form=form,
        year=year,
        month=month,
        day=day,
    )


@flask_app.route("/heatmap/y2y-month-perspective")
def y2y_month_perspective():
    user_id = flask.session.get(COOKIE_USER)
    if not user_id:
        return flask.redirect(flask.url_for("login"))
    user_profile = ds.profile(user_id)

    # per-year stats map: year -> (distance, duration, color)
    data = {
        "Jan": {},
        "Feb": {},
        "Mar": {},
        "Apr": {},
        "May": {},
        "Jun": {},
        "Jul": {},
        "Aug": {},
        "Sep": {},
        "Oct": {},
        "Nov": {},
        "Dec": {},
    }
    activity_types = ds.list_activity_types(user_id=user_id)
    ds_stats = ds.activities_stats(
        user_id=user_id,
        dataset_name=user_profile.dataset_name,
        include_meta=True,
    )
    referential_year = ds_stats.year_max
    this_month = int(datetime.date.today().month)

    for year in range(referential_year, ds_stats.year_min - 1, -1):
        for m in data:
            data[m][year] = [0.0, "0h00m00s", ""]

        year_as = ds.list_activities(
            user_id=user_id,
            dataset_name=user_profile.dataset_name,
            filter_year=year,
        )
        year_stats = stats.ActivitiesStats(year_as)
        year_data_distance = year_stats.get_year_totals(
            aspect=commons.StatsAspect.DISTANCE, activity_types=activity_types
        )
        year_data_duration = year_stats.get_year_totals(
            aspect=commons.StatsAspect.DURATION, activity_types=activity_types
        )

        if year == referential_year and this_month < 12:
            for month_idx in range(this_month + 1, 13):
                year_data_distance[month_idx] = 0.0
                year_data_duration[month_idx] = 0

        for month_idx in year_data_distance:
            data[cals.MONTH_INDEX_2_STR[month_idx]][year][0] = round(
                year_data_distance[month_idx] / 1000, 1
            )
            data[cals.MONTH_INDEX_2_STR[month_idx]][year][1] = cals.seconds_to_str_time(
                year_data_duration[month_idx]
            )

    # colors
    for m in data:
        for year in data[m]:
            if year != referential_year:
                if cals.MONTH_STR_2_INDEX[m] > this_month:
                    data[m][year][2] = ""
                    continue

                if data[m][year][0] > data[m][referential_year][0]:
                    data[m][year][2] = "#ffcccc"
                elif data[m][year][0] == data[m][referential_year][0]:
                    data[m][year][2] = "#cccccc"
                else:
                    data[m][year][2] = "#ccffcc"
            else:
                if data[m][year][0] > 0:
                    data[m][year][2] = "#fffffe"

    return flask.render_template(
        "heatmap-y2y-month-perspective.html",
        user_profile=user_profile,
        data=data,
        years=[y for y in data.get("Jan", []).keys()],
    )


@flask_app.route("/heatmap/weekday-to-activity")
def heatmap_weekday_to_activity():
    user_id = flask.session.get(COOKIE_USER)
    if not user_id:
        return flask.redirect(flask.url_for("login"))
    user_profile = ds.profile(user_id)

    aspect = flask.request.args.get("aspect", "heatmap")

    # map: weekday -> activity
    activities = ds.list_activities(
        user_id=user_id, dataset_name=user_profile.dataset_name, skip_future=True
    )

    if activities:
        # map: weekday -> activity type -> count
        weekday_activities_heatmap = {d: {} for d in cals.WEEKDAY_INDEX_2_STR.values()}
        heatmap_sports = set()
        activities_count = {"all": 0}
        activity_types = ds.list_activity_types(user_id=user_id)
        for a in activities:
            if not activity_types.is_sport(a.activity_type_key):
                continue
            activities_count["all"] += 1

            weekday = cals.WEEKDAY_INDEX_2_STR.get(
                calendar.weekday(a.when_year, a.when_month, a.when_day), ""
            )
            if a.activity_type_key not in weekday_activities_heatmap[weekday]:
                heatmap_sports.add(a.activity_type_key)
                weekday_activities_heatmap[weekday][a.activity_type_key] = 0
            if a.activity_type_key not in activities_count:
                activities_count[a.activity_type_key] = 0
            weekday_activities_heatmap[weekday][a.activity_type_key] += 1
            activities_count[a.activity_type_key] += 1

        heatmap_sports = list(heatmap_sports)
        # sort by total count (descending)
        heatmap_sports.sort(key=lambda s: activities_count.get(s, 0), reverse=True)
        # min/max for heatmap map: activity_type_key -> (min count, max count)
        heatmap_sports_min_max = {}
        for w in weekday_activities_heatmap:
            for s in weekday_activities_heatmap[w]:
                if s not in heatmap_sports_min_max:
                    heatmap_sports_min_max[s] = (0, weekday_activities_heatmap[w][s])
                heatmap_sports_min_max[s] = (
                    min(heatmap_sports_min_max[s][0], weekday_activities_heatmap[w][s]),
                    max(heatmap_sports_min_max[s][1], weekday_activities_heatmap[w][s]),
                )
        heatmap_palettes = {}
        for s in heatmap_sports:
            p = ninjas.HeatmapPaletteNinja(
                base_color=ninjas.HeatmapPaletteNinja.BASE_COLOR_G,
                min_value=heatmap_sports_min_max[s][0],
                max_value=heatmap_sports_min_max[s][1],
            )
            heatmap_palettes[s] = p
        # extend heatmap map w/ colors
        for w in weekday_activities_heatmap:
            for s in heatmap_sports:
                if s in weekday_activities_heatmap[w]:
                    weekday_activities_heatmap[w][s] = (
                        weekday_activities_heatmap[w][s],
                        heatmap_palettes[s].color(weekday_activities_heatmap[w][s]),
                    )
                else:
                    weekday_activities_heatmap[w][s] = (0, heatmap_palettes[s].color(0))

        # calculate weekday totals
        weekday_totals = {}
        for w in weekday_activities_heatmap:
            total = sum(weekday_activities_heatmap[w][s][0] for s in heatmap_sports)
            weekday_totals[w] = total

        # find most active day
        most_active_day = (
            max(weekday_totals, key=weekday_totals.get) if weekday_totals else ""
        )

        # calculate average activities per weekday (across all time)
        avg_per_weekday = (
            round(activities_count["all"] / 7, 1) if activities_count["all"] else 0
        )

        # bokeh chart only when chart aspect is requested
        chart_script, chart_div = None, None
        is_mobile = bool(flask.session.get(COOKIE_MOBILE))
        if aspect == "chart" and heatmap_sports:
            chart_script, chart_div = charts.weekday_activity_heatmap(
                weekday_activities_heatmap=weekday_activities_heatmap,
                heatmap_sports=heatmap_sports,
                is_mobile_view=is_mobile,
            )

        return flask.render_template(
            "heatmap-weekday-to-activity.html",
            user_profile=user_profile,
            form=forms.SettingsForm(),
            aspect=aspect,
            activities_count=activities_count,
            weekday_activities_heatmap=weekday_activities_heatmap,
            heatmap_sports=heatmap_sports,
            weekday_totals=weekday_totals,
            most_active_day=most_active_day,
            avg_per_weekday=avg_per_weekday,
            chart_script=chart_script,
            chart_div=chart_div,
        )

    return flask.redirect(flask.url_for("home"))


@flask_app.route("/search")
def search():
    user_id = flask.session.get(COOKIE_USER)
    if not user_id:
        return flask.redirect(flask.url_for("login"))

    return flask.render_template(
        "search.html",
        user_profile=ds.profile(user_id),
    )


@flask_app.route("/calendar/heatmap")
def calendar_heatmap():
    user_id = flask.session.get(COOKIE_USER)
    if not user_id:
        return flask.redirect(flask.url_for("login"))
    user_profile = ds.profile(user_id)

    cal_heatmap = ds.activity_type_heatmap(
        user_id=user_id, dataset_name=user_profile.dataset_name
    )

    if cal_heatmap.activities:
        return flask.render_template(
            "heatmap-calendar.html",
            user_profile=user_profile,
            data=cal_heatmap,
            is_mobile=flask.session.get(COOKIE_MOBILE),
        )

    return flask.redirect(flask.url_for("home"))


@flask_app.route("/calendar/year/<year>")
def calendar_year(year):
    user_id = flask.session.get(COOKIE_USER)
    if not user_id:
        return flask.redirect(flask.url_for("login"))
    user_profile = ds.profile(user_id)

    # redirect to valid year
    try:
        year_int = int(year)
    except ValueError:
        flask.abort(400)

    if not year_int:
        year_int = ds.activities_stats(
            user_id=user_id,
            dataset_name=user_profile.dataset_name,
            include_meta=True,
        ).year_max
        if year_int:
            return flask.redirect(f"/calendar/year/{year_int}")
        else:
            return flask.redirect(flask.url_for("home"))

    # age at a year
    age_at_year = (
        cals.get_age_at(
            born_year=user_profile.born_year,
            born_month=user_profile.born_month,
            born_day=user_profile.born_day,
            year=year_int,
        )
        if year_int
        else 0
    )

    cal_heatmap = views.CalendarHeatmap(
        from_year=year_int,
        to_year=year_int,
        user_profile=user_profile,
        activity_types=ds.list_activity_types(user_id),
        logger=app_logger,
    )
    cal_heatmap.build_activity_type_heatmap(
        activities=ds.list_activities(
            user_id=user_id, dataset_name=user_profile.dataset_name
        ),
    )

    activities_stats = ds.activities_stats(
        user_id=user_id,
        dataset_name=user_profile.dataset_name,
        activities=ds.list_activities(
            user_id=user_id,
            dataset_name=user_profile.dataset_name,
            filter_year=year_int,
        ),
    )

    today = datetime.date.today()
    current_week = today.isocalendar()[1]

    # serialize week stats for the year bar chart navigation widget
    calendar_week_stats = []
    for week_num in cal_heatmap.heatmap.get(year_int, {}):
        stats = cal_heatmap.week_stats.get(year_int, {}).get(week_num, {})
        calendar_week_stats.append(
            {
                "week_number": week_num,
                "meters": stats.get("meters", 0),
                "seconds": stats.get("seconds", 0),
                "kgs": stats.get("kgs", 0),
                "weight": stats.get("weight", 0) or 0,
                "time": stats.get("time", "00:00:00"),
                "week_date": stats.get("week_date", ""),
            }
        )

    return flask.render_template(
        "calendar-year.html",
        user_profile=user_profile,
        year=year_int,
        years=reversed(
            [
                y
                for y in range(
                    user_profile.born_year,
                    datetime.date.today().year + 1,
                )
            ]
        ),
        data=cal_heatmap,
        stats=activities_stats,
        activity_types=ds.list_activity_types(user_id=user_id),
        symptoms=ds.list_symptoms(user_id=user_id),
        age_at_year=age_at_year,
        current_year=today.year,
        current_week=current_week,
        calendar_week_stats_json=json.dumps(calendar_week_stats),
        view=flask.request.args.get("view"),  # compact or full
        is_mobile=flask.session.get(COOKIE_MOBILE),
    )


@flask_app.route("/charts/year/<year>")
def charts_year(year):
    user_id = flask.session.get(COOKIE_USER)
    if not user_id:
        return flask.redirect(flask.url_for("login"))
    user_profile = ds.profile(user_id)

    year_int = 2000
    try:
        year_int = int(year)
    except ValueError:
        flask.abort(400)

    if not year_int:
        year_int = ds.activities_stats(
            user_id=user_id, dataset_name=user_profile.dataset_name
        ).year_max
        if year_int:
            return flask.redirect(f"/charts/year/{year_int}")
        else:
            return flask.redirect(flask.url_for("home"))

    cal_heatmap = views.CalendarHeatmap(
        from_year=year_int,
        to_year=year_int,
        user_profile=user_profile,
        activity_types=ds.list_activity_types(user_id),
        logger=app_logger,
    )
    cal_heatmap.build_activity_type_heatmap(
        activities=ds.list_activities(
            user_id=user_id, dataset_name=user_profile.dataset_name
        ),
    )

    # chart
    chart_type = flask.request.args.get("chart")
    if chart_type in [charts.ChartType.KM.value, charts.ChartType.SUM_KM.value]:
        script, div = charts.total_km_per_week_in_year(
            cal_heatmap=cal_heatmap,
            year=year_int,
            cumulative=bool(chart_type == charts.ChartType.SUM_KM.value),
            is_mobile_view=flask.session.get(COOKIE_MOBILE),
        )
    elif chart_type in [charts.ChartType.HOUR.value, charts.ChartType.SUM_HOUR.value]:
        script, div = charts.total_hours_per_week_in_year(
            cal_heatmap=cal_heatmap,
            year=year_int,
            cumulative=bool(chart_type == charts.ChartType.SUM_HOUR.value),
            is_mobile_view=flask.session.get(COOKIE_MOBILE),
        )
    elif chart_type in [charts.ChartType.KG.value, charts.ChartType.SUM_KG.value]:
        script, div = charts.total_kg_per_week_in_year(
            cal_heatmap=cal_heatmap,
            year=year_int,
            cumulative=bool(chart_type == charts.ChartType.SUM_KG.value),
            is_mobile_view=flask.session.get(COOKIE_MOBILE),
        )
    elif chart_type == charts.ChartType.WEIGHT.value:
        script, div = charts.average_weight_per_week_in_year(
            cal_heatmap=cal_heatmap,
            year=year_int,
            is_mobile_view=flask.session.get(COOKIE_MOBILE),
        )
    else:
        app_logger.warning(f"Unsupported chart type: {chart_type}")
        script, div = charts.total_km_per_week_in_year(
            cal_heatmap=cal_heatmap,
            year=year_int,
            is_mobile_view=flask.session.get(COOKIE_MOBILE),
        )

    return flask.render_template(
        "charts-year.html",
        user_profile=user_profile,
        year=year_int,
        years=reversed(
            [
                y
                for y in range(
                    user_profile.born_year,
                    datetime.date.today().year + 1,
                )
            ]
        ),
        data=cal_heatmap,
        stats=ds.activities_stats(
            user_id=user_id,
            dataset_name=user_profile.dataset_name,
            activities=cal_heatmap.activities,
        ),
        div=div,  # bokeh
        script=script,  # bokeh
    )


@flask_app.route("/app/insights/sickness/heatmap")
def insight_sickness_heatmap():
    user_id = flask.session.get(COOKIE_USER)
    if not user_id:
        return flask.redirect(flask.url_for("login"))
    user_profile = ds.profile(user_id)

    this_year = datetime.date.today().year

    cal_heatmap = views.CalendarHeatmap(
        from_year=this_year,
        to_year=this_year,
        user_profile=user_profile,
        activity_types=ds.list_activity_types(user_id),
        logger=app_logger,
    )

    activities = ds.list_activities(
        user_id=user_id, dataset_name=user_profile.dataset_name
    )

    if activities:
        cal_heatmap.build_sickness_heatmap(activities=activities)

        return flask.render_template(
            "insight-sickness-heatmap.html",
            user_profile=user_profile,
            data=cal_heatmap,
        )

    return flask.redirect(flask.url_for("home"))


#
# Blob store routes – activity recordings and photos
#


@flask_app.route(
    "/app/activities/<activity_key>/recordings/upload",
    methods=["GET", "POST"],
)
def upload_activity_recording(activity_key: str):
    """Upload a raw recording file to an activity."""
    user_id = flask.session.get(COOKIE_USER)
    if not user_id:
        return flask.redirect(flask.url_for("login"))

    user_profile = ds.profile(user_id)

    if flask.request.method == "POST":
        form = forms.UploadRecordingForm()
        if form.validate_on_submit():
            file_storage = form.recording_file.data
            svc = _blob_service()
            try:
                meta = svc.upload_recording(
                    user_id=user_id,
                    activity_key=activity_key,
                    uploaded_file=file_storage.stream,
                    original_filename=file_storage.filename,
                    content_type=file_storage.content_type or "",
                    name=form.name.data or "",
                    description=form.description.data or "",
                    keywords=form.keywords.data or "",
                )

                task_type = ""
                if meta.extension == ".fit":
                    task_type = do.fit_import.FitImportTask.TASK_TYPE
                elif meta.extension == ".gpx":
                    task_type = do.gpx_import.GpxImportTask.TASK_TYPE
                elif meta.extension == ".hrm":
                    task_type = do.recording_reprocess.RecordingReprocessTask.TASK_TYPE

                if task_type:
                    task_entity = task_entities.TaskEntity(
                        key=str(uuid.uuid4()),
                        user_id=str(user_id),
                        task_type=task_type,
                        status=task_entities.TaskStatus.QUEUED,
                        created_at=datetime.datetime.now(),
                        started_at=None,
                        completed_at=None,
                        error_message=None,
                        error_type=None,
                        error_traceback=None,
                        progress=0,
                        parameters={
                            "user_id": user_id,
                            "dataset_name": user_profile.dataset_name,
                            "activity_key": activity_key,
                            "source_blob_uuid": meta.blob_key,
                            "blob_key": meta.blob_key,
                        },
                        is_cancelled=False,
                        result_route="get_activity",
                        result_route_kwargs={"key": activity_key},
                    )
                    task_id = app_task_manager.executor.submit(task_entity)
                    flask.flash(
                        message=(
                            f"Recording uploaded and processing queued (task {task_id})"
                        ),
                        category="success",
                    )
                    return flask.redirect(flask.url_for("task_detail", task_id=task_id))
                else:
                    flask.flash(
                        message=(
                            "Recording uploaded. Parquet conversion is available "
                            "for FIT/GPX/HRM uploads only"
                        ),
                        category="success",
                    )
                    return flask.redirect(
                        flask.url_for("get_activity", key=activity_key)
                    )

            except (
                blob_pkg.BlobValidationError,
                blob_pkg.BlobStoreError,
                ValueError,
            ) as exc:
                msg = f"Recording upload error: {exc}"
                app_logger.error(msg, traceback=f"{traceback.format_exc()}")
                flask.flash(message=msg, category="error")
        else:
            msg = "Recording upload form validation failed"
            app_logger.error(msg)
            flask.flash(message=msg, category="error")
    else:
        form = forms.UploadRecordingForm()

    return flask.render_template(
        "activity-recording-upload.html",
        form=form,
        activity_key=activity_key,
        user_id=user_id,
        user_profile=user_profile,
    )


@flask_app.route(
    "/app/activities/<activity_key>/recordings/<blob_uuid>/download",
    methods=["GET"],
)
def download_activity_recording(activity_key: str, blob_uuid: str):
    """Download a raw recording file."""
    user_id = flask.session.get(COOKIE_USER)
    if not user_id:
        return flask.redirect(flask.url_for("login"))

    svc = _blob_service()
    try:
        stream, meta = svc.open_recording(
            user_id=user_id,
            activity_key=activity_key,
            blob_key=blob_uuid,
        )
        raw_name = meta.original_file_name or f"recording-{blob_uuid}{meta.extension}"
        return flask.send_file(
            stream,
            mimetype="application/octet-stream",
            as_attachment=True,
            download_name=_sanitize_download_name(raw_name),
        )
    except (blob_pkg.BlobValidationError, blob_pkg.BlobNotFoundError) as exc:
        msg = f"Avatar upload failed: {exc}"
        app_logger.error(msg, user_id=user_id, traceback=traceback.format_exc())
        flask.flash(message=msg, category="error")
        return flask.redirect(flask.url_for("get_activity", key=activity_key))


@flask_app.route(
    "/app/activities/<activity_key>/recordings/<blob_uuid>/delete",
    methods=["POST"],
)
def delete_activity_recording(activity_key: str, blob_uuid: str):
    """Delete a recording and its associated Parquet."""
    user_id = flask.session.get(COOKIE_USER)
    if not user_id:
        return flask.redirect(flask.url_for("login"))

    svc = _blob_service()
    try:
        svc.delete_recording(
            user_id=user_id,
            activity_key=activity_key,
            blob_key=blob_uuid,
        )
        flask.flash(message="Recording deleted", category="success")
    except (blob_pkg.BlobValidationError, blob_pkg.BlobStoreError) as exc:
        msg = f"Recording delete error: {exc}"
        app_logger.error(msg, user_id=user_id, traceback=traceback.format_exc())
        flask.flash(message=msg, category="error")

    return flask.redirect(
        flask.url_for("get_activity", key=activity_key) + "#recordings-row"
    )


@flask_app.route(
    "/app/activities/<activity_key>/recordings/<blob_uuid>/reprocess",
    methods=["POST"],
)
def reprocess_activity_recording(activity_key: str, blob_uuid: str):
    """Queue a re-process task for a recording."""
    from mytral.tasks.do import recording_reprocess

    user_id = flask.session.get(COOKIE_USER)
    if not user_id:
        return flask.redirect(flask.url_for("login"))

    user_profile = ds.profile(user_id)
    task = task_entities.TaskEntity(
        key=str(uuid.uuid4()),
        task_type=recording_reprocess.RecordingReprocessTask.TASK_TYPE,
        user_id=user_id,
        status=task_entities.TaskStatus.QUEUED,
        created_at=datetime.datetime.now(),
        started_at=None,
        completed_at=None,
        error_message=None,
        error_type=None,
        error_traceback=None,
        progress=0,
        parameters={
            "user_id": user_id,
            "dataset_name": user_profile.dataset_name,
            "activity_key": activity_key,
            "source_blob_uuid": blob_uuid,
            "blob_key": blob_uuid,
        },
        is_cancelled=False,
    )
    task_id = app_task_manager.executor.submit(task)
    flask.flash(
        message=f"Recording re-processing queued (task {task_id})",
        category="success",
    )
    return flask.redirect(flask.url_for("get_activity", key=activity_key))


@flask_app.route(
    "/app/activities/<activity_key>/photos/upload", methods=["GET", "POST"]
)
def upload_activity_photos(activity_key: str):
    """Upload one or more photos to an activity.

    GET  – render upload form
    POST – process uploaded files
    """
    user_id = flask.session.get(COOKIE_USER)
    if not user_id:
        return flask.redirect(flask.url_for("login"))

    if flask.request.method == "POST":
        form = forms.UploadActivityPhotosForm()
        if form.validate_on_submit():
            uploaded = form.photos.data
            if not isinstance(uploaded, list):
                uploaded = [uploaded]
            pairs = [(f.stream, f.filename) for f in uploaded if f.filename]
            svc = _blob_service()
            try:
                svc.upload_photos(
                    user_id=user_id,
                    activity_key=activity_key,
                    uploaded_files=pairs,
                    name=form.name.data or "",
                    description=form.description.data or "",
                    keywords=form.keywords.data or "",
                )
                flask.flash(
                    message=f"{len(pairs)} photo(s) uploaded", category="success"
                )
                return flask.redirect(flask.url_for("get_activity", key=activity_key))
            except (blob_pkg.BlobValidationError, blob_pkg.BlobStoreError) as exc:
                msg = f"Photo upload error: {exc}"
                app_logger.error(msg, user_id=user_id, traceback=traceback.format_exc())
                flask.flash(message=msg, category="error")
        else:
            flask.flash(message="Photo upload form validation failed", category="error")

    else:
        form = forms.UploadActivityPhotosForm()

    svc = _blob_service()
    try:
        activity = ds.get_activity(
            user_id=user_id,
            dataset_name=ds.profile(user_id).dataset_name,
            key=activity_key,
        )
        current_count = len(activity.photo_blob_keys)
    except (ValueError, KeyError):
        current_count = 0

    return flask.render_template(
        "activity-photos-upload.html",
        form=form,
        activity_key=activity_key,
        current_count=current_count,
        user_id=user_id,
        user_profile=ds.profile(user_id),
    )


@flask_app.route(
    "/app/activities/<activity_key>/blob/photos/<blob_key>",
    methods=["GET"],
)
def download_activity_photo(activity_key: str, blob_key: str):
    """Stream a normalized activity photo."""
    user_id = flask.session.get(COOKIE_USER)
    if not user_id:
        return flask.redirect(flask.url_for("login"))

    svc = _blob_service()
    try:
        stream, meta = svc.open_photo(
            user_id=user_id,
            activity_key=activity_key,
            blob_key=blob_key,
            variant="normalized",
        )
        return flask.send_file(stream, mimetype=meta.content_type)
    except (
        blob_pkg.BlobValidationError,
        blob_pkg.BlobNotFoundError,
        blob_pkg.BlobStoreError,
    ) as exc:
        msg = f"Photo download error: {exc}"
        app_logger.error(msg, user_id=user_id, traceback=traceback.format_exc())
        flask.flash(message=msg, category="error")
        return flask.redirect(flask.url_for("get_activity", key=activity_key))


@flask_app.route(
    "/app/activities/<activity_key>/blob/photos/<blob_key>/thumbnail",
    methods=["GET"],
)
def download_activity_photo_thumbnail(activity_key: str, blob_key: str):
    """Stream an activity photo thumbnail."""
    user_id = flask.session.get(COOKIE_USER)
    if not user_id:
        return flask.redirect(flask.url_for("login"))

    svc = _blob_service()
    try:
        stream, meta = svc.open_photo(
            user_id=user_id,
            activity_key=activity_key,
            blob_key=blob_key,
            variant="thumbnail",
        )
        return flask.send_file(stream, mimetype="image/jpeg")
    except (
        blob_pkg.BlobValidationError,
        blob_pkg.BlobNotFoundError,
        blob_pkg.BlobStoreError,
    ) as exc_top:
        app_logger.warning(
            f"Fallback on activity thumbnail DOWNLOAD error: {exc_top}",
            user_id=user_id,
            traceback=traceback.format_exc(),
        )
        # fall back to normalized when thumbnail is not yet generated
        try:
            stream, meta = svc.open_photo(
                user_id=user_id,
                activity_key=activity_key,
                blob_key=blob_key,
                variant="normalized",
            )
            return flask.send_file(stream, mimetype=meta.content_type)
        except (
            blob_pkg.BlobValidationError,
            blob_pkg.BlobNotFoundError,
            blob_pkg.BlobStoreError,
        ) as exc:
            msg = f"Thumbnail error: {exc}"
            app_logger.error(msg, user_id=user_id, traceback=traceback.format_exc())
            flask.flash(message=msg, category="error")
            return flask.redirect(flask.url_for("get_activity", key=activity_key))


@flask_app.route(
    "/app/activities/<activity_key>/blob/photos/<blob_key>/update",
    methods=["GET", "POST"],
)
def update_activity_photo_metadata(activity_key: str, blob_key: str):
    """Update user-editable metadata for a photo."""
    user_id = flask.session.get(COOKIE_USER)
    if not user_id:
        return flask.redirect(flask.url_for("login"))

    blob_svc = _blob_service()
    try:
        photos = blob_svc.list_photos(user_id=user_id, activity_key=activity_key)
    except (blob_pkg.BlobStoreError, blob_pkg.BlobValidationError) as exc:
        msg = f"Photo metadata error: {exc}"
        app_logger.error(msg, user_id=user_id, traceback=traceback.format_exc())
        flask.flash(message=msg, category="error")
        return flask.redirect(flask.url_for("get_activity", key=activity_key))

    photo = next((item for item in photos if item.blob_key == blob_key), None)
    if photo is None:
        flask.abort(404)

    form = forms.UpdateActivityPhotoMetadataForm()
    if flask.request.method == "GET":
        form.name.data = photo.name
        form.description.data = photo.description
        form.keywords.data = ", ".join(photo.keywords)
        return flask.render_template(
            "activity-photo-update.html",
            user_profile=ds.profile(user_id),
            form=form,
            key=activity_key,
            photo=photo,
        )

    if form.validate_on_submit():
        try:
            blob_svc.update_photo_metadata(
                user_id=user_id,
                activity_key=activity_key,
                blob_key=blob_key,
                name=form.name.data or "",
                description=form.description.data or "",
                keywords=form.keywords.data or "",
            )
            flask.flash(message="Photo metadata updated", category="success")
        except (blob_pkg.BlobValidationError, blob_pkg.BlobStoreError) as exc:
            msg = f"Photo metadata error: {exc}"
            app_logger.error(msg, user_id=user_id, traceback=traceback.format_exc())
            flask.flash(message=msg, category="error")
    else:
        msg = "Photo metadata form validation failed"
        app_logger.error(msg, user_id=user_id, traceback=traceback.format_exc())
        flask.flash(message=msg, category="error")

    return flask.redirect(
        flask.url_for("get_activity", key=activity_key) + "#photos-row"
    )


@flask_app.route(
    "/app/activities/<activity_key>/blob/photos/<blob_key>/delete",
    methods=["POST"],
)
def delete_activity_photo(activity_key: str, blob_key: str):
    """Delete a photo from an activity."""
    user_id = flask.session.get(COOKIE_USER)
    if not user_id:
        return flask.redirect(flask.url_for("login"))

    svc = _blob_service()
    try:
        svc.delete_photo(
            user_id=user_id,
            activity_key=activity_key,
            blob_key=blob_key,
        )
        flask.flash(message="Photo deleted", category="success")
    except (blob_pkg.BlobValidationError, blob_pkg.BlobStoreError) as exc:
        msg = f"Photo delete error: {exc}"
        app_logger.error(msg, user_id=user_id, traceback=traceback.format_exc())
        flask.flash(message=msg, category="error")

    return flask.redirect(
        flask.url_for("get_activity", key=activity_key) + "#photos-row"
    )


@flask_app.route(
    "/app/activities/<activity_key>/blob/photos/<blob_key>/highlight",
    methods=["POST"],
)
def set_activity_highlight_photo(activity_key: str, blob_key: str):
    """Set a photo as the activity highlight image."""
    user_id = flask.session.get(COOKIE_USER)
    if not user_id:
        return flask.redirect(flask.url_for("login"))

    svc = _blob_service()
    try:
        svc.set_highlight_photo(
            user_id=user_id,
            activity_key=activity_key,
            blob_key=blob_key,
        )
        flask.flash(message="Highlight photo set", category="success")
    except (blob_pkg.BlobValidationError, blob_pkg.BlobStoreError) as exc:
        msg = f"Highlight photo error: {exc}"
        app_logger.error(msg, user_id=user_id, traceback=traceback.format_exc())
        flask.flash(message=msg, category="error")

    return flask.redirect(flask.url_for("get_activity", key=activity_key))
