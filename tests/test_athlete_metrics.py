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
from unittest import mock

import pytest

from mytral import athlete_metrics as am
from mytral import settings as app_settings

#
# estimate_max_hr
#


@pytest.mark.mytral
def test_estimate_max_hr_tanaka():
    # GIVEN
    age = 40

    # WHEN
    result = am.estimate_max_hr(age)

    # THEN — Tanaka: 208 - 0.7 * 40 = 180
    assert result == 180
    print(f"DONE: estimate_max_hr(40) = {result}")


@pytest.mark.mytral
def test_estimate_max_hr_young():
    # GIVEN
    age = 20

    # WHEN
    result = am.estimate_max_hr(age)

    # THEN — 208 - 0.7 * 20 = 194
    assert result == 194
    print(f"DONE: estimate_max_hr(20) = {result}")


@pytest.mark.mytral
def test_estimate_max_hr_senior():
    # GIVEN
    age = 70

    # WHEN
    result = am.estimate_max_hr(age)

    # THEN — 208 - 0.7 * 70 = 159
    assert result == 159
    print(f"DONE: estimate_max_hr(70) = {result}")


#
# estimate_anaerobic_threshold_hr
#


@pytest.mark.mytral
def test_estimate_anaerobic_threshold_hr():
    # GIVEN
    e_max_hr = 180

    # WHEN
    result = am.estimate_anaerobic_threshold_hr(e_max_hr)

    # THEN — 180 * 0.85 = 153
    assert result == 153
    print(f"DONE: estimate_anaerobic_threshold_hr(180) = {result}")


#
# estimate_aerobic_threshold_hr
#


@pytest.mark.mytral
def test_estimate_aerobic_threshold_hr_maf_dominates():
    # GIVEN — young athlete where MAF (180 - age) > LTHR - 25
    age = 20
    lthr = 165  # LTHR - 25 = 140; MAF = 160 — MAF wins

    # WHEN
    result = am.estimate_aerobic_threshold_hr(lthr, age)

    # THEN
    maf = 180 - age  # 160
    lthr_offset = lthr - 25  # 140
    assert result == max(maf, lthr_offset)
    print(f"DONE: estimate_aerobic_threshold_hr({lthr}, {age}) = {result}")


@pytest.mark.mytral
def test_estimate_aerobic_threshold_hr_lthr_offset_dominates():
    # GIVEN — older athlete where LTHR - 25 > MAF
    age = 60
    lthr = 140  # LTHR - 25 = 115; MAF = 120 — LTHR offset wins

    # WHEN
    result = am.estimate_aerobic_threshold_hr(lthr, age)

    # THEN
    maf = 180 - age  # 120
    lthr_offset = lthr - 25  # 115
    assert result == max(maf, lthr_offset)
    print(f"DONE: estimate_aerobic_threshold_hr({lthr}, {age}) = {result}")


#
# _power_fraction_of_ftp
#


@pytest.mark.mytral
def test_power_fraction_at_anchors():
    # GIVEN / WHEN / THEN — anchor points must be exact
    assert am._power_fraction_of_ftp(20.0) == pytest.approx(1.053, abs=1e-3)
    assert am._power_fraction_of_ftp(60.0) == pytest.approx(1.000, abs=1e-3)
    assert am._power_fraction_of_ftp(10.0) == pytest.approx(1.150, abs=1e-3)
    print("DONE: _power_fraction_of_ftp anchor values correct")


@pytest.mark.mytral
def test_power_fraction_interpolated():
    # GIVEN — 40 min is between 20 min (1.053) and 60 min (1.000)
    # 40 min is 50% between 20 and 60 → interpolation midpoint
    f20 = am._power_fraction_of_ftp(20.0)
    f60 = am._power_fraction_of_ftp(60.0)
    f40 = am._power_fraction_of_ftp(40.0)

    # WHEN / THEN
    assert f60 < f40 < f20  # monotone decreasing
    print(f"DONE: power fraction at 40 min = {f40:.4f} (between {f20} and {f60})")


#
# estimate_ftp_from_activities
#


