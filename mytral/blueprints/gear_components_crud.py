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
from datetime import datetime

import flask
import flask_wtf
import wtforms
from wtforms import validators

from mytral import app_user_ds as ds
from mytral import ff
from mytral import settings
from mytral.routes import COOKIE_USER
from mytral.routes import flask_app

NAME_ENTITY = "Gear component"
NAME_ENTITIES = f"{NAME_ENTITY}s"

ENTITY = "component"
ENTITIES = f"{ENTITY}s"

METHODS = "components"

#
# forms
#


class ComponentForm(flask_wtf.FlaskForm):
    """Form for creating/editing components."""

    template = wtforms.SelectField(
        label="Template (optional)",
        description="Select a pre-configured component template",
        choices=[("", "-- No template --")],
        validators=[validators.Optional()],
        validate_choice=False,
    )
    name = wtforms.StringField(
        label="Name",
        description="Component name (e.g., 'Chain', 'Fork', 'Front Tire')",
        validators=[validators.DataRequired()],
    )
    cost = wtforms.FloatField(
        label="Cost",
        description="Purchase cost",
        validators=[validators.Optional()],
        default=0.0,
    )
    installed_date = wtforms.DateField(
        label="Installed Date",
        description="When was this component installed?",
        validators=[validators.DataRequired()],
        default=datetime.now().date,
    )
    next_service_km = wtforms.IntegerField(
        label="Service Interval (km)",
        description="Service every X kilometers (leave empty if not tracking by km)",
        validators=[validators.Optional()],
    )
    next_service_hours = wtforms.IntegerField(
        label="Service Interval (hours)",
        description="Service every X hours (leave empty if not tracking by hours)",
        validators=[validators.Optional()],
    )
    replaces_component = wtforms.SelectField(
        label="Replaces Component",
        description="Select component this one replaces (will retire the old one)",
        choices=[("", "-- None --")],
        validators=[validators.Optional()],
        validate_choice=False,
    )
    notes = wtforms.TextAreaField(
        label="Notes",
        description="Additional notes about this component",
        validators=[validators.Optional()],
    )
    submit = wtforms.SubmitField("Save Component")


class ComponentServiceForm(flask_wtf.FlaskForm):
    """Form for recording component service."""

    service_date = wtforms.DateField(
        label="Service Date",
        validators=[validators.DataRequired()],
        default=datetime.now().date,
    )
    service_type = wtforms.SelectField(
        label="Service Type",
        choices=[
            ("replacement", "Replacement"),
            ("service", "Service"),
            ("inspection", "Inspection"),
        ],
        validators=[validators.DataRequired()],
    )
    cost = wtforms.FloatField(
        label="Service Cost",
        validators=[validators.Optional()],
        default=0.0,
    )
    notes = wtforms.TextAreaField(
        label="Notes",
        validators=[validators.Optional()],
    )
    reset_counter = wtforms.BooleanField(
        label="Reset service counter",
        default=True,
    )
    submit = wtforms.SubmitField("Record Service")


class DeleteComponentForm(flask_wtf.FlaskForm):
    """Form for deleting a component."""

    submit = wtforms.SubmitField("Delete")


#
# routes
#


