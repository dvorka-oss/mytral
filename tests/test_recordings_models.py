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
"""Tests for mytral.recordings.models."""

import datetime

import pytest

from mytral.recordings.models import RecordingData
from mytral.recordings.models import RecordingFmt
from mytral.recordings.models import RecordingSummary


@pytest.mark.mytral
def test_recording_data_creation():
    """Test basic RecordingData creation with all fields."""
    # GIVEN
    now = datetime.datetime.now()
    timestamps = [now, now + datetime.timedelta(seconds=1)]
    hr = [120, 125]
    speed = [25.0, 26.0]
    cadence = [80, 82]
    altitude = [100.0, 101.0]
    lat = [50.0, 50.001]
    lon = [14.0, 14.001]
    power = [200.0, 205.0]

    # WHEN
    rd = RecordingData(
        timestamps=timestamps,
        hr_values=hr,
        speed_values=speed,
        cadence_values=cadence,
        altitude_values=altitude,
        lat_values=lat,
        lon_values=lon,
        power_values=power,
        has_speed=True,
        has_cadence=True,
        has_altitude=True,
        has_gps=True,
        has_power=True,
        source_format="fit",
    )

    # THEN
    assert len(rd.timestamps) == 2
    assert rd.hr_values == [120, 125]
    assert rd.speed_values == [25.0, 26.0]
    assert rd.has_speed is True
    assert rd.has_cadence is True
    assert rd.has_altitude is True
    assert rd.has_gps is True
    assert rd.has_power is True
    assert rd.source_format == "fit"
    print("RecordingData creation: DONE")


@pytest.mark.mytral
def test_recording_data_nullable_channels():
    """Test RecordingData with nullable (None) channel values."""
    # GIVEN
    now = datetime.datetime.now()

    # WHEN
    rd = RecordingData(
        timestamps=[now],
        hr_values=[None],
        speed_values=[None],
        cadence_values=[None],
        altitude_values=[None],
        lat_values=[None],
        lon_values=[None],
        power_values=[None],
        has_speed=False,
        has_cadence=False,
        has_altitude=False,
        has_gps=False,
        has_power=False,
        source_format="hrm",
    )

    # THEN
    assert rd.hr_values == [None]
    assert rd.speed_values == [None]
    assert rd.has_speed is False
    assert rd.source_format == "hrm"
    print("RecordingData nullable channels: DONE")


@pytest.mark.mytral
def test_recording_summary_defaults():
    """Test that RecordingSummary has correct defaults."""
    # GIVEN / WHEN
    s = RecordingSummary()

    # THEN
    assert s.activity_type_key is None
    assert s.when is None
    assert s.hours is None
    assert s.minutes is None
    assert s.seconds is None
    assert s.distance is None
    assert s.kcal is None
    assert s.avg_hr is None
    assert s.max_hr is None
    assert s.avg_cadence is None
    assert s.max_cadence is None
    assert s.avg_speed is None
    assert s.max_speed is None
    assert s.avg_watts is None
    assert s.max_watts is None
    assert s.elevation_gain is None
    assert s.name_hint is None
    print("RecordingSummary defaults: DONE")


@pytest.mark.mytral
def test_recording_summary_partial_fill():
    """Test RecordingSummary with some fields filled."""
    # GIVEN
    when = datetime.datetime(2024, 6, 1, 10, 0, 0)

    # WHEN
    s = RecordingSummary(
        activity_type_key="run",
        when=when,
        hours=1,
        minutes=30,
        seconds=0,
        distance=15000,
        avg_hr=145,
        max_hr=175,
    )

    # THEN
    assert s.activity_type_key == "run"
    assert s.when == when
    assert s.hours == 1
    assert s.minutes == 30
    assert s.seconds == 0
    assert s.distance == 15000
    assert s.avg_hr == 145
    assert s.max_hr == 175
    assert s.kcal is None
    print("RecordingSummary partial fill: DONE")


@pytest.mark.mytral
def test_recording_fmt_values():
    """Test RecordingFmt enum values."""
    # GIVEN / WHEN / THEN
    assert RecordingFmt.FIT.value == ".fit"
    assert RecordingFmt.GPX.value == ".gpx"
    assert RecordingFmt.HRM.value == ".hrm"
    print("RecordingFmt values: DONE")
