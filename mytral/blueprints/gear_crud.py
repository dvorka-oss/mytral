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
from datetime import date
from datetime import datetime

import flask
import flask_wtf
import wtforms
from wtforms import validators

import mytral
from mytral import app_user_ds as ds
from mytral import charts
from mytral import ff
from mytral import forms
from mytral import settings as user_settings
from mytral.blobstore import EntityPhotoService
from mytral.blobstore import exceptions as blob_exc
from mytral.blobstore import validation as blob_validation
from mytral.blobstore.models import BlobKind
from mytral.blobstore.models import BlobOwnerKind
from mytral.routes import COOKIE_MOBILE
from mytral.routes import COOKIE_USER
from mytral.routes import flask_app

NAME_ENTITY = "Gear"
NAME_ENTITIES = f"{NAME_ENTITY}s"

ENTITY = "gear"
ENTITIES = f"{ENTITY}s"

METHODS = "gear"

#
# CRUD: LIST, CREATE, UPDATE, DELETE
#


class JinjaTemplates:
    """Jinja templates."""

    _PREFIX = f"settings-{ENTITY}-"

    LIST = f"{_PREFIX}list.html"
    CREATE = f"{_PREFIX}create.html"
    GET = f"{_PREFIX}get.html"
    UPDATE = f"{_PREFIX}update.html"
    DELETE = f"{_PREFIX}delete.html"


#
# forms
#


class CsrfForm(flask_wtf.FlaskForm):
    """Minimal form used only for CSRF token generation."""


class CreateGearForm(flask_wtf.FlaskForm):
    activity = wtforms.SelectField(
        # choices & default are dynamically set in the view
        label="Default for activity type",
        description="The activity type this gear is primarily used for",
        validators=[],
        validate_choice=False,
    )

    name = wtforms.StringField(
        label="Name",
        description="Unique name to identify this gear (e.g., 'Winter Running Shoes')",
        validators=[validators.DataRequired()],
    )
    vendor = wtforms.StringField(
        label="Vendor",
        description=(
            "Brand or manufacturer of the gear (e.g., 'Nike', 'Adidas', 'Specialized')"
        ),
        validators=[],
    )
    model = wtforms.StringField(
        label="Model",
        description="Specific model name or number (e.g., 'Pegasus 40', 'Tarmac SL7')",
        validators=[],
    )
    size = wtforms.StringField(
        label="Size",
        description="Size specification (e.g., '42 EU', 'Large', '56cm')",
        validators=[],
    )
    weight = wtforms.FloatField(
        label="Weight (kg)",
        description="Weight of the gear in kilograms (e.g., 8.2 for a bike)",
        validators=[validators.Optional(), validators.NumberRange(min=0)],
        default=0.0,
    )
    since = wtforms.IntegerField(
        label="Since",
        description="Year when you started using this gear",
        validators=[validators.NumberRange(1900, 2100)],
        default=datetime.now().year,
    )
    comment = wtforms.TextAreaField(
        label="Description",
        description="Additional notes about this gear. Supports Markdown formatting.",
        validators=[],
    )
    url = wtforms.StringField(
        label="URL",
        description=(
            "Link to product page or more information "
            "(e.g., 'https://example.com/product')"
        ),
        validators=[],
    )
    retired = wtforms.BooleanField(
        label="Retired",
        description="Mark if this gear is no longer in active use",
        default=False,
        validators=[],
    )
    is_default = wtforms.BooleanField(
        label="Default",
        description="Set as default gear for the selected activity type",
        default=False,
        validators=[],
    )

    # stats

    stat_use = wtforms.IntegerField(
        label="Use",
        validators=[],
        default=0,
    )
    stat_from = wtforms.StringField(
        label="From",
        validators=[],
    )
    stat_to = wtforms.StringField(
        label="To",
        validators=[],
    )
    stat_meters = wtforms.IntegerField(
        label="Meters",
        validators=[],
        default=0,
    )
    stat_km_str = wtforms.StringField(
        label="",
        validators=[],
    )
    stat_seconds = wtforms.IntegerField(
        label="Seconds",
        validators=[],
        default=0,
    )
    stat_duration_str = wtforms.StringField(
        label="Duration",
        validators=[],
    )
    purchased = wtforms.DateField(
        label="Purchased",
        description="Date when this gear was purchased (YYYY-MM-DD",
        format="%Y-%m-%d",
        validators=[validators.Optional()],
    )

    tcoo_base = wtforms.FloatField(
        label="Base Price",
        description="Initial purchase price of the gear",
        validators=[validators.Optional(), validators.NumberRange(min=0)],
        default=0.0,
    )
    tcoo_additional = wtforms.FloatField(
        label="Additional Cost",
        description=(
            "Other costs not tracked by components "
            "(e.g., bike fitting, shipping, insurance, custom work)"
        ),
        validators=[validators.Optional(), validators.NumberRange(min=0)],
        default=0.0,
    )

    # key is handled by the backend

    submit = wtforms.SubmitField("Create")


