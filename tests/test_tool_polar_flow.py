# MyTraL: my trailing log
#
# Copyright (C) 2015-2026 Martin Dvorak <martin.dvorak@mindforger.com>
#
# This program is free software: you can redistribute it and/or modify
# it under the terms of the GNU Affero General Public License as published by
# the Free Software Foundation, either version 3 of the License, or
# (at your option) any later version.
# This program is distributed in the hope that it will be useful,
# but WITHOUT ANY WARRANTY; without even the implied warranty of
# MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the
# GNU Affero General Public License for more details.
#
# You should have received a copy of the GNU Affero General Public License
# along with this program. If not, see <http://www.gnu.org/licenses/>.

"""Tests for Polar Flow client, credentials, dedup and rate-limit handling."""

import contextlib
import io
import json
import pathlib
import urllib.parse

import pytest
import structlog

from mytral import app_blobstore
from mytral import app_config
from mytral import config
from mytral import loggers
from mytral import plugins
from mytral import security
from mytral import settings
from mytral.blueprints import polar_flow_uri_space
from mytral.integrations import polar_flow
from mytral.routes import flask_app
from mytral.tasks.do import polar_flow_commons
from tests import _given


def _noop(*_args, **_kwargs):
    """No-op callback for progress/log/cancellation hooks."""
    return None


class _FakeResponse:
    """Minimal stand-in for a requests.Response."""

    def __init__(
        self,
        status_code,
        json_body=None,
        headers=None,
        content=b"",
        text="",
        json_raises=False,
    ):
        self.status_code = status_code
        self._json = json_body
        self._json_raises = json_raises
        self.headers = headers or {}
        self.content = content
        self.text = text

    def json(self):
        if self._json_raises:
            # mimic requests raising on a body that is not JSON at all
            raise ValueError("no JSON body")
        return self._json


def _api_summary(src_id, start_time, sport, duration, distance):
    """Build a Polar AccessLink exercise summary dict for tests."""
    return {
        "id": src_id,
        "start-time": start_time,
        "duration": duration,
        "distance": distance,
        "calories": 500,
        "heart-rate": {"average": 140, "maximum": 170},
        "sport": sport,
        "detailed-sport-info": sport,
    }


@pytest.mark.mytral
def test_credentials_roundtrip_encrypted():
    """Encrypted task credentials decrypt back to their original values."""
    #
    # GIVEN
    #
    enc_key = app_config.encryption_key
    params = {
        "access_token": security.encrypt("secret-access-token", enc_key),
        "polar_user_id": "999",
    }
    # ciphertext must not leak the plaintext
    assert "secret-access-token" not in params["access_token"]

    #
    # WHEN
    #
    creds = polar_flow_commons.build_polar_credentials(params, enc_key)

    #
    # THEN
    #
    assert creds.access_token == "secret-access-token"
    assert creds.polar_user_id == "999"
    print("DONE: credentials encrypt at rest and decrypt via the encryption key")


@pytest.mark.mytral
def test_rate_limit_backoff(monkeypatch):
    """A 429 with Retry-After triggers a bounded retry that then succeeds."""
    #
    # GIVEN
    #
    calls = {"n": 0}
    slept = {"n": 0}

    def fake_request(method, url, headers=None, json=None):
        calls["n"] += 1
        if calls["n"] == 1:
            return _FakeResponse(429, headers={"Retry-After": "0"})
        return _FakeResponse(200, json_body={"ok": True})

    monkeypatch.setattr(polar_flow.requests, "request", fake_request)
    monkeypatch.setattr(
        polar_flow.time, "sleep", lambda _s: slept.__setitem__("n", slept["n"] + 1)
    )

    #
    # WHEN
    #
    response = polar_flow._request(
        "GET", "https://x/y", access_token="token", logger=polar_flow.app_logger
    )

    #
    # THEN
    #
    assert calls["n"] == 2
    assert slept["n"] == 1
    assert response.status_code == 200
    print("DONE: 429 Retry-After triggers a bounded retry that then succeeds")


