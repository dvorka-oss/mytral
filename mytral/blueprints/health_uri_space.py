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

import flask

from mytral import app_user_ds as ds
from mytral import charts
from mytral.routes import COOKIE_MOBILE
from mytral.routes import COOKIE_USER
from mytral.routes import flask_app

BODY_PARTS = {
    # head / neck
    "head": ["front-head", "back-head"],
    "neck": ["front-neck", "back-neck"],
    # shoulders
    "shoulder_left": ["front-shoulder-l", "back-shoulder-l"],
    "shoulder_right": ["front-shoulder-r", "back-shoulder-r"],
    # chest / back
    "chest": ["front-chest"],
    "upper_back": ["back-upper", "back-lats-r", "back-lats-l"],
    "lower_back": ["back-lower"],
    # arms
    "arm_left": ["front-arm-l", "back-arm-l"],
    "arm_right": ["front-arm-r", "back-arm-r"],
    "elbow_left": ["front-elbow-l", "back-elbow-l"],
    "elbow_right": ["front-elbow-r", "back-elbow-r"],
    "forearm_left": ["front-forearm-l", "back-forearm-l"],
    "forearm_right": ["front-forearm-r", "back-forearm-r"],
    "wrist_left": ["front-wrist-l", "back-wrist-l"],
    "wrist_right": ["front-wrist-r", "back-wrist-r"],
    "hand_left": ["front-hand-l", "back-hand-l"],
    "hand_right": ["front-hand-r", "back-hand-r"],
    # hips / legs
    "hip_left": ["front-hip-l", "back-hip-l"],
    "hip_right": ["front-hip-r", "back-hip-r"],
    "thigh_left": ["front-thigh-l", "back-thigh-l"],
    "thigh_right": ["front-thigh-r", "back-thigh-r"],
    "knee_left": ["front-knee-l", "back-knee-l"],
    "knee_right": ["front-knee-r", "back-knee-r"],
    "calf_left": ["front-calf-l", "back-calf-l"],
    "calf_right": ["front-calf-r", "back-calf-r"],
    "ankle_left": ["front-ankle-l", "back-ankle-l"],
    "ankle_right": ["front-ankle-r", "back-ankle-r"],
    "foot_left": ["front-foot-l", "back-foot-l"],
    "foot_right": ["front-foot-r", "back-foot-r"],
}


def _get_active_injuries(user_id: str, year: int = None):
    """Get active injuries and sicknesses from activities.

    Parameters
    ----------
    user_id : str
        user identifier
    year : int, optional
        filter by year, None for current year only, 0 for all years

    Returns
    -------
    list[dict]
        list of injury/sickness records with fields:
        - symptom: str
        - side: str
        - body_part: str
        - health: int
        - date: str
    """
    activities = ds.list_activities(
        user_id=user_id,
        dataset_name=ds.profile(user_id).dataset_name,
    )

    injuries = []
    current_year = datetime.date.today().year

    for activity in activities:
        if year is not None and year != 0 and activity.when_year != year:
            continue
        if year is None and activity.when_year != current_year:
            continue

        if activity.sickness_symptoms:
            for symptom in activity.sickness_symptoms:
                if symptom.health < 100:
                    injuries.append(
                        {
                            "symptom": symptom.symptom,
                            "side": symptom.side,
                            "body_part": symptom.body_part,
                            "health": symptom.health,
                            "date": activity.when,
                            "year": activity.when_year,
                            "activity_year": activity.when_year,
                            "activity_month": activity.when_month,
                            "activity_day": activity.when_day,
                        }
                    )

    return injuries


def _build_body_highlights(injuries: list[dict], symptoms_registry) -> set:
    """Build body highlight set from symptom definitions.

    For each recorded injury, look up the symptom by name in the registry
    and collect all body_parts defined on that symptom. Falls back to the
    legacy body_part field on the injury record when the symptom has no
    body_parts defined yet.

    Parameters
    ----------
    injuries : list[dict]
        list of injury records (from _get_active_injuries)
    symptoms_registry : UserSymptoms
        user's symptom registry loaded from the data store

    Returns
    -------
    set[str]
        set of SVG element IDs to highlight as injured on the mannequin
    """
    highlights: set[str] = set()
    for injury in injuries:
        symptom_key = injury.get("symptom", "")
        symptom = symptoms_registry.symptoms_by_key.get(symptom_key)
        if symptom and symptom.body_parts:
            highlights.update(symptom.body_parts)
        else:
            # legacy fallback: use the body_part + side recorded on the activity
            body_part = injury.get("body_part")
            side = injury.get("side")
            if body_part:
                key = f"{body_part}_{side}" if side else body_part
                if key in BODY_PARTS:
                    highlights.update(BODY_PARTS[key])

    return highlights


@flask_app.route("/me")
@flask_app.route("/me/<int:year>")
def me(year=None):
    """Display body visualization with injury/sickness highlights.

    Parameters
    ----------
    year : int, optional
        year to filter injuries, None for current year, 0 for all years

    Returns
    -------
    str
        rendered me.html template with injury data
    """
    user_id = flask.session.get(COOKIE_USER)
    if not user_id:
        return flask.redirect(flask.url_for("login"))

    if year is None:
        year = datetime.date.today().year

    injuries = _get_active_injuries(user_id, year)

    # build body highlights from symptom definitions (body_parts field)
    symptoms_registry = ds.list_symptoms(user_id=user_id)
    body_highlights = _build_body_highlights(injuries, symptoms_registry)

    # enrich each injury with resolved SVG part IDs for JS-based filtering
    for injury in injuries:
        symptom = symptoms_registry.symptoms_by_key.get(injury["symptom"])
        injury["body_parts"] = (
            symptom.body_parts if (symptom and symptom.body_parts) else []
        )

    # get available years from activities
    activities = ds.list_activities(
        user_id=user_id,
        dataset_name=ds.profile(user_id).dataset_name,
    )
    years = sorted(
        set(a.when_year for a in activities if a.sickness_symptoms), reverse=True
    )

    chart_script, chart_div = charts.me_symptoms_scatter(
        injuries=injuries,
        symptoms_registry=symptoms_registry,
        year=year,
        is_mobile_view=bool(flask.session.get(COOKIE_MOBILE)),
    )

    return flask.render_template(
        "me.html",
        injuries=injuries,
        body_highlights=body_highlights,
        title="My Body Status",
        user_profile=ds.profile(user_id),
        year=year,
        years=years,
        current_year=datetime.date.today().year,
        symptoms=symptoms_registry,
        script=chart_script,
        me_chart_div=chart_div,
    )
