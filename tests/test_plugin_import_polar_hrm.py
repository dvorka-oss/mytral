# MyTraL: my trailing log
#
# Copyright (C) 2015-2026 Martin Dvorak <martin.dvorak@mindforger.com>
#
# This program is free software: you can redistribute it and/or modify
# it under the terms of the GNU General Public License as published by
# the Free Software Foundation, either version 3 of the License, or
# (at your option) any later version.
# This program is distributed in the hope that it will be useful,
# but WITHOUT ANY WARRANTY; without even the implied warranty of
# MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the
# GNU Affero General Public License for more details.
#
# You should have received a copy of the GNU Affero General Public License
# along with this program. If not, see <http://www.gnu.org/licenses/>.

"""Tests for Polar Precision Performance HRM/PDD plugin."""

import datetime
import io
import pathlib

import fitparse
import pytest

from mytral import commons
from mytral import config
from mytral import plugins
from mytral.integrations import polar_hrm
from tests import _given

# path to the real Polar test dataset — skip integration tests if absent
_POLAR_DATA_DIR = (
    pathlib.Path(__file__).parent
    / "data"
    / "import"
    / "polar"
    / "Polar Precision Performance"
    / "Marco"
)

_POLAR_HAS_DATA = _POLAR_DATA_DIR.is_dir()

# a specific .hrm file that we validated manually
_HRM_2003 = _POLAR_DATA_DIR / "2003" / "03092801.hrm"
_PDD_2003 = _POLAR_DATA_DIR / "2003" / "20030928.pdd"

# alias for brevity
PolarPlugin = polar_hrm.PolarHrmImportPlugin


#
# parse_smode
#


@pytest.mark.mytral
def test_parse_smode_all_zeros():
    """parse_smode("000000") should return all False."""
    #
    # GIVEN
    #
    smode = "000000"

    #
    # WHEN
    #
    has_speed, has_cadence, has_altitude, has_power, has_balance = (
        polar_hrm.parse_smode(smode)
    )

    #
    # THEN
    #
    assert not has_speed
    assert not has_cadence
    assert not has_altitude
    assert not has_power
    assert not has_balance
    print("DONE: parse_smode all-zeros returns all False")


@pytest.mark.mytral
def test_parse_smode_speed_only():
    """parse_smode("10000000") should return has_speed=True,
    rest False (bit0 = leftmost).
    """
    #
    # GIVEN
    #
    smode = "10000000"  # bit 0 (leftmost) = speed present

    #
    # WHEN
    #
    has_speed, has_cadence, has_altitude, has_power, has_balance = (
        polar_hrm.parse_smode(smode)
    )

    #
    # THEN
    #
    assert has_speed
    assert not has_cadence
    assert not has_altitude
    print("DONE: parse_smode speed-only returns has_speed=True")


@pytest.mark.mytral
def test_parse_smode_all_channels():
    """parse_smode with all relevant bits set should return all True."""
    #
    # GIVEN
    #
    smode = "11111111"

    #
    # WHEN
    #
    has_speed, has_cadence, has_altitude, has_power, has_balance = (
        polar_hrm.parse_smode(smode)
    )

    #
    # THEN
    #
    assert has_speed
    assert has_cadence
    assert has_altitude
    assert has_power
    assert has_balance
    print("DONE: parse_smode all-channels returns all True")


#
# map_activity_type_index
#


@pytest.mark.mytral
def test_map_activity_type_index_known_codes():
    """activity type index should return recognised MyTraL activity_type_key strings."""
    #
    # GIVEN / WHEN / THEN
    #
    assert polar_hrm.map_activity_type_index(1) == commons.AT_RUN
    assert polar_hrm.map_activity_type_index(2) == commons.AT_RIDE
    assert polar_hrm.map_activity_type_index(3) == commons.AT_SWIM
    assert polar_hrm.map_activity_type_index(5) == commons.AT_SKI_F
    assert polar_hrm.map_activity_type_index(6) == commons.AT_RS_F
    assert polar_hrm.map_activity_type_index(9) == commons.AT_RIDE_MOUNTAIN
    assert polar_hrm.map_activity_type_index(10) == commons.AT_SKATE_INLINE
    print("DONE: activity type index returns correct MyTraL activity_type_key strings")


