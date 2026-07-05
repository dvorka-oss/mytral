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

import pathlib

import pytest

from mytral import app_blobstore
from mytral import app_config
from mytral import config
from mytral import plugins
from mytral import security
from mytral.integrations import polar_flow
from mytral.tasks.do import polar_flow_commons
from tests import _given


def _noop(*_args, **_kwargs):
    """No-op callback for progress/log/cancellation hooks."""
    return None


class _FakeResponse:
    """Minimal stand-in for a requests.Response."""

    def __init__(self, status_code, json_body=None, headers=None, content=b""):
        self.status_code = status_code
        self._json = json_body
        self.headers = headers or {}
        self.content = content

    def json(self):
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
