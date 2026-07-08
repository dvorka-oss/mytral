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
import pytest

from mytral import config
from mytral.blueprints import auth_uri_space


def _fake_render_template(captured, **kwargs):
    def render(template_name, **context):
        captured["template_name"] = template_name
        captured["context"] = context
        return "ok"

    return render


@pytest.mark.mytral
def test_login_get_auto_logs_in_when_single_desktop_auto_login_user(monkeypatch):
    # GIVEN a desktop installation with exactly one auto-login enabled user
    monkeypatch.setattr(
        auth_uri_space.app_config, "incarnation", config.MytralIncarnation.DESKTOP
    )
    monkeypatch.setattr(
        auth_uri_space.ds,
        "list_profile_names",
        lambda auto_login=False: {"athlete": "user-1"},
    )

    with auth_uri_space.flask_app.test_request_context("/login", method="GET"):
        # WHEN
        response = auth_uri_space.login()

        # THEN - silently logged in and redirected to the dashboard
        assert response.status_code == 302
        assert response.location == flask.url_for("home")
        assert flask.session[auth_uri_space.COOKIE_USER] == "user-1"

    print("DONE: GET /login auto-logs in the sole desktop auto-login user")


@pytest.mark.mytral
def test_login_get_auto_migrates_before_auto_login(monkeypatch):
    # GIVEN a desktop installation with one auto-login user and a pending
    # data migration that succeeds
    monkeypatch.setattr(
        auth_uri_space.app_config, "incarnation", config.MytralIncarnation.DESKTOP
    )
    monkeypatch.setattr(
        auth_uri_space.ds,
        "list_profile_names",
        lambda auto_login=False: {"athlete": "user-1"},
    )
    calls = {"migrated": False}

    def _fake_migration():
        calls["migrated"] = True
        return True

    monkeypatch.setattr(auth_uri_space, "_run_fs_migration", _fake_migration)

    with auth_uri_space.flask_app.test_request_context("/login", method="GET"):
        # WHEN
        response = auth_uri_space.login()

        # THEN - migration ran first, then the user was silently logged in
        assert calls["migrated"] is True
        assert response.status_code == 302
        assert response.location == flask.url_for("home")
        assert flask.session[auth_uri_space.COOKIE_USER] == "user-1"

    print("DONE: GET /login runs data migration before auto-login")


@pytest.mark.mytral
def test_login_get_does_not_auto_login_when_migration_fails(monkeypatch):
    # GIVEN a desktop installation with one auto-login user and a pending
    # data migration that fails
    monkeypatch.setattr(
        auth_uri_space.app_config, "incarnation", config.MytralIncarnation.DESKTOP
    )
    monkeypatch.setattr(
        auth_uri_space.ds,
        "list_profile_names",
        lambda auto_login=False: {"athlete": "user-1"},
    )
    monkeypatch.setattr(auth_uri_space, "_run_fs_migration", lambda: False)
    monkeypatch.setattr(
        auth_uri_space.config.MytralPersistenceFsConfig,
        "is_migrate",
        lambda self: True,
    )
    captured = {}
    monkeypatch.setattr(flask, "render_template", _fake_render_template(captured))

    with auth_uri_space.flask_app.test_request_context("/login", method="GET"):
        # WHEN
        response = auth_uri_space.login()

        # THEN - no silent login; the login page (with migration UI) is shown
        assert response == "ok"
        assert captured["template_name"] == "log-in.html"
        assert captured["context"]["is_migrate"] is True
        assert auth_uri_space.COOKIE_USER not in flask.session

    print("DONE: GET /login does not auto-login when data migration fails")


@pytest.mark.mytral
def test_login_get_does_not_auto_login_when_suppressed_after_logout(monkeypatch):
    # GIVEN a desktop installation where auto-login was just suppressed (logout)
    monkeypatch.setattr(
        auth_uri_space.app_config, "incarnation", config.MytralIncarnation.DESKTOP
    )
    monkeypatch.setattr(
        auth_uri_space.ds,
        "list_profile_names",
        lambda auto_login=False: {"athlete": "user-1"},
    )
    monkeypatch.setattr(
        auth_uri_space.config.MytralPersistenceFsConfig,
        "is_migrate",
        lambda self: False,
    )
    captured = {}
    monkeypatch.setattr(flask, "render_template", _fake_render_template(captured))

    with auth_uri_space.flask_app.test_request_context("/login", method="GET"):
        flask.session[auth_uri_space.COOKIE_AUTO_LOGIN_SUPPRESSED] = True

        # WHEN
        response = auth_uri_space.login()

        # THEN - regular login page is rendered, no silent login happens
        assert response == "ok"
        assert captured["context"]["auto_login_usernames"] == ["athlete"]
        assert auth_uri_space.COOKIE_USER not in flask.session

    print("DONE: GET /login does not auto-login right after logout")


@pytest.mark.mytral
def test_login_get_does_not_auto_login_with_multiple_auto_login_users(monkeypatch):
    # GIVEN a desktop installation with more than one auto-login enabled user
    monkeypatch.setattr(
        auth_uri_space.app_config, "incarnation", config.MytralIncarnation.DESKTOP
    )
    monkeypatch.setattr(
        auth_uri_space.ds,
        "list_profile_names",
        lambda auto_login=False: {"athlete": "user-1", "coach": "user-2"},
    )
    monkeypatch.setattr(
        auth_uri_space.config.MytralPersistenceFsConfig,
        "is_migrate",
        lambda self: False,
    )
    captured = {}
    monkeypatch.setattr(flask, "render_template", _fake_render_template(captured))

    with auth_uri_space.flask_app.test_request_context("/login", method="GET"):
        # WHEN
        response = auth_uri_space.login()

        # THEN - user must pick which account to use, no silent login
        assert response == "ok"
        assert auth_uri_space.COOKIE_USER not in flask.session

    print("DONE: GET /login does not auto-login when multiple accounts allow it")


@pytest.mark.mytral
def test_logout_suppresses_auto_login_on_desktop(monkeypatch):
    # GIVEN a logged-in desktop user
    monkeypatch.setattr(
        auth_uri_space.app_config, "incarnation", config.MytralIncarnation.DESKTOP
    )
    monkeypatch.setattr(auth_uri_space.ds, "cache_evict", lambda user_id: None)

    with auth_uri_space.flask_app.test_request_context("/logout", method="GET"):
        flask.session[auth_uri_space.COOKIE_USER] = "user-1"

        # WHEN
        response = auth_uri_space.logout()

        # THEN - session is cleared and auto-login is suppressed going forward
        assert response.status_code == 302
        assert auth_uri_space.COOKIE_USER not in flask.session
        assert flask.session[auth_uri_space.COOKIE_AUTO_LOGIN_SUPPRESSED] is True

    print("DONE: logout suppresses desktop auto-login")


@pytest.mark.mytral
def test_logout_does_not_suppress_auto_login_on_webapp(monkeypatch):
    # GIVEN a logged-in webapp user (auto-login concept does not apply there)
    monkeypatch.setattr(
        auth_uri_space.app_config, "incarnation", config.MytralIncarnation.WEBAPP
    )
    monkeypatch.setattr(auth_uri_space.ds, "cache_evict", lambda user_id: None)

    with auth_uri_space.flask_app.test_request_context("/logout", method="GET"):
        flask.session[auth_uri_space.COOKIE_USER] = "user-1"

        # WHEN
        auth_uri_space.logout()

        # THEN
        assert auth_uri_space.COOKIE_AUTO_LOGIN_SUPPRESSED not in flask.session

    print("DONE: logout leaves webapp sessions untouched by desktop-only flag")
