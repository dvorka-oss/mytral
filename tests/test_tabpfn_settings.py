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
import pytest

from mytral.ml.icl import settings as icl_settings


@pytest.mark.mytral
def test_icl_settings_empty():
    """Test IclSettings.empty() returns disabled defaults."""
    # GIVEN / WHEN
    s = icl_settings.IclSettings.empty()

    # THEN
    assert s.enabled is False
    assert s.enable_illness_risk is True
    print("DONE: IclSettings.empty() returns disabled defaults")


@pytest.mark.mytral
def test_icl_settings_roundtrip():
    """Test IclSettings serialization roundtrip via to_dict / from_dict."""
    # GIVEN
    original = icl_settings.IclSettings(
        enabled=True,
        enable_illness_risk=False,
    )

    # WHEN
    d = original.to_dict()
    restored = icl_settings.IclSettings.from_dict(d)

    # THEN
    assert restored.enabled == original.enabled
    assert restored.enable_illness_risk == original.enable_illness_risk
    print("DONE: IclSettings roundtrip serialization")


@pytest.mark.mytral
def test_icl_settings_from_empty_dict_returns_defaults():
    """Test IclSettings.from_dict({}) returns default (empty) settings."""
    # GIVEN
    empty_dict: dict = {}

    # WHEN
    s = icl_settings.IclSettings.from_dict(empty_dict)

    # THEN
    assert s.enabled is False
    assert s.enable_illness_risk is True
    print("DONE: IclSettings.from_dict({}) returns defaults")


@pytest.mark.mytral
def test_icl_settings_to_dict_contains_required_keys():
    """Test IclSettings.to_dict() contains all expected keys."""
    # GIVEN
    s = icl_settings.IclSettings(enabled=True, enable_illness_risk=True)

    # WHEN
    d = s.to_dict()

    # THEN
    assert "enabled" in d
    assert "enable_illness_risk" in d
    assert d["enabled"] is True
    assert d["enable_illness_risk"] is True
    print("DONE: IclSettings.to_dict() keys and values correct")


@pytest.mark.mytral
def test_icl_settings_partial_dict_uses_defaults():
    """Test from_dict with missing keys falls back to defaults."""
    # GIVEN
    partial: dict = {"enabled": True}  # enable_illness_risk missing

    # WHEN
    s = icl_settings.IclSettings.from_dict(partial)

    # THEN
    assert s.enabled is True
    assert s.enable_illness_risk is True  # default
    print("DONE: IclSettings partial dict uses defaults for missing keys")


@pytest.mark.mytral
def test_model_status_constants_are_distinct():
    """Test that all MODEL_STATUS_* constants are non-empty and unique."""
    # GIVEN
    constants = [
        icl_settings.MODEL_STATUS_NOT_INSTALLED,
        icl_settings.MODEL_STATUS_NOT_DOWNLOADED,
        icl_settings.MODEL_STATUS_DOWNLOADING,
        icl_settings.MODEL_STATUS_DOWNLOADED,
        icl_settings.MODEL_STATUS_FAILED,
    ]

    # WHEN / THEN
    assert len(set(constants)) == len(constants), "all status constants must be unique"
    assert all(isinstance(c, str) and c for c in constants)
    print("DONE: MODEL_STATUS_* constants are distinct non-empty strings")