@pytest.mark.mytral
def test_map_activity_type_index_unknown_falls_back_to_gym():
    """Map with an unrecognized code should fall back to AT_GYM."""
    #
    # GIVEN
    #
    unknown_index = 999

    #
    # WHEN
    #
    result = polar_hrm.map_activity_type_index(unknown_index)

    #
    # THEN
    #
    assert result == commons.AT_GYM
    print("DONE: activity type map unknown code falls back to AT_GYM")


#
# parse_hrm — real data
#


@pytest.mark.mytral
@pytest.mark.skipif(not _HRM_2003.exists(), reason="Polar test data not available")
def test_parse_hrm_real_file():
    """parse_hrm should extract correct header fields from a real .hrm file."""
    #
    # GIVEN
    #
    hrm_path = _HRM_2003  # 03092801.hrm — manually verified

    #
    # WHEN
    #
    hrm_data = polar_hrm.parse_hrm(hrm_path)

    #
    # THEN
    #
    # activity type index comes from PDD, not HRM — but start time is in HRM
    assert hrm_data["start_hour"] == 10, (
        f"Expected start_hour=10, got {hrm_data['start_hour']}"
    )
    assert hrm_data["start_minute"] == 45, (
        f"Expected start_minute=45, got {hrm_data['start_minute']}"
    )
    assert hrm_data["avg_hr"] == 154, f"Expected avg_hr=154, got {hrm_data['avg_hr']}"
    assert hrm_data["max_hr"] == 194, f"Expected max_hr=194, got {hrm_data['max_hr']}"
    assert isinstance(hrm_data.get("rows"), list)
    assert len(hrm_data["rows"]) > 0
    print(
        f"DONE: parse_hrm avg_hr={hrm_data['avg_hr']}, max_hr={hrm_data['max_hr']}, "
        f"rows={len(hrm_data['rows'])}"
    )


#
# parse_pdd — real data
#


@pytest.mark.mytral
@pytest.mark.skipif(not _PDD_2003.exists(), reason="Polar test data not available")
def test_parse_pdd_real_file():
    """parse_pdd should extract exercise entries from a real .pdd file."""
    #
    # GIVEN
    #
    pdd_path = _PDD_2003

    #
    # WHEN
    #
    exercises = polar_hrm.parse_pdd(pdd_path)

    #
    # THEN
    #
    assert len(exercises) > 0, "Expected at least one exercise in pdd file"
    ex = exercises[0]
    assert "activity_type_index" in ex
    assert "start_time_s" in ex
    assert "duration_s" in ex
    assert ex["duration_s"] > 0
    print(
        f"DONE: parse_pdd found {len(exercises)} exercise(s), "
        f"first activity_type_key={ex['activity_type_index']}"
    )


#
# build_fit - verify output parses with fitparse
#


@pytest.mark.mytral
@pytest.mark.skipif(not _HRM_2003.exists(), reason="Polar test data not available")
def test_build_fit_produces_valid_bytes():
    """build_fit should produce bytes that fitparse can read back."""
    #
    # GIVEN
    #

    hrm_data = polar_hrm.parse_hrm(_HRM_2003)
    start_dt = datetime.datetime(2003, 9, 28, 10, 45, 28, tzinfo=datetime.timezone.utc)

    #
    # WHEN
    #
    fit_bytes = polar_hrm.build_fit(
        hrm_data=hrm_data,
        start_dt=start_dt,
        activity_type_index=hrm_data.get("activity_type_index", 2),
        interval_s=hrm_data.get("interval_s", 5),
    )

    #
    # THEN
    #
    assert isinstance(fit_bytes, bytes)
    assert len(fit_bytes) > 0

    # verify it is parseable
    parsed = fitparse.FitFile(io.BytesIO(fit_bytes))
    records = list(parsed.get_messages("record"))
    assert len(records) > 0, "Expected at least one record message in FIT output"
    print(
        f"DONE: build_fit produced {len(fit_bytes)} bytes, {len(records)} FIT records"
    )


