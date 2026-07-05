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

"""Regression tests for BHR blueprint fixes (auth, outfit, gear components)."""

from types import SimpleNamespace

import flask
import pytest

from mytral import routes
from mytral.blueprints import auth_uri_space
from mytral.blueprints import gear_components_crud
from mytral.blueprints import gear_crud
from mytral.blueprints import outfit_crud

#
# H3 - login POST must validate the form (CSRF) before authenticating
#


@pytest.mark.mytral
def test_login_post_without_csrf_is_rejected(monkeypatch):
    # GIVEN - CSRF enabled and a POST with no token; is_user_name must never run
    called = {"is_user_name": False}
    monkeypatch.setitem(routes.flask_app.config, "WTF_CSRF_ENABLED", True)
    monkeypatch.setattr(
        auth_uri_space.app_ds,
        "is_user_name",
        lambda user_name: called.__setitem__("is_user_name", True) or True,
    )

    with routes.flask_app.test_request_context(
        "/login",
        method="POST",
        data={"username": "alice", "password": "secret123"},
    ):
        # WHEN - the login handler runs without a valid CSRF token
        response = auth_uri_space.login()

    # THEN - it redirects back to login and never reaches authentication
    assert response.status_code == 302
    assert "/login" in response.headers["Location"]
    assert called["is_user_name"] is False
    print("DONE: login POST without CSRF is rejected before authentication")


#
# M12 - outfit create must not IndexError when the user has no activity types
#


@pytest.mark.mytral
def test_outfit_create_with_no_activity_types_does_not_crash(monkeypatch):
    # GIVEN - a user whose activity-type choices list is empty
    monkeypatch.setattr(
        outfit_crud.ds,
        "list_activity_types",
        lambda user_id: SimpleNamespace(choices=lambda: []),
    )
    monkeypatch.setattr(
        outfit_crud.ds, "profile", lambda user_id: SimpleNamespace(dataset_name="d")
    )
    monkeypatch.setattr(flask, "render_template", lambda *a, **k: "ok")

    with routes.flask_app.test_request_context("/settings/outfits/create"):
        flask.session[routes.COOKIE_USER] = "user-1"

        # WHEN - the create form is rendered
        result = outfit_crud.settings_outfit_create()

    # THEN - no IndexError; the page renders
    assert result == "ok"
    print("DONE: outfit create with zero activity types does not crash")


#
# M14 - gear component service delete on a bad gear key redirects, not 500
#


@pytest.mark.mytral
def test_gear_component_service_delete_bad_gear_key_redirects(monkeypatch):
    # GIVEN - a gear lookup that raises (missing key)
    monkeypatch.setattr(
        gear_components_crud.ds,
        "profile",
        lambda user_id: SimpleNamespace(dataset_name="d"),
    )

    def _raise(*args, **kwargs):
        raise ValueError("gear with key 'BADKEY' not found")

    monkeypatch.setattr(gear_components_crud.ds, "get_gear", _raise)

    with routes.flask_app.test_request_context(
        "/settings/gears/BADKEY/components/c1/service/0/delete",
        method="POST",
    ):
        flask.session[routes.COOKIE_USER] = "user-1"

        # WHEN - deleting a service entry on a non-existent gear
        response = gear_components_crud.settings_gear_component_service_delete(
            "BADKEY", "c1", 0
        )

        # the redirect target lives in the gear_crud blueprint
        expected = flask.url_for(gear_crud.settings_gear_list.__name__)

    # THEN - a graceful redirect (not an unhandled 500)
    assert response.status_code == 302
    assert response.headers["Location"] == expected
    print("DONE: gear component service delete on bad key redirects gracefully")
