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

"""Regression tests for the brutally-honest review fixes (BHR_ROUTES_JULY_5).

Each test maps to a finding id (H*/M*/L*) and locks in the corrected behavior.
"""

import pathlib
from types import SimpleNamespace

import flask
import pytest
import werkzeug.exceptions

from mytral import routes
from mytral.backends import entities as entities_mod

#
# H1 - clone/copy must not share the source's physical blobs
#


@pytest.mark.mytral
def test_reset_activity_blobs_clears_all_references():
    # GIVEN - an activity that references photos and recordings
    activity = entities_mod.ActivityEntity()
    activity.recorded_blob_keys = ["rec-1.gpx", "rec-2.fit"]
    activity.recorded_parquet_keys = {"rec-1": "parquet-1"}
    activity.photo_blob_keys = ["photo-1", "photo-2"]
    activity.highlight_photo_blob_key = "photo-1"

    # WHEN - the blob references are reset for a clone
    routes._reset_activity_blobs(activity)

    # THEN - every blob reference is emptied so the clone owns no shared blobs
    assert activity.recorded_blob_keys == []
    assert activity.recorded_parquet_keys == {}
    assert activity.photo_blob_keys == []
    assert activity.highlight_photo_blob_key == ""
    print("DONE: _reset_activity_blobs clears all blob references")


@pytest.mark.mytral
def test_copy_day_resets_blobs_on_copied_activity(monkeypatch):
    # GIVEN - a source activity with photos on the copied day
    source = entities_mod.ActivityEntity()
    source.key = "src-key"
    source.when_year, source.when_month, source.when_day = 2026, 7, 5
    source.photo_blob_keys = ["photo-1"]
    source.recorded_blob_keys = ["rec-1.gpx"]
    source.recorded_parquet_keys = {"rec-1": "parquet-1"}
    source.highlight_photo_blob_key = "photo-1"

    created = []
    monkeypatch.setitem(routes.flask_app.config, "WTF_CSRF_ENABLED", False)
    monkeypatch.setattr(
        routes.ds, "profile", lambda user_id: SimpleNamespace(dataset_name="default")
    )
    monkeypatch.setattr(
        routes.ds,
        "list_activities",
        lambda **kwargs: [source],
    )
    monkeypatch.setattr(routes.ds, "create_key", lambda: "new-key")
    monkeypatch.setattr(
        routes.ds,
        "create_activity",
        lambda user_id, dataset_name, entity: created.append(entity),
    )

    with routes.flask_app.test_request_context(
        "/activities/date/2026/7/5/copy",
        method="POST",
        data={
            "target_year": "2026",
            "target_month": "7",
            "target_day": "6",
        },
    ):
        flask.session[routes.COOKIE_USER] = "user-1"

        # WHEN - the day is copied to a new date
        routes.copy_day("2026", "7", "5")

    # THEN - the copied activity carries no blob references from the source
    assert len(created) == 1
    copied = created[0]
    assert copied.photo_blob_keys == []
    assert copied.recorded_blob_keys == []
    assert copied.recorded_parquet_keys == {}
    assert copied.highlight_photo_blob_key == ""
    print("DONE: copy_day resets blob references on the copied activity")


#
# M4 - unvalidated int() route params must yield 400, not 500
#


@pytest.mark.mytral
def test_int_or_400_parses_valid_values():
    # GIVEN/WHEN/THEN - valid numeric strings parse to int
    assert routes._int_or_400("2026") == 2026
    assert routes._int_or_400(7) == 7
    print("DONE: _int_or_400 parses valid values")


@pytest.mark.mytral
def test_int_or_400_aborts_on_invalid():
    # GIVEN - a non-numeric param
    # WHEN/THEN - it aborts with HTTP 400 (BadRequest) rather than crashing
    for bad in ("abc", "", None):
        with pytest.raises(werkzeug.exceptions.BadRequest):
            routes._int_or_400(bad)
    print("DONE: _int_or_400 aborts with 400 on invalid input")


@pytest.mark.mytral
def test_list_activities_for_date_bad_param_aborts_400(monkeypatch):
    # GIVEN - a logged-in user and a non-numeric date component
    monkeypatch.setattr(
        routes.ds, "profile", lambda user_id: SimpleNamespace(dataset_name="default")
    )

    with routes.flask_app.test_request_context("/activities/date/abc/1/1"):
        flask.session[routes.COOKIE_USER] = "user-1"

        # WHEN/THEN - the handler aborts 400 instead of raising ValueError (500)
        with pytest.raises(werkzeug.exceptions.BadRequest):
            routes.list_activities_for_date("abc", "1", "1")
    print("DONE: list_activities_for_date aborts 400 on non-numeric param")


