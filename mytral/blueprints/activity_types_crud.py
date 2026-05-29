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
import flask_wtf
import wtforms
from wtforms import validators

from mytral import app_user_ds as ds
from mytral import commons
from mytral import ff
from mytral import muscle_groups as mg
from mytral import settings as user_settings
from mytral.routes import COOKIE_USER
from mytral.routes import flask_app

NAME_ENTITY = "Activity type"
NAME_ENTITIES = f"{NAME_ENTITY}s"

ENTITY = "activity-type"
ENTITIES = f"{ENTITY}s"

METHODS = "activity_types"

META_ACTIVITY_TYPE_CHOICES = [
    ("", "-- None --"),
    (commons.M_AT_ALPINE_SKI, commons.M_AT_ALPINE_SKI),
    (commons.M_AT_CANOEING, commons.M_AT_CANOEING),
    (commons.M_AT_GAMES, commons.M_AT_GAMES),
    (commons.M_AT_GYM, commons.M_AT_GYM),
    (commons.M_AT_HIKE, commons.M_AT_HIKE),
    (commons.M_AT_MULTISPORT, commons.M_AT_MULTISPORT),
    (commons.M_AT_PHYSIO, commons.M_AT_PHYSIO),
    (commons.M_AT_RIDE, commons.M_AT_RIDE),
    (commons.M_AT_ROW, commons.M_AT_ROW),
    (commons.M_AT_RUN, commons.M_AT_RUN),
    (commons.M_AT_SKI, commons.M_AT_SKI),
    (commons.M_AT_SWIM, commons.M_AT_SWIM),
    (commons.M_AT_RELAX, commons.M_AT_RELAX),
]

#
# CRUD: activity types - LIST, CREATE, UPDATE, DELETE
#


class JinjaTemplates:
    """Jinja templates."""

    _PREFIX = f"settings-{ENTITIES}-"

    LIST = f"{_PREFIX}list.html"
    CREATE = f"{_PREFIX}create.html"
    GET = f"{_PREFIX}get.html"
    UPDATE = f"{_PREFIX}update.html"
    DELETE = f"{_PREFIX}delete.html"


#
# forms
#


class CreateForm(flask_wtf.FlaskForm):
    name = wtforms.StringField(
        label="",
        validators=[validators.DataRequired(), validators.Length(min=1, max=30)],
    )

    is_distance = wtforms.BooleanField(
        label="",
        default=False,
    )
    is_exercise = wtforms.BooleanField(
        label="",
        default=False,
    )
    is_regen = wtforms.BooleanField(
        label="",
        default=False,
    )
    is_meta = wtforms.BooleanField(
        label="",
        default=False,
    )
    is_built_in = wtforms.BooleanField(
        label="",
        default=False,
    )

    emoji = wtforms.StringField(
        label="",
        validators=[validators.Length(min=0, max=2)],
        default="",
    )
    color = wtforms.StringField(
        label="",
        validators=[validators.Length(min=0, max=15)],
        default="w3-white",
    )

    meta_activity_type = wtforms.SelectField(
        label="",
        choices=META_ACTIVITY_TYPE_CHOICES,
        validators=[validators.Optional()],
        default="",
    )

    count = wtforms.IntegerField(
        label="",
        validators=[validators.NumberRange(0, 50_000)],
        default=0,
    )

    # key is handled by the backend

    submit = wtforms.SubmitField("Create")


class UpdateForm(CreateForm):
    submit = wtforms.SubmitField("Save")


class DeleteActivityTypeForm(flask_wtf.FlaskForm):
    submit = wtforms.SubmitField("Delete")


#
# routes
#


