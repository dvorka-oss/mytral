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
from mytral.blueprints import gear_crud


@pytest.mark.mytral
def test_settings_gear_get_renders_lightbox_photo_gallery(monkeypatch):
    # GIVEN
    photo = SimpleNamespace(
        blob_key="blob-1",
        name="Bike",
        original_file_name="bike.jpg",
        description="",
        keywords=[],
    )

    class _Gear:
        key = "gear-1"
        name = "Bike"
        activity_type_key = "cycling"
        vendor = ""
        model = ""
        size = ""
        purchased = ""
        comment = ""
        is_default = False
        retired = False
        tcoo_total = 0
        tcoo_base = 0
        tcoo_cost = 0
        tcoo_additional = 0
        url = ""
        photo_blob_keys = [photo.blob_key]
        highlight_photo_blob_key = photo.blob_key

        def get_components(self, include_retired=False):
            return []

        def get_predecessor_chain(self, component_key):
            return []

    class _ActivityTypes:
        def color(self, key):
            return "#000000"

        def emoji(self, key):
            return "B"

        def name(self, key):
            return "Bike"

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
        if endpoint == "settings_gear_photo":
            return f"/settings/gears/{values['key']}/photos/{values['blob_key']}"
        if endpoint == "settings_gear_photo_thumbnail":
            return (
                f"/settings/gears/{values['key']}/photos/{values['blob_key']}/thumbnail"
            )
        if endpoint == "settings_gear_upload_photo":
            return f"/settings/gears/{values['key']}/photos/upload"
        if endpoint == "settings_gear_update_photo_metadata":
            return f"/settings/gears/{values['key']}/photos/{values['blob_key']}/update"
        if endpoint == "settings_gear_delete_photo":
            return f"/settings/gears/{values['key']}/photos/{values['blob_key']}/delete"
        if endpoint == "settings_gear_highlight_photo":
            return (
                f"/settings/gears/{values['key']}/photos/{values['blob_key']}/highlight"
            )
        if endpoint == "settings_gear_list":
            return "/settings/gears"
        if endpoint == "settings_gear_update":
            return f"/settings/gears/{values['key']}/update"
        if endpoint == "settings_activity_types_list":
            return "/settings/activity-types"
        if endpoint == "profile":
            return "/profile"
        return f"/{endpoint}"

    monkeypatch.setattr(
        gear_crud.ds, "get_gear", lambda user_id, key, dataset_name: _Gear()
    )
    monkeypatch.setattr(gear_crud.ds, "profile", lambda user_id: profile)
    monkeypatch.setattr(
        gear_crud.ds, "list_activity_types", lambda user_id: _ActivityTypes()
    )
    monkeypatch.setattr(
        gear_crud.ds, "recompute_gear_service_intervals", lambda **kwargs: None
    )
    monkeypatch.setattr(gear_crud, "_entity_photo_service", lambda: _PhotoService())
    monkeypatch.setitem(routes.flask_app.jinja_env.globals, "url_for", fake_url_for)

    with routes.flask_app.test_request_context(
        "/settings/gears/gear-1/get",
        method="GET",
    ):
        flask.session[routes.COOKIE_USER] = "user-1"

        # WHEN
        html = gear_crud.settings_gear_get("gear-1")

    # THEN
    if hasattr(html, "get_data"):
        html = html.get_data(as_text=True)
    normalized = " ".join(html.split())
    assert (
        'data-fslightbox="gear-photos" data-type="image" '
        'href="/settings/gears/gear-1/photos/blob-1" class="d-block"'
    ) in normalized
    assert 'src="/settings/gears/gear-1/photos/blob-1/thumbnail"' in normalized
    assert 'href="/settings/gears/gear-1/photos/upload"' in normalized
    assert 'href="/settings/gears/gear-1/photos/blob-1/update"' in normalized
    print("DONE: gear photos open in the lightbox gallery")


@pytest.mark.mytral
def test_settings_gear_upload_photo_get_renders_template(monkeypatch):
    # GIVEN
    gear = SimpleNamespace(photo_blob_keys=["blob-1"])
    captured = {}

    class _Form:
        def __init__(self, prefix=""):
            self.prefix = prefix

    def fake_render_template(template_name, **context):
        captured["template_name"] = template_name
        captured["context"] = context
        return "ok"

    monkeypatch.setattr(
        gear_crud.ds, "profile", lambda user_id: SimpleNamespace(dataset_name="default")
    )
    monkeypatch.setattr(
        gear_crud.ds, "get_gear", lambda user_id, key, dataset_name: gear
    )
    monkeypatch.setattr(gear_crud.forms, "UploadEntityPhotoForm", _Form)
    monkeypatch.setattr(flask, "render_template", fake_render_template)

    with routes.flask_app.test_request_context(
        "/settings/gears/gear-1/photos/upload",
        method="GET",
    ):
        flask.session[routes.COOKIE_USER] = "user-1"

        # WHEN
        response = gear_crud.settings_gear_upload_photo("gear-1")

    # THEN
    assert response == "ok"
    assert captured["template_name"] == "settings-gear-photo-upload.html"
    assert captured["context"]["current_count"] == 1
    assert captured["context"]["gear"] is gear
    print("DONE: gear photo upload page renders on GET")


@pytest.mark.mytral
def test_settings_gear_update_photo_metadata_get_renders_template(monkeypatch):
    # GIVEN
    gear = SimpleNamespace(photo_blob_keys=["blob-1"])
    photo = SimpleNamespace(
        blob_key="blob-1",
        name="gear-photo",
        description="desc",
        keywords=["k1", "k2"],
        original_file_name="gear.jpg",
    )
    captured = {}

    class _BlobStore:
        def get_blob_metadata(self, user_id, blob_key):
            return photo

    def fake_render_template(template_name, **context):
        captured["template_name"] = template_name
        captured["context"] = context
        return "ok"

    monkeypatch.setattr(
        gear_crud.ds,
        "profile",
        lambda user_id: SimpleNamespace(dataset_name="default"),
    )
    monkeypatch.setattr(
        gear_crud.ds,
        "get_gear",
        lambda user_id, key, dataset_name: gear,
    )
    monkeypatch.setattr(gear_crud.mytral, "app_blobstore", _BlobStore())
    monkeypatch.setattr(flask, "render_template", fake_render_template)

    with routes.flask_app.test_request_context(
        "/settings/gears/gear-1/photos/blob-1/update",
        method="GET",
    ):
        flask.session[routes.COOKIE_USER] = "user-1"

        # WHEN
        response = gear_crud.settings_gear_update_photo_metadata("gear-1", "blob-1")

    # THEN
    assert response == "ok"
    assert captured["template_name"] == "settings-gear-photo-update.html"
    assert captured["context"]["photo"] is photo
    assert captured["context"]["gear"] is gear
    print("DONE: gear photo metadata editor renders on GET")