@flask_app.route(
    f"/settings/gears/<gear_key>/{ENTITIES}/create", methods=["GET", "POST"]
)
def settings_gear_component_create(gear_key: str):
    """Create a component for a gear."""
    user_id = flask.session.get(COOKIE_USER)
    if not user_id:
        return flask.redirect(flask.url_for("login"))

    try:
        gear = ds.get_gear(
            user_id=user_id, key=gear_key, dataset_name=ds.profile(user_id).dataset_name
        )
    except Exception as e:
        flask.flash(
            message=f"Gear error - unable to get gear with key {gear_key}: {e}",
            category="error",
        )
        return flask.redirect(flask.url_for("settings_gear_list"))

    if flask.request.method == "GET":
        form = ComponentForm()

        # populate template choices - show all templates grouped by category
        template_choices = [("", "-- No template --")]
        for template in ds.list_component_templates(user_id=user_id).templates:
            label = (
                f"[{template.category}] {template.name}"
                if template.category
                else template.name
            )
            template_choices.append((template.key, label))
        form.template.choices = template_choices

        # populate replaces component choices
        replaces_choices = [("", "-- None --")]
        for comp in gear.get_components():
            replaces_choices.append(
                (comp.key, f"{comp.name} (installed {comp.installed_date})")
            )
        form.replaces_component.choices = replaces_choices

        return flask.render_template(
            "settings-gear-component-create.html",
            ff=ff,
            user_profile=ds.profile(user_id),
            gear=gear,
            form=form,
        )

    elif flask.request.method == "POST":
        form = ComponentForm()
        if form.validate_on_submit():
            install_date_str = form.installed_date.data.isoformat()

            # create component
            component = settings.GearComponent(
                name=form.name.data,
                cost=form.cost.data or 0.0,
                installed_date=install_date_str,
                next_service_km=form.next_service_km.data,
                next_service_hours=form.next_service_hours.data,
                notes=form.notes.data or "",
            )

            # handle replacement: retire old component and record replacement event date
            replaces_key = form.replaces_component.data
            if replaces_key and replaces_key != "":
                component.replaces_key = replaces_key
                for c in gear.components:
                    if c.get("key") == replaces_key:
                        old_component = settings.GearComponent.from_dict(c)
                        # record the event date; km_at_service will be recomputed
                        # on page load via recompute_gear_service_intervals
                        replacement_entry = settings.ComponentServiceHistoryEntry(
                            date=install_date_str,
                            km_at_service=old_component.km_since_service,
                            hours_at_service=old_component.hours_since_service,
                            service_type="replacement",
                        )
                        if replaces_key not in gear.component_history:
                            gear.component_history[replaces_key] = []
                        gear.component_history[replaces_key].append(
                            replacement_entry.to_dict()
                        )
                        c["status"] = "retired"
                        c["replaced_by_key"] = component.key
                        break

            # add component to gear
            gear.components.append(component.to_dict())

            # initialize new component usage at 0 (component-relative baseline);
            # recompute_gear_service_intervals will refine this from
            # activity data on the next page load
            for c in gear.components:
                if c.get("key") == component.key:
                    c["last_service_km"] = 0.0
                    c["last_service_hours"] = 0.0
                    c["distance_meters"] = 0
                    c["time_seconds"] = 0
                    break

            # recalculate TCoO
            gear.recalculate_tcoo()

            # save
            ds.update_gear(
                user_id=user_id,
                gear=gear,
                dataset_name=ds.profile(user_id).dataset_name,
            )

            flask.flash(
                message=f"Component '{component.name}' created", category="success"
            )
            return flask.redirect(flask.url_for("settings_gear_update", key=gear_key))

        flask.flash(
            message="Component create error - form validation error", category="error"
        )

    else:
        flask.flash(
            message=f"{NAME_ENTITY} create error - unsupported HTTP method",
            category="error",
        )

    return flask.redirect(flask.url_for("settings_gear_update", key=gear_key))


