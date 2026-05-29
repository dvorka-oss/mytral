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
from types import SimpleNamespace

import flask
import pytest

from mytral import routes
from mytral.blueprints import exercise_types_crud as exercise_crud


@pytest.mark.mytral
def test_build_photo_markdown_link_text_uses_label_and_url():
    # GIVEN
    photo_name = "Front squat"
    photo_url = "http://127.0.0.1:5000/settings/exercises/abc/photos/def"

    # WHEN
    markdown = exercise_crud.build_photo_markdown_link_text(photo_name, photo_url)

    # THEN
    assert markdown == f"[{photo_name}]({photo_url})"
    print("DONE: photo markdown link text is built correctly")


@pytest.mark.mytral
def test_build_photo_markdown_link_text_falls_back_to_photo_label():
    # GIVEN
    photo_url = "http://127.0.0.1:5000/settings/exercises/abc/photos/def"

    # WHEN
    markdown = exercise_crud.build_photo_markdown_link_text("   ", photo_url)

    # THEN
    assert markdown == f"[photo]({photo_url})"
    print("DONE: photo markdown link text fallback is correct")


@pytest.mark.mytral
def test_settings_exercises_update_passes_entity_to_template(monkeypatch):
    # GIVEN
    entity = SimpleNamespace(
        name="Front squat",
        description="",
        weight=0.0,
        tags=[],
        muscle_groups=[],
        muscle_groups_secondary=[],
        photo_blob_keys=[],
    )
    captured = {}

    class _PhotoService:
        def list_photos(self, user_id, blob_keys):
            return []

    def fake_render_template(template_name, **context):
        captured["template_name"] = template_name
        captured["context"] = context
        return "ok"

    monkeypatch.setattr(exercise_crud.ds, "get_exercise", lambda user_id, key: entity)
    monkeypatch.setattr(exercise_crud.ds, "profile", lambda user_id: {})
    monkeypatch.setattr(exercise_crud, "_entity_photo_service", lambda: _PhotoService())
    monkeypatch.setattr(flask, "render_template", fake_render_template)

    with routes.flask_app.test_request_context(
        "/settings/exercises/abc/update",
        method="GET",
    ):
        flask.session[routes.COOKIE_USER] = "user-1"

        # WHEN
        response = exercise_crud.settings_exercises_update("abc")

    # THEN
    assert response == "ok"
    assert captured["template_name"] == exercise_crud.JinjaTemplates.UPDATE
    assert captured["context"]["entity"] is entity
    print("DONE: exercise update template receives entity context")


@pytest.mark.mytral
def test_settings_exercises_get_renders_lightbox_photo_gallery(monkeypatch):
    # GIVEN
    photo = SimpleNamespace(
        blob_key="blob-1",
        name="Front squat",
        original_file_name="front.jpg",
        description="",
        keywords=[],
    )
    entity = SimpleNamespace(
        key="exercise-1",
        name="Front squat",
        description="",
        weight=0.0,
        tags=[],
        muscle_groups=[],
        muscle_groups_secondary=[],
        photo_blob_keys=[photo.blob_key],
        highlight_photo_blob_key=photo.blob_key,
    )
    profile = SimpleNamespace(
        user="User",
        expert=False,
        dataset_name="default",
        strava_client_id=None,
        strava_client_secret=None,
    )

    class _PhotoService:
        def list_photos(self, user_id, blob_keys):
            return [photo]

    def fake_url_for(endpoint, **values):
        if endpoint == "settings_exercises_photo":
            return f"/settings/exercises/{values['key']}/photos/{values['blob_key']}"
        if endpoint == "settings_exercises_photo_thumbnail":
            return (
                f"/settings/exercises/{values['key']}/photos/{values['blob_key']}"
                "/thumbnail"
            )
        if endpoint == "settings_exercises_upload_photo":
            return f"/settings/exercises/{values['key']}/photos/upload"
        if endpoint == "settings_exercises_update_photo_metadata":
            return (
                f"/settings/exercises/{values['key']}/photos"
                f"/{values['blob_key']}/update"
            )
        if endpoint == "settings_exercises_delete_photo":
            return (
                f"/settings/exercises/{values['key']}/photos"
                f"/{values['blob_key']}/delete"
            )
        if endpoint == "settings_exercises_highlight_photo":
            return (
                f"/settings/exercises/{values['key']}/photos/{values['blob_key']}"
                "/highlight"
            )
        if endpoint == "settings_exercises_list":
            return "/settings/exercises"
        if endpoint == "profile":
            return "/profile"
        return f"/{endpoint}"

    monkeypatch.setattr(exercise_crud.ds, "get_exercise", lambda user_id, key: entity)
    monkeypatch.setattr(exercise_crud.ds, "profile", lambda user_id: profile)
    monkeypatch.setattr(exercise_crud, "_entity_photo_service", lambda: _PhotoService())
    monkeypatch.setitem(routes.flask_app.jinja_env.globals, "url_for", fake_url_for)

    with routes.flask_app.test_request_context(
        "/settings/exercises/exercise-1/get",
        method="GET",
    ):
        flask.session[routes.COOKIE_USER] = "user-1"

        # WHEN
        html = exercise_crud.settings_exercises_get("exercise-1")

    # THEN
    normalized = " ".join(html.split())
    assert (
        'data-fslightbox="exercise-photos" data-type="image" '
        'href="/settings/exercises/exercise-1/photos/blob-1" class="d-block"'
    ) in normalized
    assert 'src="/settings/exercises/exercise-1/photos/blob-1/thumbnail"' in normalized
    assert "Highlight" in normalized
    assert "icon-tabler-star" not in normalized
    print("DONE: exercise photos open in the lightbox gallery")