@pytest.mark.mytral
def test_transaction_commit_flow(monkeypatch):
    """The transaction model lists exercises once and returns nothing after commit."""
    #
    # GIVEN
    #
    state = {"committed": False}

    def fake_request(method, url, headers=None, json=None):
        if method == "POST" and url.endswith("/exercise-transactions"):
            # after commit there is nothing new -> 204
            if state["committed"]:
                return _FakeResponse(204)
            return _FakeResponse(201, json_body={"transaction-id": 42})
        if method == "GET" and url.endswith("/exercise-transactions/42"):
            return _FakeResponse(
                200, json_body={"exercises": ["https://x/ex/1", "https://x/ex/2"]}
            )
        if method == "PUT" and url.endswith("/exercise-transactions/42"):
            state["committed"] = True
            return _FakeResponse(200)
        return _FakeResponse(404)

    monkeypatch.setattr(polar_flow.requests, "request", fake_request)
    logger = polar_flow.app_logger

    #
    # WHEN
    #
    tid = polar_flow.create_transaction(
        access_token="tok", polar_user_id="7", logger=logger
    )
    exercises = polar_flow.list_transaction_exercises(
        access_token="tok", polar_user_id="7", transaction_id=tid, logger=logger
    )
    committed = polar_flow.commit_transaction(
        access_token="tok", polar_user_id="7", transaction_id=tid, logger=logger
    )
    # a second cycle after commit finds nothing new
    tid_after = polar_flow.create_transaction(
        access_token="tok", polar_user_id="7", logger=logger
    )

    #
    # THEN
    #
    assert tid == "42"
    assert exercises == ["https://x/ex/1", "https://x/ex/2"]
    assert committed is True
    assert tid_after is None
    print("DONE: transaction create/list/commit prevents re-delivery (no duplicates)")


@pytest.mark.mytral
def test_failed_summary_fetch_skips_commit(tmp_path: pathlib.Path, monkeypatch):
    """A failed summary fetch leaves the transaction uncommitted (no data loss)."""
    #
    # GIVEN
    #
    test_config = config.MytralConfig(persistence_data_dir=tmp_path)
    _ds, user_ds, user_profile = _given.given_test(
        test_config, user_id="test_polar_flow_commit_user"
    )
    monkeypatch.setattr(polar_flow, "app_user_ds", user_ds)

    commit_spy = {"called": False}
    monkeypatch.setattr(polar_flow, "create_transaction", lambda **_k: "42")
    monkeypatch.setattr(
        polar_flow, "list_transaction_exercises", lambda **_k: ["u1", "u2"]
    )

    def fake_summary(access_token, exercise_url, logger):
        # first exercise fetches fine, second one fails (returns None)
        if exercise_url == "u1":
            return _api_summary(
                111, "2023-05-20T08:30:00", "RUNNING", "PT0H30M0S", 5000
            )
        return None

    monkeypatch.setattr(polar_flow, "fetch_exercise_summary", fake_summary)
    monkeypatch.setattr(
        polar_flow,
        "commit_transaction",
        lambda **_k: commit_spy.__setitem__("called", True),
    )

    creds = type("_Creds", (), {})()
    creds.access_token = "tok"
    creds.polar_user_id = "7"

    #
    # WHEN
    #
    imported, skipped, recordings = polar_flow_commons.pull_new_exercises(
        creds,
        dataset=user_ds,
        blobstore=app_blobstore,
        config=test_config,
        user_id=user_profile.user_id,
        dataset_name=user_profile.dataset_name,
        import_recordings=False,
        log_fn=_noop,
        logger=polar_flow.app_logger,
        check_cancellation=_noop,
        update_progress=_noop,
    )

    #
    # THEN
    #
    assert imported == 1  # the successfully-fetched exercise was imported
    assert commit_spy["called"] is False  # failed fetch -> transaction NOT committed
    print("DONE: a failed summary fetch leaves the transaction uncommitted for retry")