@flask_app.route(
    f"/settings/gears/<gear_key>/{ENTITIES}/<component_key>/update",
    methods=["GET", "POST"],
)
def settings_gear_component_update(gear_key: str, component_key: str):
    """Update a component."""
    user_id = flask.session.get(COOKIE_USER)
    if not user_id:
        return flask.redirect(flask.url_for("login"))

    try:
        gear = ds.get_gear(
            user_id=user_id, key=gear_key, dataset_name=ds.profile(user_id).dataset_name
        )
        component = gear.get_component(component_key)
        if not component:
            raise ValueError(f"Component {component_key} not found")
    except Exception as e:
        flask.flash(message=f"Component error: {e}", category="error")
        return flask.redirect(flask.url_for("settings_gear_update", key=gear_key))

    if flask.request.method == "GET":
        form = ComponentForm()

        # populate form with component data
        form.name.data = component.name
        form.cost.data = component.cost
        form.installed_date.data = (
            datetime.fromisoformat(component.installed_date).date()
            if component.installed_date
            else None
        )
        form.next_service_km.data = component.next_service_km
        form.next_service_hours.data = component.next_service_hours
        form.notes.data = component.notes

        # hide template field (not needed on update)
        form.template.render_kw = {"style": "display:none;"}
        form.template.choices = [("", "")]

        # populate replaces component choices (all components except this one)
        replaces_choices = [("", "-- None --")]
        for comp in gear.get_components(include_retired=True):
            if comp.key != component_key:
                replaces_choices.append(
                    (comp.key, f"{comp.name} (installed {comp.installed_date})")
                )
        form.replaces_component.choices = replaces_choices
        form.replaces_component.data = component.replaces_key or ""

        return flask.render_template(
            "settings-gear-component-update.html",
            ff=ff,
            user_profile=ds.profile(user_id),
            gear=gear,
            component=component,
            form=form,
        )

    elif flask.request.method == "POST":
        form = ComponentForm()
        # must set choices before validation
        form.template.choices = [("", "")]
        replaces_choices = [("", "-- None --")]
        for comp in gear.get_components(include_retired=True):
            if comp.key != component_key:
                replaces_choices.append(
                    (comp.key, f"{comp.name} (installed {comp.installed_date})")
                )
        form.replaces_component.choices = replaces_choices

        if form.validate_on_submit():
            new_replaces_key = form.replaces_component.data or ""

            # update component in gear.components list
            for c in gear.components:
                if c.get("key") == component_key:
                    c["name"] = form.name.data or ""
                    c["cost"] = form.cost.data or 0.0
                    c["installed_date"] = (
                        form.installed_date.data.isoformat()
                        if form.installed_date.data
                        else ""
                    )
                    c["next_service_km"] = form.next_service_km.data
                    c["next_service_hours"] = form.next_service_hours.data
                    c["notes"] = form.notes.data or ""
                    old_replaces_key = c.get("replaces_key", "")

                    if new_replaces_key != old_replaces_key:
                        # unlink old predecessor
                        if old_replaces_key:
                            for prev in gear.components:
                                if prev.get("key") == old_replaces_key:
                                    prev.pop("replaced_by_key", None)
                                    prev["status"] = "active"
                                    break
                        # link new predecessor
                        if new_replaces_key:
                            for prev in gear.components:
                                if prev.get("key") == new_replaces_key:
                                    prev["replaced_by_key"] = component_key
                                    prev["status"] = "retired"
                                    break
                        c["replaces_key"] = new_replaces_key
                    break

            # recalculate TCoO
            gear.recalculate_tcoo()

            # save
            ds.update_gear(
                user_id=user_id,
                gear=gear,
                dataset_name=ds.profile(user_id).dataset_name,
            )

            flask.flash(
                message=f"Component '{form.name.data}' updated", category="success"
            )
            return flask.redirect(flask.url_for("settings_gear_update", key=gear_key))

        flask.flash(
            message="Component update error - form validation error", category="error"
        )

    else:
        flask.flash(
            message=f"{NAME_ENTITY} update error - unsupported HTTP method",
            category="error",
        )

    return flask.redirect(flask.url_for("settings_gear_update", key=gear_key))


