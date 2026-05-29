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
from mytral import muscle_groups as mg
from mytral import settings as user_settings
from mytral.blobstore import EntityPhotoService
from mytral.blobstore import exceptions as blob_exc
from mytral.blobstore import validation as blob_validation
from mytral.blobstore.models import BlobKind
from mytral.blobstore.models import BlobOwnerKind
from mytral.routes import COOKIE_USER
from mytral.routes import flask_app

NAME_ENTITY = "Exercise"
NAME_ENTITIES = f"{NAME_ENTITY}s"

ENTITY = "exercise"
ENTITIES = f"{ENTITY}s"

METHODS = "exercises"

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


class CreateExerciseTypeForm(flask_wtf.FlaskForm):
    name = wtforms.StringField(
        label="Exercise name",
        validators=[validators.DataRequired()],
    )

    description = wtforms.TextAreaField(
        label="Description",
        validators=[validators.Optional()],
        description="Exercise description. Supports Markdown formatting.",
    )

    weight = wtforms.FloatField(
        label="Default weight (kg)",
        validators=[validators.NumberRange(0, 500)],
        default=0.0,
    )

    tags = wtforms.StringField(
        label="Tags (comma-separated)",
        validators=[validators.Optional()],
        description=(
            "Enter tags separated by commas (e.g., upper body, strength, compound)"
        ),
    )

    count = wtforms.IntegerField(
        label="",
        validators=[validators.NumberRange(0, 50_000)],
        default=0,
    )

    # key is handled by the backend

    submit = wtforms.SubmitField("Create")


class UpdateExerciseTypeForm(CreateExerciseTypeForm):
    submit = wtforms.SubmitField("Save")


class DeleteExerciseTypeForm(flask_wtf.FlaskForm):
    submit = wtforms.SubmitField("Delete")


#
# helpers
#


def _entity_photo_service() -> EntityPhotoService:
    """Return an EntityPhotoService bound to the global blobstore."""
    return EntityPhotoService(store=mytral.app_blobstore)


def build_photo_markdown_link_text(photo_name: str, photo_url: str) -> str:
    """Build markdown link text for inserting a photo link into descriptions."""
    label = photo_name.strip() if photo_name and photo_name.strip() else "photo"
    return f"[{label}]({photo_url})"


def build_muscle_highlights(
    primary_groups: list[str], secondary_groups: list[str]
) -> dict[str, str]:
    """Build mannequin highlight classes for an exercise."""
    highlights: dict[str, str] = {}
    for group in primary_groups:
        if group:
            highlights[group] = "state-active"
    for group in secondary_groups:
        if group and group not in highlights:
            highlights[group] = "state-secondary"
    return highlights


#
# routes
#