@pytest.mark.mytral
def test_cross_channel_dedup(tmp_path: pathlib.Path, monkeypatch):
    """A GDPR session and an API exercise for the same workout do not duplicate."""
    #
    # GIVEN
    #
    _ds, user_ds, user_profile = _given.given_test(
        config.MytralConfig(persistence_data_dir=tmp_path),
        user_id="test_polar_flow_dedup_user",
    )
    monkeypatch.setattr(polar_flow, "app_user_ds", user_ds)
    plugin = plugins.registry.get_plugin(polar_flow.PolarFlowActivityImportPlugin.NAME)
    dataset_name = user_profile.dataset_name

    # API exercise: trail run at 08:30:00, id=111
    api_activity = plugin.import_activity(
        dataset_item=_api_summary(
            111, "2023-05-20T08:30:00", "TRAIL_RUNNING", "PT1H0M0S", 10000
        ),
        user_profile=user_profile,
    )
    user_ds.create_activity(
        user_id=user_profile.user_id, dataset_name=dataset_name, entity=api_activity
    )

    # GDPR session: SAME workout, different id, 60s later start, 20s longer
    gdpr_dup = plugin.import_activity(
        dataset_item=_api_summary(
            222, "2023-05-20T08:31:00", "TRAIL_RUNNING", "PT1H0M20S", 10010
        ),
        user_profile=user_profile,
    )
    # a genuinely different workout later the same day
    other = plugin.import_activity(
        dataset_item=_api_summary(
            333, "2023-05-20T18:00:00", "RUNNING", "PT0H30M0S", 5000
        ),
        user_profile=user_profile,
    )

    #
    # WHEN
    #
    dup_match = polar_flow_commons.find_existing_polar_flow_activity(
        dataset=user_ds,
        user_id=user_profile.user_id,
        dataset_name=dataset_name,
        candidate=gdpr_dup,
    )
    other_match = polar_flow_commons.find_existing_polar_flow_activity(
        dataset=user_ds,
        user_id=user_profile.user_id,
        dataset_name=dataset_name,
        candidate=other,
    )

    #
    # THEN
    #
    assert dup_match == api_activity.key
    assert other_match is None
    print("DONE: cross-channel natural-key dedup catches the duplicate, not the rest")


def _given_polar_profile() -> settings.UserProfile:
    """Build a user profile with Polar Flow client credentials configured."""
    return settings.UserProfile(
        user_id="u1",
        user="user",
        email="user@example.com",
        password_enc="x",
        dataset_name="main",
        dataset_names=["main"],
        polar_flow_client_id="client-id",
        polar_flow_client_secret="client-secret",
    )


class _FakeProfileDs:
    """Dataset stub recording the profile handed to update_profile()."""

    def __init__(self):
        self.updated = None

    def update_profile(self, user_profile):
        self.updated = user_profile
        return user_profile