@flask_app.route(
    f"/settings/gears/<gear_key>/{ENTITIES}/<component_key>/delete",
    methods=["GET", "POST"],
)
def settings_gear_component_delete(gear_key: str, component_key: str):
    """Delete a component."""
    user_id = flask.session.get(COOKIE_USER)
    if not user_id:
        return flask.redirect(flask.url_for("login"))

    try:
        gear = ds.get_gear(
            user_id=user_id, key=gear_key, dataset_name=ds.profile(user_id).dataset_name
        )
        component = gear.get_component(component_key)
        if not component:
            raise ValueError(f"Component {component_key} not found")
    except Exception as e:
        flask.flash(message=f"Component error: {e}", category="error")
        return flask.redirect(flask.url_for("settings_gear_update", key=gear_key))

    form = DeleteComponentForm()

    if flask.request.method == "POST":
        if form.validate_on_submit():
            # remove component
            gear.components = [
                c for c in gear.components if c.get("key") != component_key
            ]

            # remove history
            if component_key in gear.component_history:
                del gear.component_history[component_key]

            # recalculate TCoO
            gear.recalculate_tcoo()

            # save
            ds.update_gear(
                user_id=user_id,
                gear=gear,
                dataset_name=ds.profile(user_id).dataset_name,
            )

            flask.flash(
                message=f"Component '{component.name}' deleted", category="success"
            )
            return flask.redirect(flask.url_for("settings_gear_update", key=gear_key))

        flask.flash(
            message="Component delete error - form validation error", category="error"
        )
        return flask.redirect(flask.url_for("settings_gear_update", key=gear_key))

    # GET
    return flask.render_template(
        "settings-gear-component-delete.html",
        ff=ff,
        user_profile=ds.profile(user_id),
        gear=gear,
        component=component,
        form=form,
    )


@flask_app.route(
    f"/settings/gears/<gear_key>/{ENTITIES}/<component_key>/service",
    methods=["GET", "POST"],
)
def settings_gear_component_service(gear_key: str, component_key: str):
    """Record service for a component."""
    user_id = flask.session.get(COOKIE_USER)
    if not user_id:
        return flask.redirect(flask.url_for("login"))

    try:
        gear = ds.get_gear(
            user_id=user_id, key=gear_key, dataset_name=ds.profile(user_id).dataset_name
        )
        component = gear.get_component(component_key)
        if not component:
            raise ValueError(f"Component {component_key} not found")
    except Exception as e:
        flask.flash(message=f"Component error: {e}", category="error")
        return flask.redirect(flask.url_for("settings_gear_update", key=gear_key))

    if flask.request.method == "GET":
        form = ComponentServiceForm()

        return flask.render_template(
            "settings-gear-component-service.html",
            ff=ff,
            user_profile=ds.profile(user_id),
            gear=gear,
            component=component,
            form=form,
        )

    elif flask.request.method == "POST":
        form = ComponentServiceForm()
        if form.validate_on_submit():
            service_date_str = form.service_date.data.isoformat()

            # record event date, type, cost and notes; km_at_service will be
            # recomputed from activity data by recompute_gear_service_intervals
            # whenever the gear detail page is loaded
            history_entry = settings.ComponentServiceHistoryEntry(
                date=service_date_str,
                km_at_service=component.km_since_service,
                hours_at_service=component.hours_since_service,
                service_type=form.service_type.data,
                cost=form.cost.data or 0.0,
                notes=form.notes.data or "",
            )

            # add to history
            if component_key not in gear.component_history:
                gear.component_history[component_key] = []
            gear.component_history[component_key].append(history_entry.to_dict())

            # update component service counters
            if form.reset_counter.data:
                for c in gear.components:
                    if c.get("key") == component_key:
                        c["last_service_km"] = component.distance_km
                        c["last_service_hours"] = component.time_hours
                        c["last_service_date"] = service_date_str
                        break

            # recalculate TCoO
            gear.recalculate_tcoo()

            # save
            ds.update_gear(
                user_id=user_id,
                gear=gear,
                dataset_name=ds.profile(user_id).dataset_name,
            )

            flask.flash(
                message=f"Service recorded for '{component.name}'", category="success"
            )
            return flask.redirect(flask.url_for("settings_gear_update", key=gear_key))

        flask.flash(
            message="Service record error - form validation error", category="error"
        )

    else:
        flask.flash(
            message=f"{NAME_ENTITY} update error - unsupported HTTP method",
            category="error",
        )

    return flask.redirect(flask.url_for("settings_gear_update", key=gear_key))


