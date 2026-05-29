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

import mytral
from mytral import app_user_ds as ds
from mytral import ff
from mytral import forms
from mytral import settings as user_settings
from mytral.blobstore import EntityPhotoService
from mytral.blobstore import exceptions as blob_exc
from mytral.blobstore import validation as blob_validation
from mytral.blobstore.models import BlobKind
from mytral.blobstore.models import BlobOwnerKind
from mytral.routes import COOKIE_USER
from mytral.routes import flask_app

NAME_ENTITY = "Goal"
NAME_ENTITIES = f"{NAME_ENTITY}s"

ENTITY = "goal"
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
    GET = f"{_PREFIX}get.html"
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
        description="Goal description. Supports Markdown formatting.",
        validators=[validators.Optional()],
    )

    tag = wtforms.StringField(
        label="",
        validators=[validators.Optional()],
        default="",
    )

    done = wtforms.BooleanField(
        label="",
        validators=[validators.Optional()],
        default=False,
    )

    urgency = wtforms.FloatField(
        label="",
        validators=[
            validators.Optional(),
            validators.NumberRange(min=0.0, max=1.0),
        ],
        default=0.5,
    )

    importance = wtforms.FloatField(
        label="",
        validators=[
            validators.Optional(),
            validators.NumberRange(min=0.0, max=1.0),
        ],
        default=0.5,
    )

    # key is handled by the backend

    submit = wtforms.SubmitField("Create")


class UpdateForm(CreateForm):
    submit = wtforms.SubmitField("Save")


class DeleteForm(flask_wtf.FlaskForm):
    submit = wtforms.SubmitField("Delete")


class QuickMoveForm(flask_wtf.FlaskForm):
    """Form for quick move operation with CSRF protection."""

    quadrant = wtforms.HiddenField(
        validators=[validators.DataRequired()],
    )


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
def settings_goals_list():
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
        aspect_arg = flask.request.args.get("aspect")

        goals = ds.list_goals(
            user_id=user_id, dataset_name=ds.profile(user_id).dataset_name
        )
        activity_types = ds.list_activity_types(
            user_id=user_id, dataset_name=ds.profile(user_id).dataset_name
        )

        if aspect_arg == "list":
            # list view
            return flask.render_template(
                JinjaTemplates.LIST,
                ff=ff,
                user_profile=ds.profile(user_id),
                goals=goals,
                activity_types=activity_types,
            )
        else:
            # DEFAULT: eisenhower matrix view
            from mytral import charts
            from mytral.routes import COOKIE_MOBILE

            # create a simple form for CSRF token
            csrf_form = DeleteForm()

            # get zoom level from query parameter or session, default to 0.7
            zoom_level = flask.request.args.get("zoom", type=float)
            if zoom_level is None:
                zoom_level = flask.session.get("eisenhower_zoom", 0.7)
            else:
                flask.session["eisenhower_zoom"] = zoom_level

            script, div = charts.goals_eisenhower_matrix(
                goals=goals,
                activity_types=activity_types,
                is_mobile_view=bool(flask.session.get(COOKIE_MOBILE)),
                zoom_level=zoom_level,
            )

            return flask.render_template(
                JinjaTemplates.LIST,
                ff=ff,
                user_profile=ds.profile(user_id),
                goals=goals,
                activity_types=activity_types,
                script=script,
                div=div,
                aspect="eisenhower",
                form=csrf_form,
                zoom_level=zoom_level,
            )

    else:
        flask.flash(
            message=f"{NAME_ENTITY} settings error - unsupported HTTP method",
            category="error",
        )
        return flask.redirect(flask.url_for("home"))


@flask_app.route(f"/settings/{ENTITIES}/create", methods=["GET", "POST"])
def settings_goal_create():
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
            entity = user_settings.Goal(
                name=form.name.data,
                activity_type=form.activity_type.data,
                description=form.description.data,
                tag=form.tag.data,
                done=form.done.data,
                urgency=(form.urgency.data if form.urgency.data is not None else 0.5),
                importance=(
                    form.importance.data if form.importance.data is not None else 0.5
                ),
                # key is assigned by the backend
            )

            ds.create_goal(user_id=user_id, goal=entity)

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
def settings_goal_update(key: str):
    """Update entity:

    - HTTP GET: show form to update entity.
    - HTTP POST: actually update entity.

    """
    user_id = flask.session.get(COOKIE_USER)
    if not user_id:
        return flask.redirect(flask.url_for("login"))

    try:
        entity = ds.get_goal(user_id=user_id, key=key)
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
        form.tag.data = entity.tag
        form.done.data = entity.done
        form.urgency.data = entity.urgency
        form.importance.data = entity.importance

        svc = _entity_photo_service()
        photos = svc.list_photos(user_id=user_id, blob_keys=entity.photo_blob_keys)

        return flask.render_template(
            JinjaTemplates.UPDATE,
            ff=ff,
            user_profile=ds.profile(user_id),
            form=form,
            key=key,
            entity=entity,
            photos=photos,
            upload_form=forms.UploadEntityPhotoForm(prefix="epu"),
            delete_form=forms.DeleteEntityPhotoForm(prefix="epd"),
            highlight_form=forms.DeleteEntityPhotoForm(prefix="eph"),
        )

    elif flask.request.method == "POST":
        form = UpdateForm()
        if form.validate_on_submit():
            entity.name = form.name.data or ""
            entity.activity_type = form.activity_type.data or ""
            entity.description = form.description.data or ""
            entity.tag = form.tag.data or ""
            entity.done = form.done.data or False
            entity.urgency = form.urgency.data if form.urgency.data is not None else 0.5
            entity.importance = (
                form.importance.data if form.importance.data is not None else 0.5
            )

            ds.update_goal(user_id=user_id, goal=entity)

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