@pytest.mark.mytral
def test_auth_token_exchange_redirect_uri_matches_authorization(monkeypatch):
    """The token exchange echoes the very redirect_uri sent to authorization.

    Polar rejects the exchange unless redirect_uri is repeated there with the
    identical value: "Must be specified if redirect_uri was passed to
    authorization endpoint".
    """
    #
    # GIVEN
    #
    user_profile = _given_polar_profile()
    sent = {}

    def fake_post(url, auth=None, headers=None, data=None):
        sent["url"] = url
        sent["auth"] = auth
        sent["data"] = data
        return _FakeResponse(200, json_body={"access_token": "tok", "x_user_id": 42})

    monkeypatch.setattr(polar_flow.requests, "post", fake_post)

    #
    # WHEN
    #
    # the authorization step - as served by GET /polar/auth-start
    with flask_app.test_request_context("http://127.0.0.1:5000/polar/auth-start"):
        auth_url = polar_flow.auth_get_auth_code_url(
            user_profile=user_profile,
            mytral_url=polar_flow_uri_space._auth_callback_url(),
        )
    # the token exchange - as served by GET /polar/auth-callback
    with flask_app.test_request_context(
        "http://127.0.0.1:5000/polar/auth-callback?code=auth-code"
    ):
        polar_flow.auth_exchange_code_for_token(
            user_profile=user_profile,
            code="auth-code",
            mytral_url=polar_flow_uri_space._auth_callback_url(),
            ds=_FakeProfileDs(),
            logger=polar_flow.app_logger,
        )

    #
    # THEN
    #
    query = urllib.parse.parse_qs(urllib.parse.urlparse(auth_url).query)
    authorization_redirect_uri = query["redirect_uri"][0]

    assert "redirect_uri" in sent["data"], "redirect_uri missing in the token exchange"
    assert sent["data"]["redirect_uri"] == authorization_redirect_uri
    assert authorization_redirect_uri == "http://127.0.0.1:5000/polar/auth-callback"
    # the rest of the documented Polar token contract
    assert sent["url"] == polar_flow.URL_OAUTH_TOKEN
    assert sent["auth"] == ("client-id", "client-secret")
    assert sent["data"]["grant_type"] == "authorization_code"
    assert sent["data"]["code"] == "auth-code"
    print("DONE: token exchange echoes the authorization redirect_uri")


@pytest.mark.mytral
def test_auth_token_exchange_persists_token_and_user_id(monkeypatch):
    """A successful exchange returns and persists the token and Polar user id."""
    #
    # GIVEN
    #
    user_profile = _given_polar_profile()
    ds = _FakeProfileDs()
    monkeypatch.setattr(
        polar_flow.requests,
        "post",
        lambda **_kw: _FakeResponse(
            200, json_body={"access_token": "polar-token", "x_user_id": 42}
        ),
    )

    #
    # WHEN
    #
    token = polar_flow.auth_exchange_code_for_token(
        user_profile=user_profile,
        code="auth-code",
        mytral_url="http://127.0.0.1:5000/polar/auth-callback",
        ds=ds,
        logger=polar_flow.app_logger,
    )

    #
    # THEN
    #
    assert token == "polar-token"
    assert user_profile.polar_flow_access_token == "polar-token"
    assert user_profile.polar_flow_user_id == "42"
    assert ds.updated is user_profile
    print("DONE: successful exchange persists the token and the Polar user id")


@pytest.mark.mytral
def test_auth_token_exchange_failure_logs_status_and_body(monkeypatch):
    """A rejected exchange logs Polar's status and error body, then raises."""
    #
    # GIVEN
    #
    user_profile = _given_polar_profile()
    body = '{"error":"invalid_grant","error_description":"redirect_uri mismatch"}'
    monkeypatch.setattr(
        polar_flow.requests,
        "post",
        lambda **_kw: _FakeResponse(
            400, json_body={"error": "invalid_grant"}, text=body
        ),
    )
    logged = {}

    class _Logger:
        def error(self, msg, **kwargs):
            logged["msg"] = msg
            logged.update(kwargs)

        def debug(self, msg, **kwargs):
            return None

    #
    # WHEN
    #
    with pytest.raises(ValueError, match="Failed to get Polar Flow access token"):
        polar_flow.auth_exchange_code_for_token(
            user_profile=user_profile,
            code="auth-code",
            mytral_url="http://127.0.0.1:5000/polar/auth-callback",
            ds=_FakeProfileDs(),
            logger=_Logger(),
        )

    #
    # THEN
    #
    assert logged["status"] == 400
    assert "invalid_grant" in logged["response"]
    assert "redirect_uri mismatch" in logged["response"]
    # a failed exchange must not persist anything
    assert not user_profile.polar_flow_access_token
    print("DONE: failed exchange logs the Polar status and error body")