@flask_app.route(
    f"/settings/gears/<gear_key>/{ENTITIES}/<component_key>/retire", methods=["POST"]
)
def settings_gear_component_retire(gear_key: str, component_key: str):
    """Retire a component."""
    user_id = flask.session.get(COOKIE_USER)
    if not user_id:
        return flask.redirect(flask.url_for("login"))

    try:
        gear = ds.get_gear(
            user_id=user_id, key=gear_key, dataset_name=ds.profile(user_id).dataset_name
        )

        # retire component and auto-record a retirement history entry so the
        # event date is preserved; km_at_service will be recomputed from
        # activity data by recompute_gear_service_intervals on next page load
        for c in gear.components:
            if c.get("key") == component_key:
                retiring = settings.GearComponent.from_dict(c)
                retirement_entry = settings.ComponentServiceHistoryEntry(
                    date=datetime.now().date().isoformat(),
                    km_at_service=retiring.km_since_service,
                    hours_at_service=retiring.hours_since_service,
                    service_type="replacement",
                )
                if component_key not in gear.component_history:
                    gear.component_history[component_key] = []
                gear.component_history[component_key].append(retirement_entry.to_dict())
                c["status"] = "retired"
                component_name = c.get("name", "Component")
                break
        else:
            raise ValueError(f"Component {component_key} not found")

        # recalculate TCoO
        gear.recalculate_tcoo()

        # save
        ds.update_gear(
            user_id=user_id,
            gear=gear,
            dataset_name=ds.profile(user_id).dataset_name,
        )

        flask.flash(message=f"Component '{component_name}' retired", category="success")
    except Exception as e:
        flask.flash(message=f"Component error: {e}", category="error")

    return flask.redirect(flask.url_for("settings_gear_get", key=gear_key))


@flask_app.route(
    f"/settings/gears/<gear_key>/{ENTITIES}/<component_key>/unretire", methods=["POST"]
)
def settings_gear_component_unretire(gear_key: str, component_key: str):
    """Un-retire a component (set status back to active)."""
    user_id = flask.session.get(COOKIE_USER)
    if not user_id:
        return flask.redirect(flask.url_for("login"))

    try:
        gear = ds.get_gear(
            user_id=user_id, key=gear_key, dataset_name=ds.profile(user_id).dataset_name
        )

        for c in gear.components:
            if c.get("key") == component_key:
                c["status"] = "active"
                component_name = c.get("name", "Component")
                break
        else:
            raise ValueError(f"Component {component_key} not found")

        # recalculate TCoO
        gear.recalculate_tcoo()

        # save
        ds.update_gear(
            user_id=user_id,
            gear=gear,
            dataset_name=ds.profile(user_id).dataset_name,
        )

        flask.flash(
            message=f"Component '{component_name}' un-retired", category="success"
        )
    except Exception as e:
        flask.flash(message=f"Component error: {e}", category="error")

    return flask.redirect(flask.url_for("settings_gear_get", key=gear_key))


def api_component_templates():
    """Get component templates (AJAX endpoint)."""
    user_id = flask.session.get(COOKIE_USER)
    category = flask.request.args.get("category", "")

    if user_id:
        all_templates = ds.list_component_templates(user_id=user_id).templates
    else:
        all_templates = settings.COMPONENT_TEMPLATES

    templates_data = []
    for template in all_templates:
        if not category or template.category == category or template.category == "all":
            templates_data.append(template.to_dict())

    return flask.jsonify(templates_data)


#
# SERVICE ENTRY
#