@pytest.mark.mytral
def test_settings_exercises_upload_photo_get_renders_template(monkeypatch):
    # GIVEN
    entity = SimpleNamespace(photo_blob_keys=["blob-1"])
    captured = {}

    class _Form:
        def __init__(self, prefix=""):
            self.prefix = prefix

    def fake_render_template(template_name, **context):
        captured["template_name"] = template_name
        captured["context"] = context
        return "ok"

    monkeypatch.setattr(
        exercise_crud.ds,
        "get_exercise",
        lambda user_id, key: entity,
    )
    monkeypatch.setattr(
        exercise_crud.ds,
        "profile",
        lambda user_id: SimpleNamespace(dataset_name="default"),
    )
    monkeypatch.setattr(exercise_crud.forms, "UploadEntityPhotoForm", _Form)
    monkeypatch.setattr(flask, "render_template", fake_render_template)

    with routes.flask_app.test_request_context(
        "/settings/exercises/abc/photos/upload",
        method="GET",
    ):
        flask.session[routes.COOKIE_USER] = "user-1"

        # WHEN
        response = exercise_crud.settings_exercises_upload_photo("abc")

    # THEN
    assert response == "ok"
    assert captured["template_name"] == "settings-exercises-photo-upload.html"
    assert captured["context"]["current_count"] == 1
    assert captured["context"]["entity"] is entity
    print("DONE: exercise photo upload page renders on GET")


@pytest.mark.mytral
def test_build_muscle_highlights_uses_primary_and_secondary_classes():
    # GIVEN
    primary = ["pecs", "lats", "pecs"]
    secondary = ["delts", "lats", ""]

    # WHEN
    highlights = exercise_crud.build_muscle_highlights(primary, secondary)

    # THEN
    assert highlights["pecs"] == "state-active"
    assert highlights["lats"] == "state-active"
    assert highlights["delts"] == "state-secondary"
    print("DONE: muscle highlight classes are built correctly")


@pytest.mark.mytral
def test_markdown_filter_renders_photo_links():
    # GIVEN
    markdown = "[Front squat](http://127.0.0.1:5000/settings/exercises/abc/photos/def)"

    # WHEN
    html = routes.markdown_filter(markdown)

    # THEN
    assert 'href="http://127.0.0.1:5000/settings/exercises/abc/photos/def"' in html
    assert ">Front squat<" in html
    print("DONE: markdown filter renders photo links")


@pytest.mark.mytral
def test_markdown_filter_renders_photo_images():
    # GIVEN
    markdown = "![me.jpeg](http://127.0.0.1:5000/settings/exercises/abc/photos/def)"

    # WHEN
    html = routes.markdown_filter(markdown)

    # THEN
    assert "<img" in html
    assert 'src="http://127.0.0.1:5000/settings/exercises/abc/photos/def"' in html
    assert 'alt="me.jpeg"' in html
    print("DONE: markdown filter renders photo images")


@pytest.mark.mytral
def test_update_activity_photo_metadata_get_renders_template(monkeypatch):
    # GIVEN
    photo = SimpleNamespace(
        blob_key="blob-1",
        name="Front squat",
        original_file_name="front.jpg",
        description="",
        keywords=[],
    )
    captured = {}

    class _BlobService:
        def list_photos(self, user_id, activity_key):
            return [photo]

    def fake_render_template(template_name, **context):
        captured["template_name"] = template_name
        captured["context"] = context
        return "ok"

    monkeypatch.setattr(routes, "_blob_service", lambda: _BlobService())
    monkeypatch.setattr(routes.ds, "profile", lambda user_id: {})
    monkeypatch.setattr(flask, "render_template", fake_render_template)

    with routes.flask_app.test_request_context(
        "/app/activities/act-1/blob/photos/blob-1/update",
        method="GET",
    ):
        flask.session[routes.COOKIE_USER] = "user-1"

        # WHEN
        response = routes.update_activity_photo_metadata("act-1", "blob-1")

    # THEN
    assert response == "ok"
    assert captured["template_name"] == "activity-photo-update.html"
    assert captured["context"]["photo"] is photo
    print("DONE: activity photo metadata editor renders on GET")
