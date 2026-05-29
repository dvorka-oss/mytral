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
from mytral import settings
from mytral.routes import COOKIE_USER
from mytral.routes import flask_app

NAME_ENTITY = "Component Template"
NAME_ENTITIES = f"{NAME_ENTITY}s"

ENTITY = "component-template"
ENTITIES = "component-templates"

METHODS = "component_templates"

#
# CRUD: LIST, CREATE, UPDATE, DELETE
#


class JinjaTemplates:
    """Jinja templates."""

    LIST = "settings-component-templates-list.html"
    CREATE = "settings-component-template-create.html"
    UPDATE = "settings-component-template-update.html"
    DELETE = "settings-component-template-delete.html"


#
# forms
#


class ComponentTemplateForm(flask_wtf.FlaskForm):
    """Form for creating/editing component templates."""

    name = wtforms.StringField(
        label="Name",
        description="Template name (e.g. 'Chain', 'Running Shoes')",
        validators=[validators.DataRequired(), validators.Length(max=128)],
    )
    category = wtforms.StringField(
        label="Category",
        description="Sport or equipment category (e.g. 'cycling', 'running')",
        validators=[validators.DataRequired(), validators.Length(max=64)],
    )
    default_service_km = wtforms.IntegerField(
        label="Service Interval (km)",
        description="Replace or service every X kilometers",
        validators=[validators.Optional()],
    )
    default_service_hours = wtforms.IntegerField(
        label="Service Interval (hours)",
        description="Replace or service every X hours",
        validators=[validators.Optional()],
    )
    default_service_months = wtforms.IntegerField(
        label="Service Interval (months)",
        description="Replace or service every X months",
        validators=[validators.Optional()],
    )
    notes = wtforms.TextAreaField(
        label="Notes",
        description="Additional notes about this template",
        validators=[validators.Optional(), validators.Length(max=512)],
    )
    submit = wtforms.SubmitField("Save")


class DeleteComponentTemplateForm(flask_wtf.FlaskForm):
    """Form for deleting a component template."""

    submit = wtforms.SubmitField("Delete")


#
# routes
#


@flask_app.route(f"/settings/{ENTITIES}", methods=["GET"])
def settings_component_templates_list():
    """List all user component templates."""
    user_id = flask.session.get(COOKIE_USER)
    if not user_id:
        return flask.redirect(flask.url_for("login"))

    if flask.request.method == "GET":
        return flask.render_template(
            JinjaTemplates.LIST,
            ff=ff,
            user_profile=ds.profile(user_id),
            templates=ds.list_component_templates(user_id=user_id),
        )

    flask.flash(
        message=f"{NAME_ENTITY} settings error - unsupported HTTP method",
        category="error",
    )
    return flask.redirect(flask.url_for("home"))


@flask_app.route(f"/settings/{ENTITIES}/create", methods=["GET", "POST"])
def settings_component_template_create():
    """Create a new component template."""
    user_id = flask.session.get(COOKIE_USER)
    if not user_id:
        return flask.redirect(flask.url_for("login"))

    if flask.request.method == "GET":
        form = ComponentTemplateForm()
        return flask.render_template(
            JinjaTemplates.CREATE,
            ff=ff,
            user_profile=ds.profile(user_id),
            form=form,
        )

    elif flask.request.method == "POST":
        form = ComponentTemplateForm()
        if form.validate_on_submit():
            template = settings.ComponentTemplate(
                name=form.name.data,
                category=form.category.data,
                default_service_km=form.default_service_km.data,
                default_service_hours=form.default_service_hours.data,
                default_service_months=form.default_service_months.data,
                notes=form.notes.data or "",
            )
            ds.create_component_template(user_id=user_id, template=template)
            flask.flash(
                message=f"{NAME_ENTITY} '{template.name}' created",
                category="success",
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


@flask_app.route(f"/settings/{ENTITIES}/<key>/update", methods=["GET", "POST"])
def settings_component_template_update(key: str):
    """Update an existing component template."""
    user_id = flask.session.get(COOKIE_USER)
    if not user_id:
        return flask.redirect(flask.url_for("login"))

    template = ds.get_component_template(user_id=user_id, key=key)
    if template is None:
        flask.flash(
            message=f"{NAME_ENTITY} not found: {key}",
            category="error",
        )
        return flask.redirect(flask.url_for(f"settings_{METHODS}_list"))

    if flask.request.method == "GET":
        form = ComponentTemplateForm()
        form.name.data = template.name
        form.category.data = template.category
        form.default_service_km.data = template.default_service_km
        form.default_service_hours.data = template.default_service_hours
        form.default_service_months.data = template.default_service_months
        form.notes.data = template.notes
        return flask.render_template(
            JinjaTemplates.UPDATE,
            ff=ff,
            user_profile=ds.profile(user_id),
            form=form,
            key=key,
            template=template,
        )

    elif flask.request.method == "POST":
        form = ComponentTemplateForm()
        if form.validate_on_submit():
            template.name = form.name.data or ""
            template.category = form.category.data or ""
            template.default_service_km = form.default_service_km.data
            template.default_service_hours = form.default_service_hours.data
            template.default_service_months = form.default_service_months.data
            template.notes = form.notes.data or ""
            ds.update_component_template(user_id=user_id, template=template)
            flask.flash(
                message=f"{NAME_ENTITY} '{template.name}' updated",
                category="success",
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


@flask_app.route(f"/settings/{ENTITIES}/<key>/delete", methods=["GET", "POST"])
def settings_component_template_delete(key: str):
    """Delete a component template."""
    user_id = flask.session.get(COOKIE_USER)
    if not user_id:
        return flask.redirect(flask.url_for("login"))

    form = DeleteComponentTemplateForm()

    if flask.request.method == "POST":
        if form.validate_on_submit():
            try:
                template = ds.get_component_template(user_id=user_id, key=key)
                template_name = template.name if template else key
                ds.delete_component_template(user_id=user_id, key=key)
                flask.flash(
                    message=f"{NAME_ENTITY} '{template_name}' deleted",
                    category="success",
                )
                return flask.redirect(flask.url_for(f"settings_{METHODS}_list"))
            except Exception as e:
                flask.flash(
                    message=f"{NAME_ENTITY} delete error: {e}",
                    category="error",
                )
                return flask.redirect(flask.url_for(f"settings_{METHODS}_list"))

        flask.flash(
            message=f"{NAME_ENTITY} delete error - form validation error",
            category="error",
        )
        return flask.redirect(flask.url_for(f"settings_{METHODS}_list"))

    # GET
    template = ds.get_component_template(user_id=user_id, key=key)
    if template is None:
        flask.flash(
            message=f"{NAME_ENTITY} not found: {key}",
            category="error",
        )
        return flask.redirect(flask.url_for(f"settings_{METHODS}_list"))

    return flask.render_template(
        JinjaTemplates.DELETE,
        ff=ff,
        user_profile=ds.profile(user_id),
        form=form,
        key=key,
        template=template,
    )