@flask_app.route(f"/settings/{ENTITIES}", methods=["GET", "POST"])
def settings_activity_types_list():
    """List:

    - HTTP GET: show the list of entries.

    Links to the actions from the listing:

    - CREATE: HTTP GET /[entity]s/create
      ... show form to create the entity.
    - UPDATE: HTTP GET /[entity]s//<key>/update
      ... show form to update the entity.
    - DELETE: HTTP GET /[entity]s/<key>/delete
      ... show form to delete the entity.

    """
    user_id = flask.session.get(COOKIE_USER)
    if not user_id:
        return flask.redirect(flask.url_for("login"))

    if flask.request.method == "GET":
        # ensure that the activities are cached -> statistics are available
        ds.activities_stats(
            user_id=user_id,
            dataset_name=ds.profile(user_id).dataset_name,
            include_meta=True,
        )

        # get activity types stats from cache
        activity_types_stats = ds.activity_types_stats(
            user_id=user_id,
            dataset_name=ds.profile(user_id).dataset_name,
        )

        entities = ds.list_activity_types(
            user_id=user_id, dataset_name=ds.profile(user_id).dataset_name
        )

        # sort activity_types_by_key by count (descending)
        sorted_items = sorted(
            entities.activity_types_by_key.items(),
            key=lambda item: (
                activity_types_stats.stats(item[0]).count
                if activity_types_stats.stats(item[0])
                else 0
            ),
            reverse=True,
        )
        entities.activity_types_by_key = dict(sorted_items)

        aspect_arg = flask.request.args.get("aspect")
        if aspect_arg:  # chart
            from mytral import charts
            from mytral.routes import COOKIE_MOBILE

            activities = ds.list_activities(
                user_id=user_id,
                dataset_name=ds.profile(user_id).dataset_name,
                skip_meta=False,
            )

            script, div = charts.activity_types_in_time(
                activity_types=entities,
                activities=activities,
                is_mobile_view=bool(flask.session.get(COOKIE_MOBILE)),
            )

            return flask.render_template(
                JinjaTemplates.LIST,
                ff=ff,
                user_profile=ds.profile(user_id),
                entities=entities,
                activity_types_stats=activity_types_stats,
                script=script,
                div=div,
            )
        else:  # list
            return flask.render_template(
                JinjaTemplates.LIST,
                ff=ff,
                user_profile=ds.profile(user_id),
                entities=entities,
                activity_types_stats=activity_types_stats,
            )

    else:
        flask.flash(
            message=f"{NAME_ENTITY} settings error - unsupported HTTP method",
            category="error",
        )
        return flask.redirect(flask.url_for("home"))


@flask_app.route(f"/settings/{ENTITIES}/create", methods=["GET", "POST"])
def settings_activity_types_create():
    """Create:

    - HTTP GET: show form to create entity.
    - HTTP POST: actually create the entity.

    """
    user_id = flask.session.get(COOKIE_USER)
    if not user_id:
        return flask.redirect(flask.url_for("login"))

    if flask.request.method == "GET":
        form = UpdateForm()

        return flask.render_template(
            JinjaTemplates.CREATE,
            ff=ff,
            user_profile=ds.profile(user_id),
            form=form,
            selected_muscles=[],
            selected_muscles_secondary=[],
            all_muscle_groups=mg.MUSCLE_GROUPS,
        )

    elif flask.request.method == "POST":
        form = UpdateForm()
        if form.validate_on_submit():
            muscle_groups_csv = flask.request.form.get("muscle_groups", "")
            muscle_groups_list = mg.parse_muscle_groups_csv(muscle_groups_csv)
            muscle_groups_secondary_csv = flask.request.form.get(
                "muscle_groups_secondary", ""
            )
            muscle_groups_secondary_list = mg.parse_muscle_groups_csv(
                muscle_groups_secondary_csv
            )
            entity = user_settings.ActivityType(
                name=form.name.data,
                is_distance=form.is_distance.data,
                is_exercise=form.is_exercise.data,
                is_regen=form.is_regen.data,
                is_meta=form.is_meta.data,
                is_built_in=False,  # activity created by user cannot be built-in
                emoji=form.emoji.data,
                color=form.color.data,
                meta_activity_type=form.meta_activity_type.data or "",
                muscle_groups=muscle_groups_list,
                muscle_groups_secondary=muscle_groups_secondary_list,
                # key is assigned by the backend
            )

            ds.create_activity_type(user_id=user_id, activity_type=entity)

            return flask.redirect(flask.url_for(f"settings_{METHODS}_list"))

        flask.flash(
            message=f"{NAME_ENTITY} create error - form validation error",
            category="error",
        )

    else:
        flask.flash(
            message=f"{NAME_ENTITY} create error - unsupported HTTP method",
            category="error",
        )

    return flask.redirect(flask.url_for(f"settings_{METHODS}_list"))


@flask_app.route(f"/settings/{ENTITIES}/<key>", methods=["GET"])
def settings_activity_types_get(key: str):
    """Get (read-only detail view) of a single activity type."""
    user_id = flask.session.get(COOKIE_USER)
    if not user_id:
        return flask.redirect(flask.url_for("login"))

    try:
        entity = ds.get_activity_type(user_id=user_id, key=key)
    except Exception as e:
        flask.flash(
            message=(
                f"{NAME_ENTITY} error - unable to get {NAME_ENTITY.lower()} "
                f"with key {key}: {e}"
            ),
            category="error",
        )
        return flask.redirect(flask.url_for(f"settings_{METHODS}_list"))

    highlights: dict[str, str] = {}
    for muscle in entity.muscle_groups or []:
        highlights[muscle] = "state-active"
    for muscle in entity.muscle_groups_secondary or []:
        if muscle not in highlights:
            highlights[muscle] = "state-secondary"

    return flask.render_template(
        JinjaTemplates.GET,
        ff=ff,
        user_profile=ds.profile(user_id),
        entity=entity,
        key=key,
        highlights=highlights,
    )