@flask_app.route(
    f"/settings/gears/<gear_key>/{ENTITIES}/<component_key>/service/"
    "<int:service_index>/update",
    methods=["GET", "POST"],
)
def settings_gear_component_service_update(gear_key, component_key, service_index):
    """Update a service history entry."""
    user_id = flask.session.get(COOKIE_USER)
    if not user_id:
        return flask.redirect(flask.url_for("login"))

    user_profile = ds.profile(user_id)
    gear = ds.get_gear(user_id, gear_key, user_profile.dataset_name)

    if not gear:
        flask.flash("Gear not found", "error")
        return flask.redirect(flask.url_for("settings_gear_list"))

    # get service history entry
    if component_key not in gear.component_history:
        flask.flash("No service history for this component", "error")
        return flask.redirect(flask.url_for("settings_gear_update", key=gear_key))

    history_list = gear.component_history[component_key]
    if service_index < 0 or service_index >= len(history_list):
        flask.flash("Service entry not found", "error")
        return flask.redirect(flask.url_for("settings_gear_update", key=gear_key))

    entry = history_list[service_index]

    if flask.request.method == "GET":
        form = ComponentServiceForm()
        # populate form with existing data
        form.service_date.data = datetime.fromisoformat(entry["date"]).date()
        form.service_type.data = entry["service_type"]
        form.cost.data = entry["cost"]
        form.notes.data = entry["notes"]
        form.reset_counter.data = False

        # find component for display
        component = None
        for comp_dict in gear.components:
            if comp_dict.get("key") == component_key:
                component = settings.GearComponent.from_dict(comp_dict)
                break

        return flask.render_template(
            "settings-gear-component-service-update.html",
            ff=ff,
            user_profile=user_profile,
            gear=gear,
            component=component,
            service_index=service_index,
            form=form,
        )

    elif flask.request.method == "POST":
        form = ComponentServiceForm()
        if form.validate_on_submit():
            # update the entry
            entry["date"] = form.service_date.data.isoformat()
            entry["service_type"] = form.service_type.data
            entry["cost"] = form.cost.data or 0.0
            entry["notes"] = form.notes.data or ""

            # recalculate TCoO
            gear.recalculate_tcoo()

            # save
            ds.update_gear(
                user_id=user_id,
                gear=gear,
                dataset_name=ds.profile(user_id).dataset_name,
            )

            flask.flash("Service entry updated successfully", "success")
            return flask.redirect(flask.url_for("settings_gear_update", key=gear_key))

    return flask.redirect(flask.url_for("settings_gear_update", key=gear_key))


@flask_app.route(
    f"/settings/gears/<gear_key>/{ENTITIES}/<component_key>/service/"
    "<int:service_index>/delete",
    methods=["POST"],
)
def settings_gear_component_service_delete(gear_key, component_key, service_index):
    """Delete a service history entry."""
    user_id = flask.session.get(COOKIE_USER)
    if not user_id:
        return flask.redirect(flask.url_for("login"))

    user_profile = ds.profile(user_id)
    gear = ds.get_gear(user_id, gear_key, user_profile.dataset_name)

    if not gear:
        flask.flash("Gear not found", "error")
        return flask.redirect(flask.url_for("settings_gear_list"))

    try:
        # get service history
        if component_key not in gear.component_history:
            flask.flash("No service history for this component", "error")
            return flask.redirect(flask.url_for("settings_gear_update", key=gear_key))

        history_list = gear.component_history[component_key]
        if service_index < 0 or service_index >= len(history_list):
            flask.flash("Service entry not found", "error")
            return flask.redirect(flask.url_for("settings_gear_update", key=gear_key))

        # delete the entry
        history_list.pop(service_index)

        # recalculate TCoO
        gear.recalculate_tcoo()

        # save
        ds.update_gear(
            user_id=user_id,
            gear=gear,
            dataset_name=ds.profile(user_id).dataset_name,
        )

        flask.flash("Service entry deleted successfully", "success")
    except Exception as e:
        flask.flash(f"Error deleting service entry: {e}", "error")

    return flask.redirect(flask.url_for("settings_gear_update", key=gear_key))