@flask_app.route(f"/settings/{ENTITIES}/<key>/get", methods=["GET"])
def settings_goal_get(key: str):
    """View goal details."""
    user_id = flask.session.get(COOKIE_USER)
    if not user_id:
        return flask.redirect(flask.url_for("login"))

    try:
        entity = ds.get_goal(user_id=user_id, key=key)
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
        entity=entity,
        photos=photos,
        upload_form=forms.UploadEntityPhotoForm(prefix="epu"),
        delete_form=forms.DeleteEntityPhotoForm(prefix="epd"),
        highlight_form=forms.DeleteEntityPhotoForm(prefix="eph"),
    )


@flask_app.route(f"/settings/{ENTITIES}/<key>/photos/upload", methods=["GET", "POST"])
def settings_goal_upload_photo(key: str):
    """Upload a photo for a goal."""
    user_id = flask.session.get(COOKIE_USER)
    if not user_id:
        return flask.redirect(flask.url_for("login"))

    upload_form = forms.UploadEntityPhotoForm(prefix="epu")
    entity = ds.get_goal(user_id=user_id, key=key)

    if flask.request.method == "GET":
        return flask.render_template(
            "settings-goals-photo-upload.html",
            ff=ff,
            user_profile=ds.profile(user_id),
            key=key,
            entity=entity,
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
                owner_kind=BlobOwnerKind.GOAL,
                kind=BlobKind.GOAL_PHOTO,
                file_stream=f.stream,
                original_filename=original_filename,
                current_count=len(entity.photo_blob_keys),
            )
            entity.photo_blob_keys = list(entity.photo_blob_keys) + [meta.blob_key]
            if not entity.highlight_photo_blob_key:
                entity.highlight_photo_blob_key = meta.blob_key
            try:
                ds.update_goal(user_id=user_id, goal=entity)
                flask.flash(message="Photo uploaded", category="success")
            except Exception as exc:
                svc.delete_photo(user_id, meta.blob_key)
                raise exc
        except Exception as e:
            flask.flash(message=f"Photo upload error: {e}", category="error")
    else:
        flask.flash(message="Photo upload form validation failed", category="error")

    return flask.redirect(flask.url_for("settings_goal_get", key=key))


@flask_app.route(
    f"/settings/{ENTITIES}/<key>/photos/<blob_key>/update", methods=["GET", "POST"]
)
def settings_goal_update_photo_metadata(key: str, blob_key: str):
    """Update metadata for a single goal photo."""
    user_id = flask.session.get(COOKIE_USER)
    if not user_id:
        return flask.redirect(flask.url_for("login"))

    try:
        entity = ds.get_goal(user_id=user_id, key=key)
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
        return flask.redirect(flask.url_for("settings_goal_get", key=key))

    if flask.request.method == "GET":
        form.name.data = photo.name
        form.description.data = photo.description
        form.keywords.data = ", ".join(photo.keywords)
        return flask.render_template(
            "settings-goals-photo-update.html",
            ff=ff,
            user_profile=ds.profile(user_id),
            form=form,
            key=key,
            entity=entity,
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
            return flask.redirect(flask.url_for("settings_goal_get", key=key))
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
        "settings-goals-photo-update.html",
        ff=ff,
        user_profile=ds.profile(user_id),
        form=form,
        key=key,
        entity=entity,
        photo=photo,
    )


@flask_app.route(f"/settings/{ENTITIES}/<key>/photos/<blob_key>", methods=["GET"])
def settings_goal_photo(key: str, blob_key: str):
    """Serve a goal photo."""
    user_id = flask.session.get(COOKIE_USER)
    if not user_id:
        return flask.redirect(flask.url_for("login"))
    try:
        entity = ds.get_goal(user_id=user_id, key=key)
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
        return flask.redirect(flask.url_for("settings_goal_get", key=key))


@flask_app.route(
    f"/settings/{ENTITIES}/<key>/photos/<blob_key>/thumbnail", methods=["GET"]
)
def settings_goal_photo_thumbnail(key: str, blob_key: str):
    """Serve a goal photo thumbnail."""
    user_id = flask.session.get(COOKIE_USER)
    if not user_id:
        return flask.redirect(flask.url_for("login"))
    try:
        entity = ds.get_goal(user_id=user_id, key=key)
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
        return flask.redirect(flask.url_for("settings_goal_get", key=key))