@pytest.mark.mytral
def test_auth_token_exchange_non_json_body_raises(monkeypatch):
    """A non-JSON error body surfaces as the domain error, not a parse error."""
    #
    # GIVEN
    #
    user_profile = _given_polar_profile()
    monkeypatch.setattr(
        polar_flow.requests,
        "post",
        lambda **_kw: _FakeResponse(
            502, json_raises=True, text="<html>Bad Gateway</html>"
        ),
    )

    #
    # WHEN / THEN
    #
    with pytest.raises(ValueError, match="Failed to get Polar Flow access token"):
        polar_flow.auth_exchange_code_for_token(
            user_profile=user_profile,
            code="auth-code",
            mytral_url="http://127.0.0.1:5000/polar/auth-callback",
            ds=_FakeProfileDs(),
            logger=polar_flow.app_logger,
        )
    print("DONE: non-JSON token response raises the domain error")


def _exchange_and_log_like_the_route(user_profile, logger) -> None:
    """Mimic /polar/auth-callback: the exchange raises, the route logs it.

    The secret must live only on ``user_profile`` - never in a local - exactly as
    in the real route, because the log renders the locals of every frame.
    """
    try:
        polar_flow.auth_exchange_code_for_token(
            user_profile=user_profile,
            code="auth-code",
            mytral_url="http://127.0.0.1:5000/polar/auth-callback",
            ds=_FakeProfileDs(),
            logger=logger,
        )
    except ValueError as exc:
        logger.exception(
            "Polar Flow authentication failed",
            exc_info=True,
            error=str(exc),
            user_id=user_profile.user_id,
        )


@pytest.mark.mytral
def test_auth_failure_logs_stacktrace_without_leaking_secrets(monkeypatch):
    """The auth failure log carries a stacktrace but no plain-text secrets.

    Regression guard: ``MytralLogger.exception()`` requires ``exc_info``, and the
    structlog chain renders frame locals - so a secret held in a local variable
    of any frame in the stack would end up in the log.
    """
    #
    # GIVEN
    #
    secret = "SUPER-SECRET-CLIENT-SECRET-42"
    token = "SUPER-SECRET-ACCESS-TOKEN-99"
    user_profile = _given_polar_profile()
    user_profile.polar_flow_client_secret = secret
    user_profile.polar_flow_access_token = token
    monkeypatch.setattr(
        polar_flow.requests,
        "post",
        lambda **_kw: _FakeResponse(
            400, json_body={"error": "invalid_grant"}, text='{"error":"invalid_grant"}'
        ),
    )

    saved_config = structlog.get_config()
    buffer = io.StringIO()
    try:
        with contextlib.redirect_stdout(buffer):
            loggers.configure_structlog(debug=False)
            #
            # WHEN
            #
            _exchange_and_log_like_the_route(
                user_profile, loggers.MytralStructLogger("test-polar-flow")
            )
    finally:
        structlog.configure(**saved_config)

    #
    # THEN
    #
    events = [json.loads(line) for line in buffer.getvalue().strip().splitlines()]
    event = events[-1]
    assert event["event"] == "Polar Flow authentication failed"
    assert event["level"] == "error"
    assert event["user_id"] == user_profile.user_id
    # the stacktrace is rendered as structured frames
    assert event["exception"], "no stacktrace rendered - exc_info was not honoured"
    assert event["exception"][0]["exc_type"] == "ValueError"
    assert event["exception"][0]["frames"]
    # no plain-text secret anywhere in the log - frame locals included
    raw = buffer.getvalue()
    assert secret not in raw, "client secret leaked into the log"
    assert token not in raw, "access token leaked into the log"
    print("DONE: auth failure logs a stacktrace and leaks no secrets")