@flask_app.route(f"/settings/{ENTITIES}", methods=["GET", "POST"])
def settings_exercises_list():
    """List entities:

    - HTTP GET: show list of entries.

    Links to the actions from the listing:

    - CREATE: HTTP GET /settings/exercises/create
      ... show form to create entity.
    - UPDATE: HTTP GET /settings/exercises/<key>/update
      ... show form to update entity.
    - DELETE: HTTP GET /settings/exercises/<key>/delete
      ... show form to delete entity.

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

        # get exercises stats from cache
        exercises_stats = ds.exercises_stats(
            user_id=user_id,
            dataset_name=ds.profile(user_id).dataset_name,
        )

        # get all exercises (fresh from data source)
        all_exercises = ds.list_exercises(
            user_id=user_id, dataset_name=ds.profile(user_id).dataset_name
        )

        # collect unique tags for filter dropdown (from all exercises)
        unique_tags = set()
        for exercise in all_exercises.exercise_by_key.values():
            if exercise.tags:
                unique_tags.update(exercise.tags)
        unique_tags = sorted(unique_tags)

        # get filter parameters from query string
        filter_tag = flask.request.args.get("tag", "")
        filter_weight = flask.request.args.get("weight", "")
        filter_weight_op = flask.request.args.get("weight_op", "gte")

        # get all exercises as list for filtering
        exercises_list = list(all_exercises.exercise_by_key.values())

        # apply filters
        if filter_tag:
            exercises_list = [e for e in exercises_list if filter_tag in (e.tags or [])]
        if filter_weight:
            try:
                weight_threshold = float(filter_weight)
                if filter_weight_op == "gte":
                    exercises_list = [
                        e
                        for e in exercises_list
                        if e.weight is not None and e.weight >= weight_threshold
                    ]
                elif filter_weight_op == "lte":
                    exercises_list = [
                        e
                        for e in exercises_list
                        if e.weight is not None and e.weight <= weight_threshold
                    ]
                elif filter_weight_op == "eq":
                    exercises_list = [
                        e
                        for e in exercises_list
                        if e.weight is not None and e.weight == weight_threshold
                    ]
            except ValueError:
                # ignore value errors
                pass

        # sort exercises by usage count (descending)
        sorted_items = sorted(
            [(e.key, e) for e in exercises_list],
            key=lambda item: (
                exercises_stats.stats(item[0]).count
                if exercises_stats.stats(item[0])
                else 0
            ),
            reverse=True,
        )

        # create new exercises object with filtered results (don't mutate original)
        import copy

        exercises = copy.copy(all_exercises)
        exercises.exercise_by_key = dict(sorted_items)

        aspect_arg = flask.request.args.get("aspect")
        if aspect_arg:  # chart
            from mytral import charts
            from mytral.routes import COOKIE_MOBILE

            activities = ds.list_activities(
                user_id=user_id,
                dataset_name=ds.profile(user_id).dataset_name,
                skip_meta=False,
            )

            script, div = charts.exercises_in_time(
                exercises=exercises,
                activities=activities,
                is_mobile_view=bool(flask.session.get(COOKIE_MOBILE)),
            )

            return flask.render_template(
                JinjaTemplates.LIST,
                ff=ff,
                user_profile=ds.profile(user_id),
                exercises=exercises,
                exercises_stats=exercises_stats,
                unique_tags=unique_tags,
                filter_tag=filter_tag,
                filter_weight=filter_weight,
                filter_weight_op=filter_weight_op,
                aspect=aspect_arg,
                script=script,
                div=div,
            )
        else:  # list
            return flask.render_template(
                JinjaTemplates.LIST,
                ff=ff,
                user_profile=ds.profile(user_id),
                exercises=exercises,
                exercises_stats=exercises_stats,
                unique_tags=unique_tags,
                filter_tag=filter_tag,
                filter_weight=filter_weight,
                filter_weight_op=filter_weight_op,
            )

    else:
        flask.flash(
            message=f"{NAME_ENTITY} error - unsupported HTTP method", category="error"
        )
        return flask.redirect(flask.url_for("home"))


@flask_app.route(f"/settings/{ENTITIES}/create", methods=["GET", "POST"])
def settings_exercises_create():
    """Create:

    - HTTP GET: show form to create entity.
    - HTTP POST: actually create entity.

    """
    user_id = flask.session.get(COOKIE_USER)
    if not user_id:
        return flask.redirect(flask.url_for("login"))

    if flask.request.method == "GET":
        form = UpdateExerciseTypeForm()

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
        form = UpdateExerciseTypeForm()
        if form.validate_on_submit():
            tags_str = form.tags.data or ""
            tags_list = [tag.strip() for tag in tags_str.split(",") if tag.strip()]
            muscle_groups_csv = flask.request.form.get("muscle_groups", "")
            muscle_groups_list = mg.parse_muscle_groups_csv(muscle_groups_csv)
            muscle_groups_secondary_csv = flask.request.form.get(
                "muscle_groups_secondary", ""
            )
            muscle_groups_secondary_list = mg.parse_muscle_groups_csv(
                muscle_groups_secondary_csv
            )

            entity = user_settings.Exercise(
                name=form.name.data,
                description=form.description.data or "",
                weight=form.weight.data or 0.0,
                tags=tags_list,
                muscle_groups=muscle_groups_list,
                muscle_groups_secondary=muscle_groups_secondary_list,
            )

            ds.create_exercise(user_id=user_id, exercise=entity)

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


@flask_app.route(
    f"/settings/{ENTITIES}/<key>/photos/<blob_key>/update", methods=["GET", "POST"]
)
def settings_exercises_update_photo_metadata(key: str, blob_key: str):
    """Update metadata for a single exercise photo."""
    user_id = flask.session.get(COOKIE_USER)
    if not user_id:
        return flask.redirect(flask.url_for("login"))

    try:
        entity = ds.get_exercise(user_id=user_id, key=key)
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
        return flask.redirect(flask.url_for("settings_exercises_get", key=key))

    if flask.request.method == "GET":
        form.name.data = photo.name
        form.description.data = photo.description
        form.keywords.data = ", ".join(photo.keywords)
        return flask.render_template(
            "settings-exercises-photo-update.html",
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
            return flask.redirect(flask.url_for("settings_exercises_get", key=key))
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
        "settings-exercises-photo-update.html",
        ff=ff,
        user_profile=ds.profile(user_id),
        form=form,
        key=key,
        entity=entity,
        photo=photo,
    )


@flask_app.route(f"/settings/{ENTITIES}/<key>/update", methods=["GET", "POST"])
def settings_exercises_update(key: str):
    """Update entity:

    - HTTP GET: show form to update entity.
    - HTTP POST: actually update entity.

    """
    user_id = flask.session.get(COOKIE_USER)
    if not user_id:
        return flask.redirect(flask.url_for("login"))

    try:
        entity = ds.get_exercise(user_id=user_id, key=key)
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
        form = UpdateExerciseTypeForm()
        form.name.data = entity.name
        form.description.data = entity.description
        form.weight.data = entity.weight
        form.tags.data = ", ".join(entity.tags) if entity.tags else ""

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
            selected_muscles=entity.muscle_groups,
            selected_muscles_secondary=entity.muscle_groups_secondary,
            all_muscle_groups=mg.MUSCLE_GROUPS,
            markdown_link_text=build_photo_markdown_link_text,
            photo_edit_route="settings_exercises_update_photo_metadata",
            description_target_id=form.description.id,
        )

    elif flask.request.method == "POST":
        form = UpdateExerciseTypeForm()
        if form.validate_on_submit():
            tags_str = form.tags.data or ""
            tags_list = [tag.strip() for tag in tags_str.split(",") if tag.strip()]
            muscle_groups_csv = flask.request.form.get("muscle_groups", "")
            muscle_groups_list = mg.parse_muscle_groups_csv(muscle_groups_csv)
            muscle_groups_secondary_csv = flask.request.form.get(
                "muscle_groups_secondary", ""
            )
            muscle_groups_secondary_list = mg.parse_muscle_groups_csv(
                muscle_groups_secondary_csv
            )

            entity.name = form.name.data or ""
            entity.description = form.description.data or ""
            entity.weight = form.weight.data or 0.0
            entity.tags = tags_list
            entity.muscle_groups = muscle_groups_list
            entity.muscle_groups_secondary = muscle_groups_secondary_list

            ds.update_exercise(user_id=user_id, exercise=entity)

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
def settings_exercises_get(key: str):
    """View exercise details."""
    user_id = flask.session.get(COOKIE_USER)
    if not user_id:
        return flask.redirect(flask.url_for("login"))

    try:
        entity = ds.get_exercise(user_id=user_id, key=key)
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
        muscle_highlights=build_muscle_highlights(
            entity.muscle_groups,
            entity.muscle_groups_secondary,
        ),
        photos=photos,
        upload_form=forms.UploadEntityPhotoForm(prefix="epu"),
        delete_form=forms.DeleteEntityPhotoForm(prefix="epd"),
        highlight_form=forms.DeleteEntityPhotoForm(prefix="eph"),
        markdown_link_text=build_photo_markdown_link_text,
        photo_edit_route="settings_exercises_update_photo_metadata",
    )


@flask_app.route(f"/settings/{ENTITIES}/<key>/photos/upload", methods=["GET", "POST"])
def settings_exercises_upload_photo(key: str):
    """Upload a photo for an exercise."""
    user_id = flask.session.get(COOKIE_USER)
    if not user_id:
        return flask.redirect(flask.url_for("login"))

    upload_form = forms.UploadEntityPhotoForm(prefix="epu")
    entity = ds.get_exercise(user_id=user_id, key=key)

    if flask.request.method == "GET":
        return flask.render_template(
            "settings-exercises-photo-upload.html",
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
                owner_kind=BlobOwnerKind.EXERCISE,
                kind=BlobKind.EXERCISE_PHOTO,
                file_stream=f.stream,
                original_filename=original_filename,
                current_count=len(entity.photo_blob_keys),
            )
            entity.photo_blob_keys = list(entity.photo_blob_keys) + [meta.blob_key]
            if not entity.highlight_photo_blob_key:
                entity.highlight_photo_blob_key = meta.blob_key
            try:
                ds.update_exercise(user_id=user_id, exercise=entity)
                flask.flash(message="Photo uploaded", category="success")
            except Exception as exc:
                svc.delete_photo(user_id, meta.blob_key)
                raise exc
        except Exception as e:
            flask.flash(message=f"Photo upload error: {e}", category="error")
    else:
        flask.flash(message="Photo upload form validation failed", category="error")

    return flask.redirect(flask.url_for("settings_exercises_get", key=key))


@flask_app.route(f"/settings/{ENTITIES}/<key>/photos/<blob_key>", methods=["GET"])
def settings_exercises_photo(key: str, blob_key: str):
    """Serve an exercise photo."""
    user_id = flask.session.get(COOKIE_USER)
    if not user_id:
        return flask.redirect(flask.url_for("login"))
    try:
        entity = ds.get_exercise(user_id=user_id, key=key)
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
        return flask.redirect(flask.url_for("settings_exercises_get", key=key))


@flask_app.route(
    f"/settings/{ENTITIES}/<key>/photos/<blob_key>/thumbnail", methods=["GET"]
)
def settings_exercises_photo_thumbnail(key: str, blob_key: str):
    """Serve an exercise photo thumbnail."""
    user_id = flask.session.get(COOKIE_USER)
    if not user_id:
        return flask.redirect(flask.url_for("login"))
    try:
        entity = ds.get_exercise(user_id=user_id, key=key)
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
        return flask.redirect(flask.url_for("settings_exercises_get", key=key))


@flask_app.route(
    f"/settings/{ENTITIES}/<key>/photos/<blob_key>/delete", methods=["POST"]
)
def settings_exercises_delete_photo(key: str, blob_key: str):
    """Delete an exercise photo."""
    user_id = flask.session.get(COOKIE_USER)
    if not user_id:
        return flask.redirect(flask.url_for("login"))

    delete_form = forms.DeleteEntityPhotoForm(prefix="epd")
    if delete_form.validate_on_submit():
        try:
            entity = ds.get_exercise(user_id=user_id, key=key)
            if blob_key not in entity.photo_blob_keys:
                flask.abort(404)
            svc = _entity_photo_service()
            svc.delete_photo(user_id=user_id, blob_key=blob_key)
            new_keys = [bk for bk in entity.photo_blob_keys if bk != blob_key]
            entity.photo_blob_keys = new_keys
            if entity.highlight_photo_blob_key == blob_key:
                entity.highlight_photo_blob_key = new_keys[0] if new_keys else ""
            ds.update_exercise(user_id=user_id, exercise=entity)
            flask.flash(message="Photo deleted", category="success")
        except Exception as e:
            flask.flash(message=f"Photo delete error: {e}", category="error")
    else:
        flask.flash(message="Photo delete form validation failed", category="error")

    return flask.redirect(flask.url_for("settings_exercises_get", key=key))


@flask_app.route(
    f"/settings/{ENTITIES}/<key>/photos/<blob_key>/highlight", methods=["POST"]
)
def settings_exercises_highlight_photo(key: str, blob_key: str):
    """Set a photo as the highlight photo for an exercise."""
    user_id = flask.session.get(COOKIE_USER)
    if not user_id:
        return flask.redirect(flask.url_for("login"))

    highlight_form = forms.DeleteEntityPhotoForm(prefix="eph")
    if highlight_form.validate_on_submit():
        try:
            entity = ds.get_exercise(user_id=user_id, key=key)
            if blob_key not in entity.photo_blob_keys:
                flask.abort(404)
            entity.highlight_photo_blob_key = blob_key
            ds.update_exercise(user_id=user_id, exercise=entity)
            flask.flash(message="Highlight photo updated", category="success")
        except Exception as e:
            flask.flash(message=f"Highlight photo error: {e}", category="error")
    else:
        flask.flash(message="Highlight form validation failed", category="error")

    return flask.redirect(flask.url_for("settings_exercises_get", key=key))


@flask_app.route(f"/settings/{ENTITIES}/<key>/delete", methods=["GET", "POST"])
def settings_exercises_delete(key: str):
    """Delete entity:

    - HTTP GET: Do you really want to delete entity?
    - HTTP POST: actually delete entity.

    """
    user_id = flask.session.get(COOKIE_USER)
    if not user_id:
        return flask.redirect(flask.url_for("login"))

    form = DeleteExerciseTypeForm()

    if flask.request.method == "POST":
        if form.validate_on_submit():
            try:
                # best-effort blob cleanup before deleting entity
                try:
                    entity = ds.get_exercise(user_id=user_id, key=key)
                    svc = _entity_photo_service()
                    for bk in entity.photo_blob_keys:
                        svc.delete_photo(user_id, bk)
                except Exception:
                    pass

                ds.delete_exercise(user_id=user_id, key=key)

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
        entity = ds.get_exercise(user_id=user_id, key=key)
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