#
# PolarHrmImportPlugin.import_activities — integration test
#


@pytest.mark.mytral
@pytest.mark.skipif(not _POLAR_HAS_DATA, reason="Polar test data not available")
def test_plugin_import_activities_2003(tmp_path: pathlib.Path):
    """import_activities should return activities for a single-year directory."""
    #
    # GIVEN
    #
    _, _, user_profile = _given.given_test(
        config.MytralConfig(persistence_data_dir=tmp_path),
        user_id="test_polar_user",
    )
    plugin: PolarPlugin = plugins.registry.get_plugin(PolarPlugin.NAME)
    year_dir = _POLAR_DATA_DIR / "2003"

    #
    # WHEN
    #
    activities = plugin.import_activities(
        datasets={polar_hrm.POLAR_HRM_DATA_DIR_KEY: year_dir},
        user_profile=user_profile,
    )

    #
    # THEN
    #
    assert len(activities) > 0, "Expected activities imported from 2003"
    for a in activities:
        assert a.when_year == 2003
        assert a.src == polar_hrm.POLAR_HRM_IMPORT_SRC
        assert a.activity_type_key in [
            commons.AT_RUN,
            commons.AT_RIDE,
            commons.AT_SWIM,
            commons.AT_SKI_DP,
            commons.AT_SKI_F,
            commons.AT_RS_DP,
            commons.AT_RS_F,
            commons.AT_GYM,
            commons.AT_HIKE,
            commons.AT_PADDLE,
            commons.AT_SKI_DOWNHILL,
            commons.AT_KAYAK,
        ], f"Unexpected activity_type_key: {a.activity_type_key}"
    print(
        f"DONE: plugin imported {len(activities)} activities from 2003, "
        f"first={activities[0].src_key}"
    )


#
# compute_max_speed_kmh / compute_elevation_gain — pure-function helpers
#


@pytest.mark.mytral
def test_compute_max_speed_kmh_from_rows():
    """compute_max_speed_kmh should return the max row speed divided by 10."""
    #
    # GIVEN
    #
    rows: list[dict] = [
        {"hr": 120, "speed_01kmh": 0, "altitude_m": 100},
        {"hr": 130, "speed_01kmh": 200, "altitude_m": 105},
        {"hr": 140, "speed_01kmh": 350, "altitude_m": 110},
        {"hr": 135, "speed_01kmh": 280, "altitude_m": 108},
        {"hr": 125, "speed_01kmh": 100, "altitude_m": 112},
    ]

    #
    # WHEN
    #
    max_speed_with_flag = polar_hrm.compute_max_speed_kmh(rows, True)
    max_speed_without_flag = polar_hrm.compute_max_speed_kmh(rows, False)
    max_speed_empty = polar_hrm.compute_max_speed_kmh([], True)

    #
    # THEN
    #
    assert max_speed_with_flag == 35.0, f"Expected 35.0 km/h, got {max_speed_with_flag}"
    assert max_speed_without_flag == 0.0, (
        f"Expected 0.0 when has_speed=False, got {max_speed_without_flag}"
    )
    assert max_speed_empty == 0.0, f"Expected 0.0 for empty rows, got {max_speed_empty}"
    print("DONE: compute_max_speed_kmh returns row max / 10")