@flask_app.route(f"/settings/{ENTITIES}/<key>/update", methods=["GET", "POST"])
def settings_activity_types_update(key: str):
    """Update entity:

    - HTTP GET: show form to update entity.
    - HTTP POST: actually update entity.

    """
    user_id = flask.session.get(COOKIE_USER)
    if not user_id:
        return flask.redirect(flask.url_for("login"))

    try:
        entity = ds.get_activity_type(user_id=user_id, key=key)
    except Exception as e:
        flask.flash(
            message=(
                f"{NAME_ENTITY} update error - unable to get {NAME_ENTITY.lower()} "
                f"with key {key}: {e}"
            ),
            category="error",
        )
        return flask.redirect(flask.url_for(f"settings_{METHODS}_list"))

    if flask.request.method == "GET":
        form = UpdateForm()
        form.name.data = entity.name
        form.is_distance.data = entity.is_distance
        form.is_exercise.data = entity.is_exercise
        form.is_regen.data = entity.is_regen
        form.is_meta.data = entity.is_meta
        form.is_built_in.data = entity.is_built_in
        form.emoji.data = entity.emoji
        form.color.data = entity.color
        form.meta_activity_type.data = entity.meta_activity_type
        form.count.data = entity.count

        return flask.render_template(
            JinjaTemplates.UPDATE,
            ff=ff,
            user_profile=ds.profile(user_id),
            form=form,
            key=key,
            selected_muscles=entity.muscle_groups,
            selected_muscles_secondary=entity.muscle_groups_secondary,
            all_muscle_groups=mg.MUSCLE_GROUPS,
        )

    elif flask.request.method == "POST":
        form = UpdateForm()
        if form.validate_on_submit():
            muscle_groups_csv = flask.request.form.get("muscle_groups", "")
            muscle_groups_list = mg.parse_muscle_groups_csv(muscle_groups_csv)
            muscle_groups_secondary_csv = flask.request.form.get(
                "muscle_groups_secondary", ""
            )
            muscle_groups_secondary_list = mg.parse_muscle_groups_csv(
                muscle_groups_secondary_csv
            )
            entity.name = form.name.data or ""
            entity.is_distance = form.is_distance.data
            entity.is_exercise = form.is_exercise.data
            entity.is_regen = form.is_regen.data
            entity.is_meta = form.is_meta.data
            entity.is_built_in = form.is_built_in.data
            entity.emoji = form.emoji.data
            entity.color = form.color.data
            entity.meta_activity_type = form.meta_activity_type.data or ""
            entity.count = form.count.data or 0
            entity.muscle_groups = muscle_groups_list
            entity.muscle_groups_secondary = muscle_groups_secondary_list

            ds.update_activity_type(user_id=user_id, activity_type=entity)

            return flask.redirect(flask.url_for(f"settings_{METHODS}_list"))

        flask.flash(
            message=f"{NAME_ENTITY} update error - form validation error",
            category="error",
        )
        return flask.redirect(flask.url_for(f"settings_{METHODS}_list"))

    flask.flash(
        message=(
            f"{NAME_ENTITY} update error - invalid HTTP method: {flask.request.method}"
        ),
        category="error",
    )
    return flask.redirect(flask.url_for(f"settings_{METHODS}_list"))


@flask_app.route(f"/settings/{ENTITIES}/<key>/delete", methods=["GET", "POST"])
def settings_activity_types_delete(key: str):
    """Delete entity:

    - HTTP GET: Do you really want to delete entity?
    - HTTP POST: actually delete the entity.

    """
    user_id = flask.session.get(COOKIE_USER)
    if not user_id:
        return flask.redirect(flask.url_for("login"))

    form = DeleteActivityTypeForm()

    if flask.request.method == "POST":
        if form.validate_on_submit():
            try:
                ds.delete_activity_type(user_id=user_id, key=key)

                flask.flash(message=f"{NAME_ENTITY} deleted", category="success")
                return flask.redirect(flask.url_for(f"settings_{METHODS}_list"))
            except Exception as e:
                flask.flash(
                    message=(
                        f"{NAME_ENTITY} delete error - {NAME_ENTITY} key {key}: {e}"
                    ),
                    category="error",
                )
                return flask.redirect(flask.url_for(f"settings_{METHODS}_list"))

        flask.flash(
            message=f"{NAME_ENTITY} delete error - form validation error",
            category="error",
        )
        return flask.redirect(flask.url_for(f"settings_{METHODS}_list"))

    # GET
    try:
        entity = ds.get_activity_type(user_id=user_id, key=key)
    except Exception as e:
        flask.flash(
            message=(
                f"{NAME_ENTITY} delete error - unable to get {NAME_ENTITY.lower()} "
                f"with key {key}: {e}"
            ),
            category="error",
        )
        return flask.redirect(flask.url_for(f"settings_{METHODS}_list"))
    return flask.render_template(
        JinjaTemplates.DELETE,
        ff=ff,
        user_profile=ds.profile(user_id),
        form=form,
        key=key,
        name=entity.name,
    )
