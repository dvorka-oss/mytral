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
import flask

from mytral import app_logger
from mytral import app_user_ds as ds
from mytral import charts
from mytral import forms
from mytral import recommender
from mytral import views
from mytral.routes import COOKIE_MOBILE
from mytral.routes import COOKIE_USER
from mytral.routes import flask_app


def _activity_type_choices(activity_types) -> list[tuple[str, str]]:
    """Build (key, name) choices for the activity-type filter, sorted by name."""
    types = sorted(
        activity_types.activity_types_by_key.values(), key=lambda t: t.name.lower()
    )
    return [("", "All types")] + [(t.key, t.name) for t in types]


def _gear_choices(gear) -> list[tuple[str, str]]:
    """Build (key, name) choices for the gear filter, sorted by name."""
    items = sorted(gear.gear_by_key.values(), key=lambda g: g.name.lower())
    return [("", "All gear")] + [(g.key, g.name) for g in items]


def _build_query(form: forms.ActivityRecommenderForm) -> recommender.RecommenderQuery:
    """Translate submitted form data into a recommender query (km -> m, h+m -> s)."""
    hours = form.hours.data
    minutes = form.minutes.data
    duration_seconds = None
    if hours is not None or minutes is not None:
        duration_seconds = (hours or 0) * 3600 + (minutes or 0) * 60

    distance_m = None
    if form.distance_km.data is not None:
        distance_m = int(form.distance_km.data * 1000)

    elevation_m = None
    if form.elevation_m.data is not None:
        elevation_m = int(form.elevation_m.data)

    return recommender.RecommenderQuery(
        activity_type_key=form.activity_type_key.data or "",
        gear_key=form.gear_key.data or "",
        duration_seconds=duration_seconds,
        distance_m=distance_m,
        elevation_m=elevation_m,
    )


@flask_app.route("/app/recommender", methods=["GET", "POST"])
def activity_recommender():
    """Activity recommender: rank the user's activities by cosine similarity to a target
    duration/distance/elevation and cluster the matches in a scatter plot."""
    user_id = flask.session.get(COOKIE_USER)
    if not user_id:
        return flask.redirect(flask.url_for("login"))
    user_profile = ds.profile(user_id)
    activity_types = ds.list_activity_types(user_id)

    form = forms.ActivityRecommenderForm()
    form.activity_type_key.choices = _activity_type_choices(activity_types)
    form.gear_key.choices = _gear_choices(ds.list_gear(user_id))

    result = None
    recommendations = None
    scatter_script = None
    scatter_div = None

    if form.validate_on_submit():
        activities = ds.list_activities(
            user_id=user_id,
            dataset_name=user_profile.dataset_name,
            skip_future=True,
        )
        query = _build_query(form)
        result = recommender.recommend(activities, query)
        recommendations = views.ActivityRecommendationView.from_matches(
            result.matches, activity_types
        )
        if result.matches:
            cluster_result = recommender.cluster(result.matches)
            activity_urls = {
                m.activity.key: flask.url_for("get_activity", key=m.activity.key)
                for m in result.matches
            }
            scatter_script, scatter_div = charts.recommender_cluster_scatter(
                cluster_result=cluster_result,
                activity_urls=activity_urls,
                activity_types=activity_types,
                is_mobile_view=bool(flask.session.get(COOKIE_MOBILE)),
            )
        app_logger.info(
            "activity recommender ran",
            user=user_id,
            candidates=result.candidate_count,
            matches=len(result.matches),
        )
    elif flask.request.method == "POST":
        flask.flash(
            message="Activity recommender form validation error.", category="error"
        )

    recommended_type_name = ""
    if result and result.recommended_type_key:
        recommended_type_name = activity_types.name(result.recommended_type_key)

    return flask.render_template(
        "activity-recommender.html",
        user_profile=user_profile,
        form=form,
        result=result,
        recommendations=recommendations,
        recommended_type_name=recommended_type_name,
        script=scatter_script,
        scatter_div=scatter_div,
    )
