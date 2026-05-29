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
from mytral import ff
from mytral import settings as user_settings
from mytral.routes import COOKIE_USER
from mytral.routes import flask_app

NAME_ENTITY = "Lap"
NAME_ENTITIES = f"{NAME_ENTITY}s"

ENTITY = "lap"
ENTITIES = f"{ENTITY}s"

METHODS = "laps"

#
# CRUD: LIST, CREATE, UPDATE, DELETE
#


class JinjaTemplates:
    """Jinja templates."""

    _PREFIX = f"settings-{ENTITIES}-"

    LIST = f"{_PREFIX}list.html"
    CREATE = f"{_PREFIX}create.html"
    UPDATE = f"{_PREFIX}update.html"
    DELETE = f"{_PREFIX}delete.html"


#
# forms
#


class CreateLapTypeForm(flask_wtf.FlaskForm):
    name = wtforms.StringField(
        label="Lap name",
        validators=[validators.DataRequired()],
    )

    description = wtforms.TextAreaField(
        label="Description",
        description="Lap/route description. Supports Markdown formatting.",
        validators=[validators.Optional()],
    )

    default_distance = wtforms.IntegerField(
        label="Default distance (m)",
        validators=[validators.NumberRange(0, 100_000)],
        default=0,
    )

    default_duration_hours = wtforms.IntegerField(
        render_kw={"placeholder": "0"},
        label="Hours",
        description="Default duration in hours (0-23)",
        validators=[validators.NumberRange(0, 23)],
        default=0,
    )
    default_duration_minutes = wtforms.IntegerField(
        render_kw={"placeholder": "0"},
        label="Minutes",
        description="Default duration in minutes (0-59)",
        validators=[validators.NumberRange(0, 59)],
        default=0,
    )
    default_duration_seconds = wtforms.IntegerField(
        render_kw={"placeholder": "0"},
        label="Seconds",
        description="Default duration in seconds (0-59)",
        validators=[validators.NumberRange(0, 59)],
        default=0,
    )

    count = wtforms.IntegerField(
        label="",
        validators=[validators.NumberRange(0, 50_000)],
        default=0,
    )

    # key is handled by the backend

    submit = wtforms.SubmitField("Create")


class UpdateLapTypeForm(CreateLapTypeForm):
    submit = wtforms.SubmitField("Save")


class DeleteLapTypeForm(flask_wtf.FlaskForm):
    submit = wtforms.SubmitField("Delete")


#
# routes
#


@flask_app.route(f"/settings/{METHODS}", methods=["GET", "POST"])
def settings_laps_list():
    """List lap types."""
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

        # get laps stats from cache
        laps_stats = ds.laps_stats(
            user_id=user_id,
            dataset_name=ds.profile(user_id).dataset_name,
        )

        laps = ds.list_laps(
            user_id=user_id, dataset_name=ds.profile(user_id).dataset_name
        )

        aspect_arg = flask.request.args.get("aspect")
        if aspect_arg:  # chart
            from mytral import charts
            from mytral.routes import COOKIE_MOBILE

            activities = ds.list_activities(
                user_id=user_id,
                dataset_name=ds.profile(user_id).dataset_name,
                skip_meta=False,
            )

            script, div = charts.laps_in_time(
                laps=laps,
                activities=activities,
                is_mobile_view=bool(flask.session.get(COOKIE_MOBILE)),
            )

            return flask.render_template(
                JinjaTemplates.LIST,
                ff=ff,
                user_profile=ds.profile(user_id),
                laps=laps,
                laps_stats=laps_stats,
                script=script,
                div=div,
            )
        else:  # list
            return flask.render_template(
                JinjaTemplates.LIST,
                ff=ff,
                user_profile=ds.profile(user_id),
                laps=laps,
                laps_stats=laps_stats,
            )
    else:
        flask.flash(
            message="Settings error - unsupported HTTP method", category="error"
        )
        return flask.redirect(flask.url_for("home"))


@flask_app.route(f"/settings/{METHODS}/create", methods=["GET", "POST"])
def settings_laps_create():
    """Create lap type."""
    user_id = flask.session.get(COOKIE_USER)
    if not user_id:
        return flask.redirect(flask.url_for("login"))

    if flask.request.method == "GET":
        form = CreateLapTypeForm()

        return flask.render_template(
            JinjaTemplates.CREATE,
            ff=ff,
            user_profile=ds.profile(user_id),
            form=form,
        )

    elif flask.request.method == "POST":
        form = CreateLapTypeForm()
        if form.validate_on_submit():
            default_duration = (
                (form.default_duration_hours.data or 0) * 3600
                + (form.default_duration_minutes.data or 0) * 60
                + (form.default_duration_seconds.data or 0)
            )
            entity = user_settings.Lap(
                name=form.name.data,
                description=form.description.data,
                default_distance=form.default_distance.data,
                default_duration=default_duration,
            )

            ds.create_lap(
                user_id=user_id,
                lap=entity,
                dataset_name=ds.profile(user_id).dataset_name,
            )

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


@flask_app.route(f"/settings/{METHODS}/<key>/update", methods=["GET", "POST"])
def settings_laps_update(key: str):
    """Update lap type."""
    user_id = flask.session.get(COOKIE_USER)
    if not user_id:
        return flask.redirect(flask.url_for("login"))

    try:
        entity = ds.get_lap(
            user_id=user_id, key=key, dataset_name=ds.profile(user_id).dataset_name
        )
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
        form = UpdateLapTypeForm()

        form.name.data = entity.name
        form.description.data = entity.description
        form.default_distance.data = entity.default_distance
        _total = entity.default_duration or 0
        form.default_duration_hours.data = _total // 3600
        form.default_duration_minutes.data = (_total % 3600) // 60
        form.default_duration_seconds.data = _total % 60

        return flask.render_template(
            JinjaTemplates.UPDATE,
            ff=ff,
            user_profile=ds.profile(user_id),
            form=form,
            key=key,
        )

    elif flask.request.method == "POST":
        form = UpdateLapTypeForm()
        if form.validate_on_submit():
            entity.name = form.name.data or ""
            entity.description = form.description.data or ""
            entity.default_distance = form.default_distance.data or 0
            entity.default_duration = (
                (form.default_duration_hours.data or 0) * 3600
                + (form.default_duration_minutes.data or 0) * 60
                + (form.default_duration_seconds.data or 0)
            )

            ds.update_lap(
                user_id=user_id,
                lap=entity,
                dataset_name=ds.profile(user_id).dataset_name,
            )

            return flask.redirect(flask.url_for(f"settings_{METHODS}_list"))

        flask.flash(
            message=f"{NAME_ENTITY} update error - form validation error",
            category="error",
        )

    else:
        flask.flash(
            message=f"{NAME_ENTITY} update error - unsupported HTTP method",
            category="error",
        )

    return flask.redirect(flask.url_for(f"settings_{METHODS}_list"))


@flask_app.route(f"/settings/{METHODS}/<key>/delete", methods=["GET", "POST"])
def settings_laps_delete(key: str):
    """Delete lap type."""
    user_id = flask.session.get(COOKIE_USER)
    if not user_id:
        return flask.redirect(flask.url_for("login"))

    form = DeleteLapTypeForm()

    if flask.request.method == "POST":
        if form.validate_on_submit():
            try:
                ds.delete_lap(
                    user_id=user_id,
                    key=key,
                    dataset_name=ds.profile(user_id).dataset_name,
                )
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
        entity = ds.get_lap(
            user_id=user_id, key=key, dataset_name=ds.profile(user_id).dataset_name
        )
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