class _CapturingLogger:
    """Logger stub recording (level, msg, kwargs) for observability assertions."""

    def __init__(self):
        self.records = []

    def _record(self, level, msg, **kwargs):
        self.records.append((level, msg, kwargs))

    def debug(self, msg, *args, **kwargs):
        self._record("debug", msg, **kwargs)

    def info(self, msg, *args, **kwargs):
        self._record("info", msg, **kwargs)

    def warning(self, msg, *args, **kwargs):
        self._record("warning", msg, **kwargs)

    def error(self, msg, *args, **kwargs):
        self._record("error", msg, **kwargs)


@pytest.mark.mytral
def test_no_new_exercises_logs_delivery_rule_hint(monkeypatch):
    """A 204 (no new exercises) explains the post-registration delivery rule.

    This is the exact scenario a user hits after connecting a fresh client: Polar
    returns 204 because their existing activities predate registration.
    """
    #
    # GIVEN
    #
    logger = _CapturingLogger()
    monkeypatch.setattr(
        polar_flow.requests, "request", lambda **_kw: _FakeResponse(204)
    )

    #
    # WHEN
    #
    transaction_id = polar_flow.create_transaction(
        access_token="tok", polar_user_id="42", logger=logger
    )

    #
    # THEN
    #
    assert transaction_id is None
    hint_records = [r for r in logger.records if "no new exercises" in r[1]]
    assert hint_records, "the 204 path did not log the no-new-exercises event"
    _, _, kwargs = hint_records[0]
    assert "hint" in kwargs, "the 204 log is missing the delivery-rule hint"
    assert "after" in kwargs["hint"].lower()
    assert "gdpr" in kwargs["hint"].lower() or "export" in kwargs["hint"].lower()
    print("DONE: 204 no-new-exercises logs the post-registration delivery hint")


@pytest.mark.mytral
def test_request_traces_method_url_status_without_token(monkeypatch):
    """Every AccessLink call is traced at debug with status - never the token."""
    #
    # GIVEN
    #
    token = "SECRET-TOKEN-DO-NOT-LOG"
    logger = _CapturingLogger()
    monkeypatch.setattr(
        polar_flow.requests, "request", lambda **_kw: _FakeResponse(200)
    )

    #
    # WHEN
    #
    polar_flow._request(
        "POST",
        "https://www.polaraccesslink.com/v3/users/42/exercise-transactions",
        access_token=token,
        logger=logger,
    )

    #
    # THEN
    #
    traces = [r for r in logger.records if r[1] == "Polar AccessLink request"]
    assert traces, "no HTTP trace was emitted"
    level, _, kwargs = traces[0]
    assert level == "debug"
    assert kwargs["method"] == "POST"
    assert kwargs["status"] == 200
    assert "exercise-transactions" in kwargs["url"]
    # the token must never appear in any traced field
    assert token not in str(kwargs), "access token leaked into the HTTP trace"
    print("DONE: AccessLink requests are traced (method/url/status) without the token")


@pytest.mark.mytral
def test_register_user_logs_registration_boundary(monkeypatch):
    """Successful registration logs the delivery boundary and the polar user id."""
    #
    # GIVEN
    #
    logger = _CapturingLogger()
    user_profile = _given_polar_profile()
    user_profile.polar_flow_access_token = "tok"
    monkeypatch.setattr(
        polar_flow.requests,
        "request",
        lambda **_kw: _FakeResponse(201, json_body={"polar-user-id": 777}),
    )

    #
    # WHEN
    #
    polar_user_id = polar_flow.register_user(
        user_profile=user_profile, ds=_FakeProfileDs(), logger=logger
    )

    #
    # THEN
    #
    assert polar_user_id == "777"
    reg_records = [r for r in logger.records if r[0] == "info" and "registered" in r[1]]
    assert reg_records, "registration did not log an info event"
    msg, kwargs = reg_records[0][1], reg_records[0][2]
    # the boundary is spelled out and the polar user id is captured
    assert "after this moment" in msg
    assert kwargs["polar_user_id"] == "777"
    print("DONE: registration logs the delivery boundary and polar user id")