def _make_activity(
    avg_watts: float,
    hours: int,
    minutes: int,
    seconds: int = 0,
    max_watts: float = 0.0,
):
    """Create a minimal mock activity entity for FTP estimation tests."""
    activity = mock.MagicMock()
    activity.avg_watts = avg_watts
    activity.max_watts = max_watts
    activity.hours = hours
    activity.minutes = minutes
    activity.seconds = seconds
    return activity


@pytest.mark.mytral
def test_estimate_ftp_from_activities_single_qualifying():
    # GIVEN — 20-minute effort at 210 W average
    # fraction for 20 min = 1.053 → FTP = 210 / 1.053 ≈ 199
    activity = _make_activity(avg_watts=210.0, hours=0, minutes=20, seconds=0)

    # WHEN
    result = am.estimate_ftp_from_activities([activity])

    # THEN
    expected = round(210.0 / am._power_fraction_of_ftp(20.0))
    assert result == pytest.approx(expected, abs=1.0)
    print(f"DONE: estimate_ftp_from_activities single = {result:.1f} W")


@pytest.mark.mytral
def test_estimate_ftp_from_activities_picks_highest():
    # GIVEN — two activities; second should yield higher FTP candidate
    activity_a = _make_activity(avg_watts=200.0, hours=0, minutes=20, seconds=0)
    activity_b = _make_activity(avg_watts=180.0, hours=1, minutes=0, seconds=0)

    # WHEN
    result = am.estimate_ftp_from_activities([activity_a, activity_b])

    # THEN — FTP from a = 200/1.053 ≈ 190; from b = 180/1.0 = 180 → a wins
    candidate_a = 200.0 / am._power_fraction_of_ftp(20.0)
    candidate_b = 180.0 / am._power_fraction_of_ftp(60.0)
    assert result == pytest.approx(max(candidate_a, candidate_b), abs=1.0)
    print(f"DONE: estimate_ftp_from_activities picks max = {result:.1f} W")


@pytest.mark.mytral
def test_estimate_ftp_from_activities_excludes_short_effort():
    # GIVEN — effort shorter than MIN_ACTIVITY_DURATION_MIN (10 min)
    activity = _make_activity(avg_watts=300.0, hours=0, minutes=5, seconds=0)

    # WHEN
    result = am.estimate_ftp_from_activities([activity])

    # THEN — short effort excluded → 0.0
    assert result == 0.0
    print("DONE: estimate_ftp_from_activities excludes short effort")


@pytest.mark.mytral
def test_estimate_ftp_from_activities_excludes_no_power():
    # GIVEN — activity with no power data
    activity = _make_activity(avg_watts=0.0, hours=1, minutes=0, seconds=0)

    # WHEN
    result = am.estimate_ftp_from_activities([activity])

    # THEN
    assert result == 0.0
    print("DONE: estimate_ftp_from_activities excludes zero power")


@pytest.mark.mytral
def test_estimate_ftp_from_activities_empty_list():
    # GIVEN
    activities = []

    # WHEN
    result = am.estimate_ftp_from_activities(activities)

    # THEN
    assert result == 0.0
    print("DONE: estimate_ftp_from_activities handles empty list")


#
# estimate_vo2max
#


@pytest.mark.mytral
def test_estimate_vo2max():
    # GIVEN — typical values
    e_max_hr = 180
    rest_hr = 50

    # WHEN
    result = am.estimate_vo2max(e_max_hr, rest_hr)

    # THEN — Uth-Sorensen: 15.3 * (180 / 50) = 55.08
    expected = 15.3 * (180 / 50)
    assert result == pytest.approx(expected, rel=1e-3)
    print(f"DONE: estimate_vo2max({e_max_hr}, {rest_hr}) = {result:.2f} mL/kg/min")


@pytest.mark.mytral
def test_estimate_vo2max_default_rest_hr():
    # GIVEN — no explicit rest HR → should use REST_HR_DEFAULT
    e_max_hr = 180

    # WHEN
    result = am.estimate_vo2max(e_max_hr)

    # THEN
    expected = 15.3 * (180 / am.REST_HR_DEFAULT)
    assert result == pytest.approx(expected, rel=1e-3)
    print(f"DONE: estimate_vo2max uses default rest HR = {result:.2f}")


#
# estimate_hrv_rmssd
#


