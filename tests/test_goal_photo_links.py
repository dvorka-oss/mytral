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
from mytral.blueprints import goal_crud


@pytest.mark.mytral
def test_settings_goal_update_passes_photo_management_context(monkeypatch):
    # GIVEN
    entity = SimpleNamespace(
        key="goal-1",
        name="Build endurance",
        activity_type="running",
        description="desc",
        tag="annual",
        done=False,
        urgency=0.4,
        importance=0.8,
        photo_blob_keys=["blob-1"],
        highlight_photo_blob_key="blob-1",
    )
    photos = [SimpleNamespace(blob_key="blob-1", name="goal-photo")]
    captured = {}

    class _ActivityChoices:
        def choices(self):
            return [("running", "Running")]

    class _PhotoService:
        def list_photos(self, user_id, blob_keys):
            return photos

    def fake_render_template(template_name, **context):
        captured["template_name"] = template_name
        captured["context"] = context
        return "ok"

    monkeypatch.setattr(goal_crud.ds, "get_goal", lambda user_id, key: entity)
    monkeypatch.setattr(
        goal_crud.ds, "list_activity_types", lambda user_id: _ActivityChoices()
    )
    monkeypatch.setattr(goal_crud.ds, "profile", lambda user_id: {})
    monkeypatch.setattr(goal_crud, "_entity_photo_service", lambda: _PhotoService())
    monkeypatch.setattr(flask, "render_template", fake_render_template)

    with routes.flask_app.test_request_context(
        "/settings/goals/goal-1/update",
        method="GET",
    ):
        flask.session[routes.COOKIE_USER] = "user-1"

        # WHEN
        response = goal_crud.settings_goal_update("goal-1")

    # THEN
    assert response == "ok"
    assert captured["template_name"] == goal_crud.JinjaTemplates.UPDATE
    assert captured["context"]["entity"] is entity
    assert captured["context"]["photos"] == photos
    assert captured["context"]["upload_form"] is not None
    assert captured["context"]["delete_form"] is not None
    assert captured["context"]["highlight_form"] is not None
    print("DONE: goal update template receives photo management context")


@pytest.mark.mytral
def test_settings_goal_get_renders_lightbox_photo_gallery(monkeypatch):
    # GIVEN
    photo = SimpleNamespace(
        blob_key="blob-1",
        name="Goal cover",
        original_file_name="goal.jpg",
        description="",
        keywords=[],
    )
    entity = SimpleNamespace(
        key="goal-1",
        name="Goal",
        description="",
        activity_type="running",
        tag="annual",
        done=False,
        urgency=0.5,
        importance=0.5,
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
        if endpoint == "settings_goal_photo":
            return f"/settings/goals/{values['key']}/photos/{values['blob_key']}"
        if endpoint == "settings_goal_photo_thumbnail":
            return (
                f"/settings/goals/{values['key']}/photos/{values['blob_key']}/thumbnail"
            )
        if endpoint == "settings_goal_upload_photo":
            return f"/settings/goals/{values['key']}/photos/upload"
        if endpoint == "settings_goal_update_photo_metadata":
            return f"/settings/goals/{values['key']}/photos/{values['blob_key']}/update"
        if endpoint == "settings_goal_delete_photo":
            return f"/settings/goals/{values['key']}/photos/{values['blob_key']}/delete"
        if endpoint == "settings_goal_highlight_photo":
            return (
                f"/settings/goals/{values['key']}/photos/{values['blob_key']}/highlight"
            )
        if endpoint == "settings_goals_list":
            return "/settings/goals"
        if endpoint == "settings_goal_update":
            return f"/settings/goals/{values['key']}/update"
        if endpoint == "profile":
            return "/profile"
        return f"/{endpoint}"

    monkeypatch.setattr(goal_crud.ds, "get_goal", lambda user_id, key: entity)
    monkeypatch.setattr(goal_crud.ds, "profile", lambda user_id: profile)
    monkeypatch.setattr(goal_crud, "_entity_photo_service", lambda: _PhotoService())
    monkeypatch.setitem(routes.flask_app.jinja_env.globals, "url_for", fake_url_for)

    with routes.flask_app.test_request_context(
        "/settings/goals/goal-1/get",
        method="GET",
    ):
        flask.session[routes.COOKIE_USER] = "user-1"

        # WHEN
        html = goal_crud.settings_goal_get("goal-1")

    # THEN
    normalized = " ".join(html.split())
    assert (
        'data-fslightbox="goal-photos" data-type="image" '
        'href="/settings/goals/goal-1/photos/blob-1" class="d-block"'
    ) in normalized
    assert 'src="/settings/goals/goal-1/photos/blob-1/thumbnail"' in normalized
    assert 'href="/settings/goals/goal-1/photos/upload"' in normalized
    assert 'href="/settings/goals/goal-1/photos/blob-1/update"' in normalized
    assert "Highlight" in normalized
    assert "icon-tabler-star" not in normalized
    print("DONE: goal photos open in the lightbox gallery")


@pytest.mark.mytral
def test_settings_goal_upload_photo_get_renders_template(monkeypatch):
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

    monkeypatch.setattr(goal_crud.ds, "get_goal", lambda user_id, key: entity)
    monkeypatch.setattr(
        goal_crud.ds,
        "profile",
        lambda user_id: SimpleNamespace(dataset_name="default"),
    )
    monkeypatch.setattr(goal_crud.forms, "UploadEntityPhotoForm", _Form)
    monkeypatch.setattr(flask, "render_template", fake_render_template)

    with routes.flask_app.test_request_context(
        "/settings/goals/goal-1/photos/upload",
        method="GET",
    ):
        flask.session[routes.COOKIE_USER] = "user-1"

        # WHEN
        response = goal_crud.settings_goal_upload_photo("goal-1")

    # THEN
    assert response == "ok"
    assert captured["template_name"] == "settings-goals-photo-upload.html"
    assert captured["context"]["current_count"] == 1
    assert captured["context"]["entity"] is entity
    print("DONE: goal photo upload page renders on GET")


@pytest.mark.mytral
def test_settings_goal_update_photo_metadata_get_renders_template(monkeypatch):
    # GIVEN
    entity = SimpleNamespace(photo_blob_keys=["blob-1"])
    photo = SimpleNamespace(
        blob_key="blob-1",
        name="goal-photo",
        description="desc",
        keywords=["k1", "k2"],
        original_file_name="goal.jpg",
    )
    captured = {}

    class _BlobStore:
        def get_blob_metadata(self, user_id, blob_key):
            return photo

    def fake_render_template(template_name, **context):
        captured["template_name"] = template_name
        captured["context"] = context
        return "ok"

    monkeypatch.setattr(goal_crud.ds, "get_goal", lambda user_id, key: entity)
    monkeypatch.setattr(
        goal_crud.ds,
        "profile",
        lambda user_id: SimpleNamespace(dataset_name="default"),
    )
    monkeypatch.setattr(goal_crud.mytral, "app_blobstore", _BlobStore())
    monkeypatch.setattr(flask, "render_template", fake_render_template)

    with routes.flask_app.test_request_context(
        "/settings/goals/goal-1/photos/blob-1/update",
        method="GET",
    ):
        flask.session[routes.COOKIE_USER] = "user-1"

        # WHEN
        response = goal_crud.settings_goal_update_photo_metadata("goal-1", "blob-1")

    # THEN
    assert response == "ok"
    assert captured["template_name"] == "settings-goals-photo-update.html"
    assert captured["context"]["photo"] is photo
    assert captured["context"]["entity"] is entity
    print("DONE: goal photo metadata editor renders on GET")
