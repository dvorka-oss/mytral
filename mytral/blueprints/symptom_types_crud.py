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

NAME_ENTITY = "Symptom"
NAME_ENTITIES = f"{NAME_ENTITY}s"

ENTITY = "symptom"
ENTITIES = f"{ENTITY}s"

METHODS = "symptoms"

#
# CRUD: LIST, CREATE, UPDATE, DELETE
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


class CreateSymptomForm(flask_wtf.FlaskForm):
    name = wtforms.StringField(
        label="",
        validators=[validators.DataRequired()],
    )

    count = wtforms.IntegerField(
        label="",
        validators=[validators.NumberRange(0, 50_000)],
        default=0,
    )

    # key is handled by the backend

    submit = wtforms.SubmitField("Create")


class UpdateSymptomForm(CreateSymptomForm):
    submit = wtforms.SubmitField("Save")


class DeleteSymptomForm(flask_wtf.FlaskForm):
    submit = wtforms.SubmitField("Delete")


#
# routes
#


@flask_app.route(f"/settings/{ENTITIES}", methods=["GET", "POST"])
def settings_symptoms_list():
    """List symptoms:

    - HTTP GET: show list of symptoms.

    Links to the actions from the listing:

    - CREATE: HTTP GET /settings/symptoms/create
      ... show form to create symptoms.
    - UPDATE: HTTP GET /settings/symptoms/<key>/update
      ... show form to update symptoms.
    - DELETE: HTTP GET /settings/symptoms/<key>/delete
      ... show form to delete symptoms.

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

        # get symptoms stats from cache
        symptoms_stats = ds.symptoms_stats(
            user_id=user_id,
            dataset_name=ds.profile(user_id).dataset_name,
        )

        symptoms = ds.list_symptoms(
            user_id=user_id, dataset_name=ds.profile(user_id).dataset_name
        )

        # sort symptoms by usage count (descending)
        sorted_items = sorted(
            symptoms.symptoms_by_key.items(),
            key=lambda item: (
                symptoms_stats.stats(item[0]).count
                if symptoms_stats.stats(item[0])
                else 0
            ),
            reverse=True,
        )
        symptoms.symptoms_by_key = dict(sorted_items)

        aspect_arg = flask.request.args.get("aspect")
        if aspect_arg:  # chart
            from mytral import charts
            from mytral.routes import COOKIE_MOBILE

            activities = ds.list_activities(
                user_id=user_id,
                dataset_name=ds.profile(user_id).dataset_name,
                skip_meta=False,
            )

            script, div = charts.symptoms_in_time(
                symptoms=symptoms,
                activities=activities,
                is_mobile_view=bool(flask.session.get(COOKIE_MOBILE)),
            )

            return flask.render_template(
                JinjaTemplates.LIST,
                ff=ff,
                user_profile=ds.profile(user_id),
                symptoms=symptoms,
                symptoms_stats=symptoms_stats,
                script=script,
                div=div,
            )
        else:  # list
            return flask.render_template(
                JinjaTemplates.LIST,
                ff=ff,
                user_profile=ds.profile(user_id),
                symptoms=symptoms,
                symptoms_stats=symptoms_stats,
            )

    else:
        flask.flash(
            message="Settings error - unsupported HTTP method", category="error"
        )
        return flask.redirect(flask.url_for("home"))


@flask_app.route(f"/settings/{ENTITIES}/create", methods=["GET", "POST"])
def settings_symptoms_create():
    """Create:

    - HTTP GET: show form to create entity.
    - HTTP POST: actually create entity.

    """
    user_id = flask.session.get(COOKIE_USER)
    if not user_id:
        return flask.redirect(flask.url_for("login"))

    if flask.request.method == "GET":
        form = UpdateSymptomForm()

        return flask.render_template(
            JinjaTemplates.CREATE,
            ff=ff,
            user_profile=ds.profile(user_id),
            form=form,
            selected_body_parts=[],
        )

    elif flask.request.method == "POST":
        form = UpdateSymptomForm()
        if form.validate_on_submit():
            body_parts_csv = flask.request.form.get("body_parts", "")
            body_parts = [p for p in body_parts_csv.split(",") if p.strip()]
            entity = user_settings.Symptom(
                name=form.name.data,
                body_parts=body_parts,
            )

            ds.create_symptom(user_id=user_id, symptom=entity)

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
def settings_symptoms_update(key: str):
    """Delete entity:

    - HTTP GET: show form to update entity.
    - HTTP POST: actually update entity.

    """
    user_id = flask.session.get(COOKIE_USER)
    if not user_id:
        return flask.redirect(flask.url_for("login"))

    try:
        entity = ds.get_symptom(user_id=user_id, key=key)
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
        form = UpdateSymptomForm()
        form.name.data = entity.name

        return flask.render_template(
            JinjaTemplates.UPDATE,
            ff=ff,
            user_profile=ds.profile(user_id),
            form=form,
            key=key,
            selected_body_parts=entity.body_parts,
        )

    elif flask.request.method == "POST":
        form = UpdateSymptomForm()
        if form.validate_on_submit():
            body_parts_csv = flask.request.form.get("body_parts", "")
            entity.name = form.name.data or ""
            entity.body_parts = [p for p in body_parts_csv.split(",") if p.strip()]

            ds.update_symptom(user_id=user_id, symptom=entity)

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


@flask_app.route(f"/settings/{ENTITIES}/<key>", methods=["GET"])
def settings_symptoms_get(key: str):
    """Get (read-only detail view) of a single symptom."""
    user_id = flask.session.get(COOKIE_USER)
    if not user_id:
        return flask.redirect(flask.url_for("login"))

    try:
        entity = ds.get_symptom(user_id=user_id, key=key)
    except Exception as e:
        flask.flash(
            message=(
                f"{NAME_ENTITY} error - unable to get {NAME_ENTITY.lower()} "
                f"with key {key}: {e}"
            ),
            category="error",
        )
        return flask.redirect(flask.url_for(f"settings_{METHODS}_list"))

    symptoms_stats = ds.symptoms_stats(
        user_id=user_id,
        dataset_name=ds.profile(user_id).dataset_name,
    )
    stat = symptoms_stats.stats(key)
    count = stat.count if stat else 0

    return flask.render_template(
        JinjaTemplates.GET,
        ff=ff,
        user_profile=ds.profile(user_id),
        entity=entity,
        key=key,
        count=count,
    )


@flask_app.route(f"/settings/{ENTITIES}/<key>/delete", methods=["GET", "POST"])
def settings_symptoms_delete(key: str):
    """Delete:

    - HTTP GET: Do you really want to delete entity?
    - HTTP POST: actually delete entity.

    """
    user_id = flask.session.get(COOKIE_USER)
    if not user_id:
        return flask.redirect(flask.url_for("login"))

    form = DeleteSymptomForm()

    if flask.request.method == "POST":
        if form.validate_on_submit():
            try:
                ds.delete_symptom(user_id=user_id, key=key)

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
        entity = ds.get_symptom(user_id=user_id, key=key)
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