@pytest.mark.mytral
def test_compute_elevation_gain_from_rows():
    """compute_elevation_gain should sum positive altitude deltas only."""
    #
    # GIVEN
    #
    rows: list[dict] = [
        {"hr": 120, "speed_01kmh": 0, "altitude_m": 100},
        {"hr": 130, "speed_01kmh": 200, "altitude_m": 105},
        {"hr": 140, "speed_01kmh": 350, "altitude_m": 110},
        {"hr": 135, "speed_01kmh": 280, "altitude_m": 108},  # down-step ignored
        {"hr": 125, "speed_01kmh": 100, "altitude_m": 112},
    ]

    #
    # WHEN
    #
    gain_with_flag = polar_hrm.compute_elevation_gain(rows, True)
    gain_without_flag = polar_hrm.compute_elevation_gain(rows, False)
    gain_empty = polar_hrm.compute_elevation_gain([], True)

    #
    # THEN
    #
    # +5 (100→105) +5 (105→110) +0 (110→108 down) +4 (108→112) = 14
    assert gain_with_flag == 14, f"Expected 14 m, got {gain_with_flag}"
    assert gain_without_flag == 0, (
        f"Expected 0 when has_altitude=False, got {gain_without_flag}"
    )
    assert gain_empty == 0, f"Expected 0 for empty rows, got {gain_empty}"
    print("DONE: compute_elevation_gain sums positive altitude deltas only")


@pytest.mark.mytral
def test_compute_elevation_gain_skips_none_altitudes():
    """compute_elevation_gain should skip rows where altitude_m is None/absent."""
    #
    # GIVEN
    #
    rows: list[dict] = [
        {"hr": 120, "altitude_m": 100},
        {"hr": 130},  # altitude_m key absent (parse failure)
        {"hr": 140, "altitude_m": 110},
        {"hr": 135, "altitude_m": None},  # explicit None
        {"hr": 125, "altitude_m": 115},
    ]

    #
    # WHEN
    #
    gain = polar_hrm.compute_elevation_gain(rows, True)

    #
    # THEN
    #
    # 100→110 = +10 (row 1 skipped, row 2→3: None skipped), 110→115 = +5
    assert gain == 15, f"Expected 15 m (skipping None/absent), got {gain}"
    print("DONE: compute_elevation_gain skips None and absent altitude_m keys")


@pytest.mark.mytral
def test_compute_elevation_gain_single_row_returns_zero():
    """compute_elevation_gain with a single row should return 0 (no deltas)."""
    #
    # GIVEN
    #
    rows: list[dict] = [{"hr": 120, "altitude_m": 100}]

    #
    # WHEN
    #
    gain = polar_hrm.compute_elevation_gain(rows, True)

    #
    # THEN
    #
    assert gain == 0, f"Expected 0 for single row, got {gain}"
    print("DONE: compute_elevation_gain single row returns 0")


@pytest.mark.mytral
def test_compute_max_speed_kmh_skips_missing_speed_keys():
    """compute_max_speed_kmh should skip rows where speed_01kmh is absent."""
    #
    # GIVEN
    #
    rows: list[dict] = [
        {"hr": 120, "speed_01kmh": 100},
        {"hr": 130},  # speed_01kmh key absent (parse failure)
        {"hr": 140, "speed_01kmh": 350},
        {"hr": 135, "speed_01kmh": 200},
    ]

    #
    # WHEN
    #
    max_speed = polar_hrm.compute_max_speed_kmh(rows, True)

    #
    # THEN
    #
    # max of [100, 0 (default), 350, 200] = 350 → 35.0 km/h
    assert max_speed == 35.0, f"Expected 35.0 km/h (max=350/10), got {max_speed}"
    print("DONE: compute_max_speed_kmh skips absent speed_01kmh keys")


#
# _build_activity — uses HRData, not the broken [Trip] section
#