@flask_app.route(
    f"/settings/{ENTITIES}/<key>/photos/<blob_key>/delete", methods=["POST"]
)
def settings_goal_delete_photo(key: str, blob_key: str):
    """Delete a goal photo."""
    user_id = flask.session.get(COOKIE_USER)
    if not user_id:
        return flask.redirect(flask.url_for("login"))

    delete_form = forms.DeleteEntityPhotoForm(prefix="epd")
    if delete_form.validate_on_submit():
        try:
            entity = ds.get_goal(user_id=user_id, key=key)
            if blob_key not in entity.photo_blob_keys:
                flask.abort(404)
            svc = _entity_photo_service()
            svc.delete_photo(user_id=user_id, blob_key=blob_key)
            new_keys = [bk for bk in entity.photo_blob_keys if bk != blob_key]
            entity.photo_blob_keys = new_keys
            if entity.highlight_photo_blob_key == blob_key:
                entity.highlight_photo_blob_key = new_keys[0] if new_keys else ""
            ds.update_goal(user_id=user_id, goal=entity)
            flask.flash(message="Photo deleted", category="success")
        except Exception as e:
            flask.flash(message=f"Photo delete error: {e}", category="error")
    else:
        flask.flash(message="Photo delete form validation failed", category="error")

    return flask.redirect(flask.url_for("settings_goal_get", key=key))


@flask_app.route(
    f"/settings/{ENTITIES}/<key>/photos/<blob_key>/highlight", methods=["POST"]
)
def settings_goal_highlight_photo(key: str, blob_key: str):
    """Set a photo as the highlight photo for a goal."""
    user_id = flask.session.get(COOKIE_USER)
    if not user_id:
        return flask.redirect(flask.url_for("login"))

    highlight_form = forms.DeleteEntityPhotoForm(prefix="eph")
    if highlight_form.validate_on_submit():
        try:
            entity = ds.get_goal(user_id=user_id, key=key)
            if blob_key not in entity.photo_blob_keys:
                flask.abort(404)
            entity.highlight_photo_blob_key = blob_key
            ds.update_goal(user_id=user_id, goal=entity)
            flask.flash(message="Highlight photo updated", category="success")
        except Exception as e:
            flask.flash(message=f"Highlight photo error: {e}", category="error")
    else:
        flask.flash(message="Highlight form validation failed", category="error")

    return flask.redirect(flask.url_for("settings_goal_get", key=key))


@flask_app.route(f"/settings/{ENTITIES}/<key>/delete", methods=["GET", "POST"])
def settings_goal_delete(key: str):
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
                # best-effort blob cleanup before deleting entity
                try:
                    entity = ds.get_goal(user_id=user_id, key=key)
                    svc = _entity_photo_service()
                    for bk in entity.photo_blob_keys:
                        svc.delete_photo(user_id, bk)
                except Exception:
                    pass

                ds.delete_goal(user_id=user_id, key=key)

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
        entity = ds.get_goal(user_id=user_id, key=key)
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


@flask_app.route(f"/settings/{ENTITIES}/<key>/move", methods=["POST"])
def settings_goal_quick_move(key: str):
    """Quick move goal to quadrant via simple POST.

    Parameters
    ----------
    key : str
        Goal key

    Returns
    -------
    flask.Response
        Redirect to goals list with current view aspect
    """
    user_id = flask.session.get(COOKIE_USER)
    if not user_id:
        return flask.redirect(flask.url_for("login"))

    form = QuickMoveForm()

    if not form.validate_on_submit():
        flask.flash(
            message="Invalid request - CSRF validation failed",
            category="error",
        )
        aspect = flask.request.args.get("aspect", "")
        if aspect:
            return flask.redirect(
                flask.url_for(f"settings_{METHODS}_list", aspect=aspect)
            )
        else:
            return flask.redirect(flask.url_for(f"settings_{METHODS}_list"))

    try:
        goal = ds.get_goal(user_id=user_id, key=key)
        quadrant = form.quadrant.data

        # map quadrant to urgency/importance values
        quadrant_values = {
            "Q1": {"urgency": 0.75, "importance": 0.75},  # Focus Now
            "Q2": {"urgency": 0.25, "importance": 0.75},  # Plan & Build
            "Q3": {"urgency": 0.75, "importance": 0.25},  # Quick Wins
            "Q4": {"urgency": 0.25, "importance": 0.25},  # Reconsider
        }

        if quadrant in quadrant_values:
            goal.urgency = quadrant_values[quadrant]["urgency"]
            goal.importance = quadrant_values[quadrant]["importance"]

            ds.update_goal(user_id=user_id, goal=goal)

            flask.flash(
                message=f"Goal moved to {quadrant}",
                category="success",
            )
        else:
            flask.flash(
                message=f"Invalid quadrant: {quadrant}",
                category="error",
            )

    except Exception as e:
        flask.flash(
            message=f"Error moving goal: {e}",
            category="error",
        )

    # preserve current view aspect when redirecting
    aspect = flask.request.args.get("aspect", "")
    if aspect:
        return flask.redirect(flask.url_for(f"settings_{METHODS}_list", aspect=aspect))
    else:
        return flask.redirect(flask.url_for(f"settings_{METHODS}_list"))
