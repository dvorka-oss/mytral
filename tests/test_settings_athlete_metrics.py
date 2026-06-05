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

from mytral import settings as app_settings

#
# AthleteMetrics serialization round-trip
#


@pytest.mark.mytral
def test_athlete_metrics_to_dict_persisted_defaults():
    # GIVEN — default (all-zero) metrics
    metrics = app_settings.AthleteMetrics()

    # WHEN
    data = metrics.to_dict_persisted()

    # THEN — all persisted fields present; all zero
    assert data["max_hr"] == 0
    assert data["anaerobic_threshold_hr"] == 0
    assert data["aerobic_threshold_hr"] == 0
    assert data["ftp"] == 0.0
    assert data["critical_power"] == 0.0
    assert data["w_prime_joules"] == 0.0
    assert data["p_max_watts"] == 0.0
    assert data["vo2max"] == 0.0
    assert data["hrv_rmssd"] == 0.0
    assert data["fat_max"] == 0.0
    assert data["z1_high"] == 0
    assert data["z2_high"] == 0
    assert data["z3_high"] == 0
    assert data["z4_high"] == 0
    # transient e_* fields must NOT appear in persisted dict
    for key in data:
        assert not key.startswith("e_"), f"Transient field {key} must not be persisted"
    print("DONE: to_dict_persisted() returns only persisted fields")


@pytest.mark.mytral
def test_athlete_metrics_round_trip():
    # GIVEN — metrics with non-zero values
    original = app_settings.AthleteMetrics(
        max_hr=183,
        anaerobic_threshold_hr=156,
        aerobic_threshold_hr=131,
        ftp=220.0,
        critical_power=215.0,
        w_prime_joules=19000.0,
        p_max_watts=980.0,
        vo2max=52.5,
        hrv_rmssd=42.0,
        fat_max=31.5,
        z1_high=117,
        z2_high=133,
        z3_high=148,
        z4_high=164,
    )

    # WHEN — serialize then deserialize
    data = original.to_dict_persisted()
    restored = app_settings.AthleteMetrics.from_dict(data)

    # THEN
    assert restored.max_hr == 183
    assert restored.anaerobic_threshold_hr == 156
    assert restored.aerobic_threshold_hr == 131
    assert restored.ftp == pytest.approx(220.0)
    assert restored.critical_power == pytest.approx(215.0)
    assert restored.w_prime_joules == pytest.approx(19000.0)
    assert restored.p_max_watts == pytest.approx(980.0)
    assert restored.vo2max == pytest.approx(52.5)
    assert restored.hrv_rmssd == pytest.approx(42.0)
    assert restored.fat_max == pytest.approx(31.5)
    assert restored.z1_high == 117
    assert restored.z2_high == 133
    assert restored.z3_high == 148
    assert restored.z4_high == 164
    # transient fields start at 0 after deserialization (resolve() fills them)
    assert restored.e_max_hr == 0
    assert restored.e_ftp == 0.0
    print("DONE: AthleteMetrics serialization round-trip OK")


@pytest.mark.mytral
def test_athlete_metrics_from_dict_backward_compat_empty():
    # GIVEN — empty dict (old profile JSON with no athlete_metrics key)
    data: dict = {}

    # WHEN
    metrics = app_settings.AthleteMetrics.from_dict(data)

    # THEN — all fields default to 0
    assert metrics.max_hr == 0
    assert metrics.ftp == 0.0
    assert metrics.vo2max == 0.0
    print("DONE: AthleteMetrics.from_dict({}) returns defaults — backward compat OK")


@pytest.mark.mytral
def test_athlete_metrics_from_dict_partial():
    # GIVEN — dict with only some fields (e.g. user set only max_hr)
    data = {"max_hr": 175, "ftp": 230.0}

    # WHEN
    metrics = app_settings.AthleteMetrics.from_dict(data)

    # THEN
    assert metrics.max_hr == 175
    assert metrics.ftp == pytest.approx(230.0)
    assert metrics.critical_power == 0.0
    assert metrics.w_prime_joules == 0.0
    assert metrics.p_max_watts == 0.0
    assert metrics.anaerobic_threshold_hr == 0  # not in dict → default
    assert metrics.z1_high == 0
    print("DONE: AthleteMetrics.from_dict with partial data OK")