# Roman's Polar dataset — only present on the local development machine,
# used to validate the fix for the validation-page regressions.
_ROMAN_DATA_DIR = (
    pathlib.Path("/home/dvorka/p/mytral/datasets-COMPLETE/roman-vetesnik")
    / "Polar 20.1.18"
    / "Polar Precision Performance"
    / "Roman"
)
# A known-bad file from Roman's 2003-11-08 run where the GPS was just
# acquiring a fix; the [Trip] section reports elevation_gain=3280m and
# max_speed=9.0 km/h but the HRData has the correct values.
_ROMAN_2003_11_08_HRM = _ROMAN_DATA_DIR / "2003" / "03110803.hrm"
_ROMAN_2003_11_08_PDD = _ROMAN_DATA_DIR / "2003" / "20031108.pdd"

# Synthetic HRM/PDD pair that reproduces the S720i broken-[Trip] scenario
# in a minimal form — committed to the repo so the fix is tested in CI.
_SYNTHETIC_DATA_DIR = (
    pathlib.Path(__file__).parent / "data" / "import" / "polar" / "synthetic"
)
_SYNTHETIC_HRM = _SYNTHETIC_DATA_DIR / "03110803.hrm"
_SYNTHETIC_PDD = _SYNTHETIC_DATA_DIR / "20031108.pdd"


@pytest.mark.mytral
@pytest.mark.skipif(
    not _ROMAN_2003_11_08_HRM.exists() or not _ROMAN_2003_11_08_PDD.exists(),
    reason="Roman Polar dataset not available",
)
def test_build_activity_uses_hrdata_not_trip_for_speed_elevation():
    """_build_activity must take max_speed/elevation_gain from HRData, not Trip.

    The Polar S720i ``[Trip]`` section is unreliable: for Roman's
    2003-11-08 08:50:18 run it reports ``max_speed_kmh=9.0`` and
    ``elevation_gain=3280`` while the HRData time series has the
    correct values. The activity produced for the validation page must
    use the HRData-derived values, and must not set ``min_hr`` (a
    day-level metric, not a per-activity one).
    """
    #
    # GIVEN
    #
    hrm_data = polar_hrm.parse_hrm(_ROMAN_2003_11_08_HRM)
    pdd_exercises = polar_hrm.parse_pdd(_ROMAN_2003_11_08_PDD)
    # Find the exercise that points at 03110803.hrm
    ex = next(
        (e for e in pdd_exercises if e.get("hrm_filename") == "03110803.hrm"),
        None,
    )
    assert ex is not None, "Expected PDD exercise for 03110803.hrm"

    plugin: PolarPlugin = PolarPlugin()
    plugin._hrm_data_cache["03110803.hrm"] = hrm_data

    # Synthetic user profile with the minimum surface the plugin reads.
    profile = _make_minimal_user_profile()

    #
    # WHEN
    #
    activity = plugin._build_activity(
        exercise=ex,
        year_dir=_ROMAN_2003_11_08_HRM.parent,
        user_profile=profile,
        correlation_id="test-correlation",
    )

    #
    # THEN
    #
    assert activity is not None
    # max_speed comes from HRData, NOT the broken [Trip] section
    assert activity.max_speed > 30.0, (
        f"max_speed should be HRData-derived (>30 km/h), got {activity.max_speed}"
    )
    # elevation_gain comes from HRData, NOT the broken [Trip] section
    assert activity.elevation_gain < 200, (
        f"elevation_gain should be HRData-derived (small), "
        f"got {activity.elevation_gain}"
    )
    # min_hr is a day-level metric — must not be set from per-activity HR
    assert activity.min_hr == 0.0, (
        f"min_hr must be 0 (day-level metric), got {activity.min_hr}"
    )
    # avg_speed is still recomputed from distance / duration (PDD-based)
    assert activity.avg_speed > 20.0, (
        f"avg_speed should be ~26 km/h (distance/duration), got {activity.avg_speed}"
    )
    # and the validation-page invariant avg_speed <= max_speed now holds
    assert activity.avg_speed <= activity.max_speed, (
        f"avg_speed ({activity.avg_speed}) should not exceed max_speed "
        f"({activity.max_speed})"
    )
    print(
        "DONE: _build_activity uses HRData for max_speed/elevation_gain "
        f"and leaves min_hr at 0 (max_speed={activity.max_speed}, "
        f"elevation_gain={activity.elevation_gain})"
    )


