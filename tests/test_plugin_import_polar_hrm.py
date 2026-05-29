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
# build_fit — verify output parses with fitparse
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