#
# L1 - pace must sort numerically, not lexicographically
#


@pytest.mark.mytral
def test_pace_to_seconds_numeric_value():
    # GIVEN/WHEN/THEN - "M:SS" pace strings convert to total seconds
    assert routes._pace_to_seconds("9:45") == 585
    assert routes._pace_to_seconds("12:05") == 725
    # empty/invalid sorts last
    assert routes._pace_to_seconds("") == 10**9
    assert routes._pace_to_seconds(None) == 10**9
    print("DONE: _pace_to_seconds returns numeric seconds")


@pytest.mark.mytral
def test_pace_sort_orders_faster_before_slower():
    # GIVEN - paces that mislead a lexicographic sort ("10:00" < "9:45" as text)
    paces = ["12:05", "9:45", "10:00", "8:30"]

    # WHEN - sorted by the numeric pace key
    ordered = sorted(paces, key=routes._pace_to_seconds)

    # THEN - the fastest (smallest minutes:seconds) comes first
    assert ordered == ["8:30", "9:45", "10:00", "12:05"]
    print("DONE: pace sort orders faster paces before slower ones")


#
# L8 - referrer redirect must be same-host only (no open redirect)
#


@pytest.mark.mytral
def test_safe_redirect_target_allows_same_host():
    with routes.flask_app.test_request_context("http://localhost/x"):
        # WHEN - the target is on the same host
        result = routes._safe_redirect_target("http://localhost/notifications", "/home")
    # THEN - it is allowed
    assert result == "http://localhost/notifications"
    print("DONE: _safe_redirect_target allows same-host targets")


@pytest.mark.mytral
def test_safe_redirect_target_rejects_external_host():
    with routes.flask_app.test_request_context("http://localhost/x"):
        # WHEN - the target points at an external host
        result = routes._safe_redirect_target("http://evil.example/phish", "/home")
    # THEN - it falls back to the safe default
    assert result == "/home"
    print("DONE: _safe_redirect_target rejects external hosts")


@pytest.mark.mytral
def test_safe_redirect_target_empty_uses_fallback():
    with routes.flask_app.test_request_context("http://localhost/x"):
        assert routes._safe_redirect_target(None, "/home") == "/home"
        assert routes._safe_redirect_target("", "/home") == "/home"
    print("DONE: _safe_redirect_target uses fallback for empty target")


#
# M2 - settings_gear_merge_strava must be POST-only with CSRF (no GET mutation)
#


@pytest.mark.mytral
def test_settings_gear_merge_strava_requires_csrf(monkeypatch):
    # GIVEN - CSRF enabled and a POST with no token; gear load must never run
    called = {"list_strava_gear": False}
    monkeypatch.setitem(routes.flask_app.config, "WTF_CSRF_ENABLED", True)
    monkeypatch.setattr(
        routes.ds,
        "list_strava_gear",
        lambda user_id: called.__setitem__("list_strava_gear", True) or None,
    )

    with routes.flask_app.test_request_context(
        "/settings/gear/merge/strava", method="POST"
    ):
        flask.session[routes.COOKIE_USER] = "user-1"

        # WHEN/THEN - it is rejected before mutating anything
        with pytest.raises(werkzeug.exceptions.Forbidden):
            routes.settings_gear_merge_strava()
    assert called["list_strava_gear"] is False
    print("DONE: settings_gear_merge_strava rejects requests without CSRF")


#
# Codebase-wide - no typographic/math non-ASCII may reappear in sources
# (locks in the BHR ASCII cleanup; sport emoji and accented proper names
#  are the CLAUDE.md exceptions and are intentionally allowed)
#


@pytest.mark.mytral
def test_no_typographic_non_ascii_in_sources():
    # GIVEN - the characters the BHR cleanup removed everywhere
    forbidden = {
        "—": "em dash",
        "–": "en dash",
        "→": "arrow",
        "’": "smart quote",
        "─": "box drawing",
        "×": "multiplication sign",
        "≈": "almost equal",
        "°": "degree sign",
        "℃": "degree celsius",
        "±": "plus-minus",
    }

    # WHEN - scanning every Python source under mytral/
    offenders = []
    for path in pathlib.Path(routes.__file__).parent.rglob("*.py"):
        text = path.read_text(encoding="utf-8")
        for ch, name in forbidden.items():
            if ch in text:
                offenders.append(f"{path}: {name}")

    # THEN - none remain
    assert offenders == [], f"typographic non-ASCII reintroduced: {offenders}"
    print("DONE: no typographic/math non-ASCII in mytral sources")