@pytest.mark.mytral
def test_build_activity_uses_hrdata_not_trip_ci():
    """_build_activity must use HRData-derived speed/elevation (CI-safe).

    Uses a synthetic .hrm/.pdd pair committed to the repo that reproduces
    the S720i broken-[Trip] scenario: Trip reports max_speed=9.0 km/h and
    elevation_gain=3280 m while the HRData time series has the correct
    values (max_speed=35.0 km/h, elevation_gain=24 m).  The synthetic
    files are minimal — just enough rows to exercise the fix.
    """
    #
    # GIVEN
    #
    hrm_data = polar_hrm.parse_hrm(_SYNTHETIC_HRM)
    pdd_exercises = polar_hrm.parse_pdd(_SYNTHETIC_PDD)
    ex = next(
        (e for e in pdd_exercises if e.get("hrm_filename") == "03110803.hrm"),
        None,
    )
    assert ex is not None, "Expected PDD exercise for 03110803.hrm"

    plugin: PolarPlugin = PolarPlugin()
    plugin._hrm_data_cache["03110803.hrm"] = hrm_data
    profile = _make_minimal_user_profile()

    #
    # WHEN
    #
    activity = plugin._build_activity(
        exercise=ex,
        year_dir=_SYNTHETIC_DATA_DIR,
        user_profile=profile,
        correlation_id="test-correlation-ci",
    )

    #
    # THEN
    #
    assert activity is not None
    # max_speed comes from HRData (35.0 km/h), NOT Trip (9.0 km/h)
    assert activity.max_speed == 35.0, (
        f"max_speed should be 35.0 (HRData-derived), got {activity.max_speed}"
    )
    # elevation_gain comes from HRData (24 m), NOT Trip (3280 m)
    assert activity.elevation_gain == 24, (
        f"elevation_gain should be 24 (HRData-derived), got {activity.elevation_gain}"
    )
    # elevation_max comes from HRData (120 m), NOT Trip (3280 m)
    assert activity.elevation_max == 120, (
        f"elevation_max should be 120 (HRData-preferred), got {activity.elevation_max}"
    )
    # min_hr is a day-level metric — must not be set from per-activity HR
    assert activity.min_hr == 0.0, (
        f"min_hr must be 0 (day-level metric), got {activity.min_hr}"
    )
    # avg_speed computed from PDD distance/duration: 16000m / 2292s * 3.6 ≈ 25.13
    assert 25.0 < activity.avg_speed < 26.0, (
        f"avg_speed should be ~25.1 km/h, got {activity.avg_speed}"
    )
    # validation invariant: avg_speed <= max_speed
    assert activity.avg_speed <= activity.max_speed, (
        f"avg_speed ({activity.avg_speed}) should not exceed max_speed "
        f"({activity.max_speed})"
    )
    print(
        "DONE: _build_activity uses HRData for max_speed/elevation_gain/elevation_max "
        f"(max_speed={activity.max_speed}, elevation_gain={activity.elevation_gain}, "
        f"elevation_max={activity.elevation_max})"
    )


def _make_minimal_user_profile() -> object:
    """Build a stand-in UserProfile that exposes the attributes the plugin reads.

    The real ``UserProfile.__init__`` has many required fields and pulls in
    several heavyweight subsystems; tests only need ``height`` to be set
    so :func:`evaluate_activity` does not crash.
    """
    return type(
        "_MinimalUserProfile",
        (),
        {
            "height": 180,
            "weight": 80,
            "rest_hr": 60,
            "max_hr": 190,
            "ftp_watts": 250,
            "refresh": lambda self: None,
            "refresh_age": lambda self: 30,
        },
    )()
