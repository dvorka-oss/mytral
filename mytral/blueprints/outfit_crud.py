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

NAME_ENTITY = "Outfit"
NAME_ENTITIES = f"{NAME_ENTITY}s"

ENTITY = "outfit"
ENTITIES = f"{ENTITY}s"

METHODS = f"{ENTITY}s"

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


class CreateForm(flask_wtf.FlaskForm):
    name = wtforms.StringField(
        label="",
        validators=[validators.DataRequired()],
    )

    activity_type = wtforms.SelectField(
        # choices & default are dynamically set in the view
        label="",
        validators=[validators.DataRequired()],
        validate_choice=False,
    )

    description = wtforms.TextAreaField(
        label="Description",
        description="Outfit description. Supports Markdown formatting.",
        validators=[validators.Optional()],
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


class DeleteForm(flask_wtf.FlaskForm):
    submit = wtforms.SubmitField("Delete")


#
# routes
#


@flask_app.route(f"/settings/{ENTITIES}", methods=["GET", "POST"])
def settings_outfits_list():
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
        dataset_name = ds.profile(user_id).dataset_name

        entities = ds.list_outfits(user_id=user_id, dataset_name=dataset_name)

        # sort outfits_by_key by count (descending)
        sorted_items = sorted(
            entities.outfits_by_key.items(),
            key=lambda item: item[1].count,
            reverse=True,
        )
        entities.outfits_by_key = dict(sorted_items)

        aspect_arg = flask.request.args.get("aspect")
        if aspect_arg:  # chart
            from mytral import charts
            from mytral.routes import COOKIE_MOBILE

            activities = ds.list_activities(
                user_id=user_id,
                dataset_name=dataset_name,
                skip_meta=False,
            )

            script, div = charts.outfits_in_time(
                outfits=entities,
                activities=activities,
                is_mobile_view=bool(flask.session.get(COOKIE_MOBILE)),
            )

            return flask.render_template(
                JinjaTemplates.LIST,
                ff=ff,
                user_profile=ds.profile(user_id),
                outfits=entities,
                script=script,
                div=div,
            )
        else:  # list
            return flask.render_template(
                JinjaTemplates.LIST,
                ff=ff,
                user_profile=ds.profile(user_id),
                outfits=entities,
            )

    else:
        flask.flash(
            message=f"{NAME_ENTITY} settings error - unsupported HTTP method",
            category="error",
        )
        return flask.redirect(flask.url_for("home"))


@flask_app.route(f"/settings/{ENTITIES}/create", methods=["GET", "POST"])
def settings_outfit_create():
    """Create:

    - HTTP GET: show form to create entity.
    - HTTP POST: actually create the entity.

    """
    user_id = flask.session.get(COOKIE_USER)
    if not user_id:
        return flask.redirect(flask.url_for("login"))

    if flask.request.method == "GET":
        form = CreateForm()

        activity_choices = ds.list_activity_types(user_id).choices()
        form.activity_type.choices = activity_choices
        form.activity_type.default = activity_choices[0][0]

        return flask.render_template(
            JinjaTemplates.CREATE,
            ff=ff,
            user_profile=ds.profile(user_id),
            form=form,
        )

    elif flask.request.method == "POST":
        form = CreateForm()
        if form.validate_on_submit():
            entity = user_settings.Outfit(
                name=form.name.data,
                activity_type=form.activity_type.data,
                description=form.description.data,
                count=form.count.data,
                # key is assigned by the backend
            )

            ds.create_outfit(user_id=user_id, outfit=entity)

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


@flask_app.route(f"/settings/{ENTITIES}/<key>/update", methods=["GET", "POST"])
def settings_outfit_update(key: str):
    """Update entity:

    - HTTP GET: show form to update entity.
    - HTTP POST: actually update entity.

    """
    user_id = flask.session.get(COOKIE_USER)
    if not user_id:
        return flask.redirect(flask.url_for("login"))

    try:
        entity = ds.get_outfit(user_id=user_id, key=key)
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

        activity_choices = ds.list_activity_types(user_id).choices()
        form.activity_type.choices = activity_choices
        form.activity_type.default = activity_choices[0][0]
        form.activity_type.data = entity.activity_type

        form.name.data = entity.name
        form.description.data = entity.description
        form.count.data = entity.count

        return flask.render_template(
            JinjaTemplates.UPDATE,
            ff=ff,
            user_profile=ds.profile(user_id),
            form=form,
            key=key,
        )

    elif flask.request.method == "POST":
        form = UpdateForm()
        if form.validate_on_submit():
            entity.name = form.name.data or ""
            entity.activity_type = form.activity_type.data or ""
            entity.description = form.description.data or ""
            entity.count = form.count.data or 0

            ds.update_outfit(user_id=user_id, outfit=entity)

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


@flask_app.route(f"/settings/{ENTITIES}/<key>/delete", methods=["GET", "POST"])
def settings_outfit_delete(key: str):
    """Delete entity:

    - HTTP GET: Do you really want to delete entity?
    - HTTP POST: actually delete entity.

    """
    user_id = flask.session.get(COOKIE_USER)
    if not user_id:
        return flask.redirect(flask.url_for("login"))

    form = DeleteForm()

    if flask.request.method == "POST":
        if form.validate_on_submit():
            try:
                ds.delete_outfit(user_id=user_id, key=key)

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
        entity = ds.get_outfit(user_id=user_id, key=key)
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