class UpdateGearForm(CreateGearForm):
    submit = wtforms.SubmitField("Save")


class DeleteGearForm(flask_wtf.FlaskForm):
    submit = wtforms.SubmitField("Delete")


#
# helpers
#


def _entity_photo_service() -> EntityPhotoService:
    """Return an EntityPhotoService bound to the global blobstore."""
    return EntityPhotoService(store=mytral.app_blobstore)


#
# routes
#


@flask_app.route(f"/settings/{ENTITIES}", methods=["GET", "POST"])
def settings_gear_list():
    """List gear:

    - HTTP GET: show list of gear.

    Links to the actions from the listing:

    - CREATE: HTTP GET /settings/gear/create
      ... show form to create gear.
    - UPDATE: HTTP GET /settings/gear/<key>/update
      ... show form to update gear.
    - DELETE: HTTP GET /settings/gear/<key>/delete
      ... show form to delete gear

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

        # get gear stats from cache
        gear_stats = ds.gear_stats(
            user_id=user_id,
            dataset_name=ds.profile(user_id).dataset_name,
        )

        gear = ds.list_gear(
            user_id=user_id,
            dataset_name=ds.profile(user_id).dataset_name,
        )

        # sort gear by last used date (descending)
        sorted_items = sorted(
            gear.gear_by_key.items(),
            key=lambda item: (
                gear_stats.stats(item[0]).stat_to if gear_stats.stats(item[0]) else ""
            ),
            reverse=True,
        )
        gear.gear_by_key = dict(sorted_items)

        # split gear into active and retired lists for separate tables
        active_gear = [g for g in gear.gear_by_key.values() if not g.retired]
        retired_gear = [g for g in gear.gear_by_key.values() if g.retired]

        activity_types = ds.list_activity_types(user_id)

        aspect_arg = flask.request.args.get("aspect")
        if aspect_arg:  # chart
            script, div = charts.gear_in_time(
                user_gear=gear,
                gear_stats=gear_stats,
                is_mobile_view=bool(flask.session.get(COOKIE_MOBILE)),
            )

            return flask.render_template(
                JinjaTemplates.LIST,
                ff=ff,
                user_profile=ds.profile(user_id),
                gear=gear,
                gear_stats=gear_stats,
                activity_types=activity_types,
                active_gear=active_gear,
                retired_gear=retired_gear,
                script=script,
                div=div,
            )
        else:  # list
            return flask.render_template(
                JinjaTemplates.LIST,
                ff=ff,
                user_profile=ds.profile(user_id),
                gear=gear,
                gear_stats=gear_stats,
                activity_types=activity_types,
                active_gear=active_gear,
                retired_gear=retired_gear,
            )

    else:
        flask.flash(
            message="Settings error - unsupported HTTP method", category="error"
        )
        return flask.redirect(flask.url_for("home"))


@flask_app.route(f"/settings/{ENTITIES}/create", methods=["GET", "POST"])
def settings_gear_create():
    """Create:

    - HTTP GET: show form to create entity.
    - HTTP POST: actually create entity.

    """
    user_id = flask.session.get(COOKIE_USER)
    if not user_id:
        return flask.redirect(flask.url_for("login"))

    if flask.request.method == "GET":
        form = CreateGearForm()

        sport_choices = ds.list_activity_types(user_id).choices()
        form.activity.choices = sport_choices
        form.activity.default = sport_choices[0][0]

        return flask.render_template(
            JinjaTemplates.CREATE,
            ff=ff,
            user_profile=ds.profile(user_id),
            form=form,
        )

    elif flask.request.method == "POST":
        form = CreateGearForm()
        if form.validate_on_submit():
            entity = user_settings.Gear(
                activity_type_key=form.activity.data,
                name=form.name.data,
                vendor=form.vendor.data,
                model=form.model.data,
                size=form.size.data,
                weight=form.weight.data or 0.0,
                comment=form.comment.data,
                url=form.url.data,
                retired=form.retired.data,
                is_default=form.is_default.data,
                tcoo_base=form.tcoo_base.data or 0.0,
                tcoo_additional=form.tcoo_additional.data or 0.0,
                purchased=form.purchased.data.isoformat()
                if form.purchased.data
                else "",
            )

            new_gear = ds.create_gear(
                user_id=user_id,
                gear=entity,
                dataset_name=ds.profile(user_id).dataset_name,
            )

            return flask.redirect(
                flask.url_for(f"settings_{METHODS}_get", key=new_gear.key)
            )

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


@flask_app.route(f"/settings/{ENTITIES}/<key>/get", methods=["GET"])
def settings_gear_get(key: str):
    """View entity details."""
    user_id = flask.session.get(COOKIE_USER)
    if not user_id:
        return flask.redirect(flask.url_for("login"))

    try:
        dataset_name = ds.profile(user_id).dataset_name
        entity = ds.get_gear(user_id=user_id, key=key, dataset_name=dataset_name)
        # recompute service history km/hours from activity records so the page
        # always reflects the actual usage between events, independent of the
        # component odometer snapshot (which may be stale for bulk-imported activities)
        ds.recompute_gear_service_intervals(
            user_id=user_id, dataset_name=dataset_name, gear=entity
        )
    except Exception as e:
        flask.flash(
            message=(
                f"{NAME_ENTITY} view error - unable to get {NAME_ENTITY.lower()} "
                f"with key {key}: {e}"
            ),
            category="error",
        )
        return flask.redirect(flask.url_for(f"settings_{METHODS}_list"))

    svc = _entity_photo_service()
    photos = svc.list_photos(user_id=user_id, blob_keys=entity.photo_blob_keys)

    return flask.render_template(
        JinjaTemplates.GET,
        ff=ff,
        user_profile=ds.profile(user_id),
        key=key,
        gear=entity,
        activity_types=ds.list_activity_types(user_id),
        csrf_form=CsrfForm(),
        photos=photos,
        upload_form=forms.UploadEntityPhotoForm(prefix="epu"),
        delete_form=forms.DeleteEntityPhotoForm(prefix="epd"),
        highlight_form=forms.DeleteEntityPhotoForm(prefix="eph"),
    )


@flask_app.route(f"/settings/{ENTITIES}/<key>/update", methods=["GET", "POST"])
def settings_gear_update(key: str):
    """Update entity:

    - HTTP GET: show form to update entity.
    - HTTP POST: actually update entity.

    """
    user_id = flask.session.get(COOKIE_USER)
    if not user_id:
        return flask.redirect(flask.url_for("login"))

    try:
        entity = ds.get_gear(
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
        form = UpdateGearForm()

        activity_choices = ds.list_activity_types(user_id).choices()
        form.activity.choices = activity_choices
        form.activity.default = activity_choices[0][0]
        form.activity.data = entity.activity_type_key

        form.name.data = entity.name
        form.vendor.data = entity.vendor
        form.model.data = entity.model
        form.size.data = entity.size
        form.weight.data = entity.weight
        form.comment.data = entity.comment
        form.url.data = entity.url
        form.retired.data = entity.retired
        form.is_default.data = entity.is_default
        form.tcoo_base.data = entity.tcoo_base
        form.tcoo_additional.data = entity.tcoo_additional
        form.purchased.data = (
            date.fromisoformat(entity.purchased) if entity.purchased else None
        )

        return flask.render_template(
            JinjaTemplates.UPDATE,
            ff=ff,
            user_profile=ds.profile(user_id),
            form=form,
            key=key,
            gear=entity,
        )

    elif flask.request.method == "POST":
        form = UpdateGearForm()
        if form.validate_on_submit():
            entity.activity_type_key = form.activity.data
            entity.name = form.name.data or ""
            entity.vendor = form.vendor.data or ""
            entity.model = form.model.data or ""
            entity.size = form.size.data or ""
            entity.weight = form.weight.data or 0.0
            entity.comment = form.comment.data or ""
            entity.url = form.url.data or ""
            entity.retired = form.retired.data
            entity.is_default = form.is_default.data
            entity.tcoo_base = form.tcoo_base.data or 0.0
            entity.tcoo_additional = form.tcoo_additional.data or 0.0
            entity.purchased = (
                form.purchased.data.isoformat() if form.purchased.data else ""
            )

            ds.update_gear(
                user_id=user_id,
                gear=entity,
                dataset_name=ds.profile(user_id).dataset_name,
            )

            return flask.redirect(
                flask.url_for(f"settings_{METHODS}_get", key=entity.key)
            )

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


@flask_app.route(f"/settings/{ENTITIES}/<key>/photos/upload", methods=["GET", "POST"])
def settings_gear_upload_photo(key: str):
    """Upload a photo for gear."""
    user_id = flask.session.get(COOKIE_USER)
    if not user_id:
        return flask.redirect(flask.url_for("login"))

    upload_form = forms.UploadEntityPhotoForm(prefix="epu")
    dataset_name = ds.profile(user_id).dataset_name
    entity = ds.get_gear(user_id=user_id, key=key, dataset_name=dataset_name)

    if flask.request.method == "GET":
        return flask.render_template(
            "settings-gear-photo-upload.html",
            ff=ff,
            user_profile=ds.profile(user_id),
            key=key,
            gear=entity,
            form=upload_form,
            current_count=len(entity.photo_blob_keys),
        )

    if upload_form.validate_on_submit():
        f = upload_form.photo.data
        original_filename = f.filename or "photo.jpg"
        try:
            svc = _entity_photo_service()
            meta = svc.upload_photo(
                user_id=user_id,
                owner_key=key,
                owner_kind=BlobOwnerKind.GEAR,
                kind=BlobKind.GEAR_PHOTO,
                file_stream=f.stream,
                original_filename=original_filename,
                current_count=len(entity.photo_blob_keys),
            )
            entity.photo_blob_keys = list(entity.photo_blob_keys) + [meta.blob_key]
            if not entity.highlight_photo_blob_key:
                entity.highlight_photo_blob_key = meta.blob_key
            try:
                ds.update_gear(user_id=user_id, gear=entity, dataset_name=dataset_name)
                flask.flash(message="Photo uploaded", category="success")
            except Exception as exc:
                svc.delete_photo(user_id, meta.blob_key)
                raise exc
        except Exception as e:
            flask.flash(message=f"Photo upload error: {e}", category="error")
    else:
        flask.flash(message="Photo upload form validation failed", category="error")

    return flask.redirect(flask.url_for("settings_gear_get", key=key))


@flask_app.route(
    f"/settings/{ENTITIES}/<key>/photos/<blob_key>/update", methods=["GET", "POST"]
)
def settings_gear_update_photo_metadata(key: str, blob_key: str):
    """Update metadata for a single gear photo."""
    user_id = flask.session.get(COOKIE_USER)
    if not user_id:
        return flask.redirect(flask.url_for("login"))

    dataset_name = ds.profile(user_id).dataset_name
    try:
        entity = ds.get_gear(user_id=user_id, key=key, dataset_name=dataset_name)
    except Exception as e:
        flask.flash(
            message=(
                f"{NAME_ENTITY} photo update error - unable to get "
                f"{NAME_ENTITY.lower()} with key {key}: {e}"
            ),
            category="error",
        )
        return flask.redirect(flask.url_for(f"settings_{METHODS}_list"))

    if blob_key not in entity.photo_blob_keys:
        flask.abort(404)

    form = forms.UpdateActivityPhotoMetadataForm()
    try:
        photo = mytral.app_blobstore.get_blob_metadata(
            user_id=user_id,
            blob_key=blob_key,
        )
    except (blob_exc.BlobNotFoundError, blob_exc.BlobStoreError) as e:
        flask.flash(
            message=(
                f"{NAME_ENTITY} photo update error - unable to load photo "
                f"{blob_key}: {e}"
            ),
            category="error",
        )
        return flask.redirect(flask.url_for("settings_gear_get", key=key))

    if flask.request.method == "GET":
        form.name.data = photo.name
        form.description.data = photo.description
        form.keywords.data = ", ".join(photo.keywords)
        return flask.render_template(
            "settings-gear-photo-update.html",
            ff=ff,
            user_profile=ds.profile(user_id),
            form=form,
            key=key,
            gear=entity,
            photo=photo,
        )

    if form.validate_on_submit():
        try:
            name, description, keywords = blob_validation.validate_blob_metadata(
                form.name.data or "",
                form.description.data or "",
                form.keywords.data or "",
            )
            mytral.app_blobstore.update_blob_metadata(
                user_id=user_id,
                blob_key=blob_key,
                name=name,
                description=description,
                keywords=keywords,
            )
            flask.flash(message="Photo metadata updated", category="success")
            return flask.redirect(flask.url_for("settings_gear_get", key=key))
        except (blob_exc.BlobValidationError, blob_exc.BlobStoreError) as e:
            flask.flash(
                message=f"{NAME_ENTITY} photo metadata error - {e}",
                category="error",
            )
    else:
        flask.flash(
            message=f"{NAME_ENTITY} photo metadata error - form validation failed",
            category="error",
        )

    return flask.render_template(
        "settings-gear-photo-update.html",
        ff=ff,
        user_profile=ds.profile(user_id),
        form=form,
        key=key,
        gear=entity,
        photo=photo,
    )


@flask_app.route(f"/settings/{ENTITIES}/<key>/photos/<blob_key>", methods=["GET"])
def settings_gear_photo(key: str, blob_key: str):
    """Serve a gear photo."""
    user_id = flask.session.get(COOKIE_USER)
    if not user_id:
        return flask.redirect(flask.url_for("login"))
    try:
        entity = ds.get_gear(
            user_id=user_id, key=key, dataset_name=ds.profile(user_id).dataset_name
        )
        if blob_key not in entity.photo_blob_keys:
            flask.abort(404)
        svc = _entity_photo_service()
        stream, meta = svc.open_photo(user_id=user_id, blob_key=blob_key)
        return flask.send_file(
            stream,
            mimetype=meta.content_type or "image/jpeg",
            download_name=meta.file_name,
        )
    except Exception as e:
        flask.flash(message=f"Photo error: {e}", category="error")
        return flask.redirect(flask.url_for("settings_gear_get", key=key))


@flask_app.route(
    f"/settings/{ENTITIES}/<key>/photos/<blob_key>/thumbnail", methods=["GET"]
)
def settings_gear_photo_thumbnail(key: str, blob_key: str):
    """Serve a gear photo thumbnail."""
    user_id = flask.session.get(COOKIE_USER)
    if not user_id:
        return flask.redirect(flask.url_for("login"))
    try:
        entity = ds.get_gear(
            user_id=user_id, key=key, dataset_name=ds.profile(user_id).dataset_name
        )
        if blob_key not in entity.photo_blob_keys:
            flask.abort(404)
        svc = _entity_photo_service()
        stream, meta = svc.open_photo(
            user_id=user_id, blob_key=blob_key, thumbnail=True
        )
        return flask.send_file(
            stream,
            mimetype="image/jpeg",
            download_name="thumbnail.jpg",
        )
    except Exception as e:
        flask.flash(message=f"Photo thumbnail error: {e}", category="error")
        return flask.redirect(flask.url_for("settings_gear_get", key=key))


@flask_app.route(
    f"/settings/{ENTITIES}/<key>/photos/<blob_key>/delete", methods=["POST"]
)
def settings_gear_delete_photo(key: str, blob_key: str):
    """Delete a gear photo."""
    user_id = flask.session.get(COOKIE_USER)
    if not user_id:
        return flask.redirect(flask.url_for("login"))

    delete_form = forms.DeleteEntityPhotoForm(prefix="epd")
    if delete_form.validate_on_submit():
        try:
            dataset_name = ds.profile(user_id).dataset_name
            entity = ds.get_gear(user_id=user_id, key=key, dataset_name=dataset_name)
            if blob_key not in entity.photo_blob_keys:
                flask.abort(404)
            svc = _entity_photo_service()
            svc.delete_photo(user_id=user_id, blob_key=blob_key)
            new_keys = [bk for bk in entity.photo_blob_keys if bk != blob_key]
            entity.photo_blob_keys = new_keys
            if entity.highlight_photo_blob_key == blob_key:
                entity.highlight_photo_blob_key = new_keys[0] if new_keys else ""
            ds.update_gear(user_id=user_id, gear=entity, dataset_name=dataset_name)
            flask.flash(message="Photo deleted", category="success")
        except Exception as e:
            flask.flash(message=f"Photo delete error: {e}", category="error")
    else:
        flask.flash(message="Photo delete form validation failed", category="error")

    return flask.redirect(flask.url_for("settings_gear_get", key=key))


@flask_app.route(
    f"/settings/{ENTITIES}/<key>/photos/<blob_key>/highlight", methods=["POST"]
)
def settings_gear_highlight_photo(key: str, blob_key: str):
    """Set a photo as the highlight photo for gear."""
    user_id = flask.session.get(COOKIE_USER)
    if not user_id:
        return flask.redirect(flask.url_for("login"))

    highlight_form = forms.DeleteEntityPhotoForm(prefix="eph")
    if highlight_form.validate_on_submit():
        try:
            dataset_name = ds.profile(user_id).dataset_name
            entity = ds.get_gear(user_id=user_id, key=key, dataset_name=dataset_name)
            if blob_key not in entity.photo_blob_keys:
                flask.abort(404)
            entity.highlight_photo_blob_key = blob_key
            ds.update_gear(user_id=user_id, gear=entity, dataset_name=dataset_name)
            flask.flash(message="Highlight photo updated", category="success")
        except Exception as e:
            flask.flash(message=f"Highlight photo error: {e}", category="error")
    else:
        flask.flash(message="Highlight form validation failed", category="error")

    return flask.redirect(flask.url_for("settings_gear_get", key=key))


@flask_app.route(f"/settings/{ENTITIES}/<key>/delete", methods=["GET", "POST"])
def settings_gear_delete(key: str):
    """Delete:

    - HTTP GET: Do you really want to delete entity?
    - HTTP POST: actually delete entity.

    """
    user_id = flask.session.get(COOKIE_USER)
    if not user_id:
        return flask.redirect(flask.url_for("login"))

    form = DeleteGearForm()

    if flask.request.method == "POST":
        if form.validate_on_submit():
            if form.validate_on_submit():
                try:
                    # best-effort blob cleanup before deleting entity
                    try:
                        dataset_name = ds.profile(user_id).dataset_name
                        entity = ds.get_gear(
                            user_id=user_id, key=key, dataset_name=dataset_name
                        )
                        svc = _entity_photo_service()
                        for bk in entity.photo_blob_keys:
                            svc.delete_photo(user_id, bk)
                    except Exception:
                        pass

                    ds.delete_gear(
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
        entity = ds.get_gear(
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