@pytest.mark.mytral
def test_estimate_hrv_rmssd():
    # GIVEN
    age = 40

    # WHEN
    result = am.estimate_hrv_rmssd(age)

    # THEN — 80 - 0.9 * 40 = 44.0
    assert result == pytest.approx(44.0, abs=0.01)
    print(f"DONE: estimate_hrv_rmssd(40) = {result:.1f} ms")


#
# estimate_fat_max
#


@pytest.mark.mytral
def test_estimate_fat_max():
    # GIVEN
    weight_kg = 70.0

    # WHEN
    result = am.estimate_fat_max(weight_kg)

    # THEN — 70 * 0.45 = 31.5
    assert result == pytest.approx(31.5, abs=0.01)
    print(f"DONE: estimate_fat_max(70) = {result:.1f} g/hr")


#
# calculate_zones
#


@pytest.mark.mytral
def test_calculate_zones_structure():
    # GIVEN
    lthr = 156
    max_hr = 183

    # WHEN
    zones = am.calculate_zones(lthr, max_hr)

    # THEN — must have 5 zones
    assert len(zones) == 5
    assert zones[0][0] == 0  # Z1 low always 0
    assert zones[4][1] == max_hr  # Z5 high = max_hr
    # zones should be non-overlapping and increasing
    for i in range(4):
        assert zones[i][1] <= zones[i + 1][0]
    print(f"DONE: calculate_zones returned 5 zones: {zones}")


#
# resolve
#


@pytest.mark.mytral
def test_resolve_all_estimated():
    # GIVEN — profile with no athlete-set metrics; age 40
    metrics = app_settings.AthleteMetrics()
    user_profile = mock.MagicMock()
    user_profile.age = 40

    # WHEN
    am.resolve(
        athlete_metrics=metrics,
        user_profile=user_profile,
        activities=[],
        weight_kg=75.0,
    )

    # THEN — all e_* fields must be populated
    assert metrics.e_max_hr == am.estimate_max_hr(40)
    assert metrics.e_anaerobic_threshold_hr == am.estimate_anaerobic_threshold_hr(
        metrics.e_max_hr
    )
    assert metrics.e_aerobic_threshold_hr > 0
    assert metrics.e_vo2max > 0
    assert metrics.e_hrv_rmssd > 0
    assert metrics.e_fat_max > 0  # weight 75 kg provided
    assert metrics.e_ftp == 0.0  # no activities with power
    assert metrics.e_critical_power == 0.0
    assert metrics.e_w_prime_joules > 0
    assert metrics.e_p_max_watts > 0
    # zones must be computed
    assert metrics.e_z1_high > 0
    assert metrics.e_z5_high == metrics.e_max_hr
    print("DONE: resolve populates all e_* fields when nothing is set")


@pytest.mark.mytral
def test_resolve_uses_set_values():
    # GIVEN — athlete set max_hr and LTHR
    metrics = app_settings.AthleteMetrics(max_hr=175, anaerobic_threshold_hr=150)
    user_profile = mock.MagicMock()
    user_profile.age = 40

    # WHEN
    am.resolve(
        athlete_metrics=metrics,
        user_profile=user_profile,
        activities=[],
        weight_kg=0.0,
    )

    # THEN — e_max_hr must equal the set value
    assert metrics.e_max_hr == 175
    assert metrics.e_anaerobic_threshold_hr == 150
    assert metrics.e_w_prime_joules > 0
    print("DONE: resolve uses athlete-set values")


@pytest.mark.mytral
def test_resolve_ftp_from_power_activity():
    # GIVEN — profile with no set FTP; 20-min activity at 210 W
    metrics = app_settings.AthleteMetrics()
    user_profile = mock.MagicMock()
    user_profile.age = 35

    activity = _make_activity(avg_watts=210.0, hours=0, minutes=20, seconds=0)

    # WHEN
    am.resolve(
        athlete_metrics=metrics,
        user_profile=user_profile,
        activities=[activity],
        weight_kg=70.0,
    )

    # THEN
    assert metrics.e_ftp > 0
    assert metrics.e_power_to_weight > 0
    assert metrics.e_critical_power == pytest.approx(metrics.e_ftp)
    assert metrics.e_p_max_watts > metrics.e_critical_power
    print(
        f"DONE: resolve estimated FTP = {metrics.e_ftp:.1f} W, "
        f"W/kg = {metrics.e_power_to_weight:.2f}"
    )