#
# UserProfile integration
#


@pytest.mark.mytral
def test_user_profile_has_athlete_metrics_attribute():
    # GIVEN — create a minimal UserProfile
    profile = app_settings.UserProfile(
        user_id="test",
        user="test_user",
        email="test@test.com",
        password_enc="",
        dataset_name="test_dataset",
        dataset_names=["test_dataset"],
    )

    # WHEN / THEN
    assert hasattr(profile, "athlete_metrics")
    assert isinstance(profile.athlete_metrics, app_settings.AthleteMetrics)
    print("DONE: UserProfile.athlete_metrics exists and has correct type")


@pytest.mark.mytral
def test_user_profile_to_dict_includes_athlete_metrics():
    # GIVEN
    profile = app_settings.UserProfile(
        user_id="test",
        user="test_user",
        email="test@test.com",
        password_enc="",
        dataset_name="test_dataset",
        dataset_names=["test_dataset"],
    )
    profile.athlete_metrics.max_hr = 185

    # WHEN
    data = profile.to_dict()

    # THEN
    assert "athlete_metrics" in data
    assert data["athlete_metrics"]["max_hr"] == 185
    print("DONE: UserProfile.to_dict() includes athlete_metrics")


@pytest.mark.mytral
def test_user_profile_from_dict_with_athlete_metrics():
    # GIVEN — profile dict with athlete_metrics embedded
    profile_data = {
        "user": "test_user",
        "height": 180,
        "dataset_name": "test_dataset",
        "athlete_metrics": {
            "max_hr": 178,
            "ftp": 210.0,
        },
    }

    # WHEN
    profile = app_settings.UserProfile.from_dict(profile_data)

    # THEN
    assert profile.athlete_metrics.max_hr == 178
    assert profile.athlete_metrics.ftp == pytest.approx(210.0)
    print("DONE: UserProfile.from_dict() loads athlete_metrics correctly")


@pytest.mark.mytral
def test_user_profile_from_dict_backward_compat_no_athlete_metrics():
    # GIVEN — old profile dict without athlete_metrics key
    profile_data = {
        "user": "old_user",
        "height": 175,
        "dataset_name": "old_dataset",
    }

    # WHEN
    profile = app_settings.UserProfile.from_dict(profile_data)

    # THEN — profile loads fine; athlete_metrics defaults to all-zero
    assert isinstance(profile.athlete_metrics, app_settings.AthleteMetrics)
    assert profile.athlete_metrics.max_hr == 0
    assert profile.athlete_metrics.ftp == 0.0
    print("DONE: UserProfile.from_dict() backward compat without athlete_metrics")


@pytest.mark.mytral
def test_user_profile_gender_defaults_to_man():
    # GIVEN — minimal profile without explicit gender
    profile = app_settings.UserProfile(
        user_id="test",
        user="test_user",
        email="test@test.com",
        password_enc="",
        dataset_name="test_dataset",
        dataset_names=["test_dataset"],
    )

    # WHEN / THEN
    assert profile.gender is None
    assert ("Woman" if profile.gender is False else "Man") == "Man"
    print("DONE: UserProfile undefined gender falls back to man")


@pytest.mark.mytral
def test_user_profile_from_dict_gender_backward_compat_defaults_to_man():
    # GIVEN — persisted profile without gender key
    profile_data = {
        "user": "old_user",
        "height": 175,
        "dataset_name": "old_dataset",
    }

    # WHEN
    profile = app_settings.UserProfile.from_dict(profile_data)

    # THEN
    assert profile.gender is None
    assert ("Woman" if profile.gender is False else "Man") == "Man"
    print("DONE: UserProfile.from_dict() keeps optional gender and falls back to man")


@pytest.mark.mytral
def test_user_profile_to_dict_includes_gender():
    # GIVEN
    profile = app_settings.UserProfile(
        user_id="test",
        user="test_user",
        email="test@test.com",
        password_enc="",
        dataset_name="test_dataset",
        dataset_names=["test_dataset"],
        gender=False,
    )

    # WHEN
    data = profile.to_dict()

    # THEN
    assert data[app_settings.UserProfile.KEY_GENDER] is False
    print("DONE: UserProfile.to_dict() includes gender")
