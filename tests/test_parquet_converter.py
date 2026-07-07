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
"""Tests for mytral.recordings.parquet_converter."""

import datetime
import io

import polars
import pytest

from mytral.recordings.parquet_converter import _derive_speed_from_gps
from mytral.recordings.parquet_converter import fit_to_parquet
from mytral.recordings.parquet_converter import gpx_to_parquet
from mytral.recordings.parquet_converter import hrm_to_parquet
from mytral.recordings.parquet_converter import load_parquet
from tests import _given

# expected canonical schema columns
_EXPECTED_COLUMNS = {
    "ts_unix_ms",
    "hr",
    "speed",
    "cadence",
    "altitude",
    "lat",
    "lon",
    "power",
    "has_speed",
    "has_cadence",
    "has_altitude",
    "has_gps",
    "has_power",
    "source_format",
}


@pytest.mark.mytral
def test_fit_to_parquet_schema():
    """Test that fit_to_parquet produces the canonical Parquet schema."""
    # GIVEN
    fit_files = sorted(_given.TEST_DATA_FIT_DIR.glob("*.fit"))
    assert fit_files, f"no .fit files in {_given.TEST_DATA_FIT_DIR}"
    fit_data = fit_files[0].read_bytes()

    # WHEN
    parquet_bytes = fit_to_parquet(fit_data)

    # THEN
    df = polars.read_parquet(io.BytesIO(parquet_bytes))
    assert set(df.columns) == _EXPECTED_COLUMNS, (
        f"schema mismatch: {set(df.columns)} != {_EXPECTED_COLUMNS}"
    )
    assert len(df) > 0, "expected non-empty parquet from real FIT file"
    assert df["source_format"][0] == "fit"
    print(f"fit_to_parquet schema: DONE ({len(df)} rows)")


@pytest.mark.mytral
def test_fit_to_parquet_empty_data():
    """Test that fit_to_parquet handles empty/corrupt bytes gracefully."""
    # GIVEN
    fit_data = b""

    # WHEN
    parquet_bytes = fit_to_parquet(fit_data)

    # THEN
    df = polars.read_parquet(io.BytesIO(parquet_bytes))
    assert df.is_empty()
    print("fit_to_parquet empty data: DONE")


@pytest.mark.mytral
def test_gpx_to_parquet_schema_minimal():
    """Test that gpx_to_parquet produces the canonical schema from minimal GPX."""
    # GIVEN
    minimal_gpx = b"""<?xml version="1.0"?>
<gpx version="1.1" xmlns="http://www.topografix.com/GPX/1/1">
  <trk><trkseg>
    <trkpt lat="50.0" lon="14.0">
      <ele>200.0</ele>
      <time>2024-06-01T10:00:00Z</time>
    </trkpt>
    <trkpt lat="50.001" lon="14.001">
      <ele>201.0</ele>
      <time>2024-06-01T10:00:05Z</time>
    </trkpt>
  </trkseg></trk>
</gpx>"""

    # WHEN
    parquet_bytes = gpx_to_parquet(minimal_gpx)

    # THEN
    df = polars.read_parquet(io.BytesIO(parquet_bytes))
    assert set(df.columns) == _EXPECTED_COLUMNS
    assert len(df) == 2
    assert df["source_format"][0] == "gpx"
    assert df["has_gps"][0] is True
    assert df["lat"][0] == pytest.approx(50.0)
    assert df["lon"][0] == pytest.approx(14.0)
    print("gpx_to_parquet minimal: DONE")


@pytest.mark.mytral
def test_gpx_to_parquet_empty_data():
    """Test that gpx_to_parquet handles empty/corrupt bytes gracefully."""
    # GIVEN
    gpx_data = b""

    # WHEN
    parquet_bytes = gpx_to_parquet(gpx_data)

    # THEN
    df = polars.read_parquet(io.BytesIO(parquet_bytes))
    assert df.is_empty()
    print("gpx_to_parquet empty data: DONE")


@pytest.mark.mytral
def test_derive_speed_from_gps_smooths_gps_noise():
    """Test that GPS speed estimation dampens single-point position spikes."""
    # GIVEN - a straight ~constant-speed track (11 m every second, ~40 km/h)
    #         with one noisy point jumping ~100 m sideways and back
    base = datetime.datetime(2024, 6, 1, 10, 0, 0, tzinfo=datetime.timezone.utc)
    n = 40
    timestamps = [base + datetime.timedelta(seconds=i) for i in range(n)]
    lats = [50.0 + i * 0.0001 for i in range(n)]
    lons = [14.0] * n
    # inject a GPS glitch at the midpoint (~140 m east then back)
    lons[20] = 14.002

    # WHEN
    speed = _derive_speed_from_gps(timestamps, lats, lons)

    # THEN - naive point-to-point would spike to hundreds of km/h at the glitch,
    #        the windowed estimate stays physically plausible
    assert len(speed) == n
    assert all(v is not None for v in speed)
    assert max(speed) < 90.0
    print("derive_speed_from_gps smooths GPS noise: DONE")


@pytest.mark.mytral
def test_load_parquet_estimates_speed_from_gps():
    """Test that load_parquet estimates speed for a GPX track lacking speed."""
    # GIVEN - a GPX track (has GPS, no native speed channel)
    gpx = b"""<?xml version="1.0"?>
<gpx version="1.1" xmlns="http://www.topografix.com/GPX/1/1">
  <trk><trkseg>
    <trkpt lat="50.0000" lon="14.0"><time>2024-06-01T10:00:00Z</time></trkpt>
    <trkpt lat="50.0001" lon="14.0"><time>2024-06-01T10:00:01Z</time></trkpt>
    <trkpt lat="50.0002" lon="14.0"><time>2024-06-01T10:00:02Z</time></trkpt>
    <trkpt lat="50.0003" lon="14.0"><time>2024-06-01T10:00:03Z</time></trkpt>
    <trkpt lat="50.0004" lon="14.0"><time>2024-06-01T10:00:04Z</time></trkpt>
  </trkseg></trk>
</gpx>"""

    # WHEN
    rec = load_parquet(gpx_to_parquet(gpx))

    # THEN
    assert rec.has_gps is True
    assert rec.has_speed is True
    assert rec.speed_estimated is True
    assert any(v is not None and v > 0 for v in rec.speed_values)
    print("load_parquet estimates speed from GPS: DONE")


@pytest.mark.mytral
def test_load_parquet_no_speed_estimation_without_gps():
    """Test that load_parquet does not estimate speed when GPS is absent."""
    # GIVEN - an HRM recording: heart rate only, no GPS, no native speed
    hrm_data = {
        "rows": [{"hr": 130}, {"hr": 135}, {"hr": 140}],
        "has_speed": False,
        "has_cadence": False,
        "has_altitude": False,
        "interval_s": 5,
        "start_hour": 10,
        "start_minute": 0,
        "start_second": 0,
        "date": 20240601,
    }

    # WHEN
    rec = load_parquet(hrm_to_parquet(hrm_data))

    # THEN
    assert rec.has_gps is False
    assert rec.has_speed is False
    assert rec.speed_estimated is False
    print("load_parquet no speed estimation without GPS: DONE")


@pytest.mark.mytral
def test_hrm_to_parquet_schema():
    """Test that hrm_to_parquet produces the canonical schema from HRM dict."""
    # GIVEN
    hrm_data = {
        "rows": [
            {"hr": 130},
            {"hr": 135},
            {"hr": 140},
        ],
        "has_speed": False,
        "has_cadence": False,
        "has_altitude": False,
        "interval_s": 5,
        "start_hour": 10,
        "start_minute": 0,
        "start_second": 0,
        "date": 20240601,
    }

    # WHEN
    parquet_bytes = hrm_to_parquet(hrm_data)

    # THEN
    df = polars.read_parquet(io.BytesIO(parquet_bytes))
    assert set(df.columns) == _EXPECTED_COLUMNS
    assert len(df) == 3
    assert df["source_format"][0] == "hrm"
    assert df["hr"][0] == 130
    assert df["has_gps"][0] is False
    print("hrm_to_parquet schema: DONE")


@pytest.mark.mytral
def test_hrm_to_parquet_empty():
    """Test that hrm_to_parquet handles empty rows gracefully."""
    # GIVEN
    hrm_data: dict = {
        "rows": [],
        "has_speed": False,
        "has_cadence": False,
        "has_altitude": False,
        "interval_s": 5,
        "date": 20240101,
    }

    # WHEN
    parquet_bytes = hrm_to_parquet(hrm_data)

    # THEN
    df = polars.read_parquet(io.BytesIO(parquet_bytes))
    assert df.is_empty()
    print("hrm_to_parquet empty: DONE")


@pytest.mark.mytral
def test_load_parquet_from_fit():
    """Test round-trip: FIT → Parquet bytes → RecordingData."""
    # GIVEN
    fit_files = sorted(_given.TEST_DATA_FIT_DIR.glob("*.fit"))
    assert fit_files
    fit_data = fit_files[0].read_bytes()
    parquet_bytes = fit_to_parquet(fit_data)

    # WHEN
    rec = load_parquet(parquet_bytes)

    # THEN
    assert len(rec.timestamps) > 0
    assert len(rec.timestamps) == len(rec.hr_values)
    assert len(rec.timestamps) == len(rec.speed_values)
    assert rec.source_format == "fit"
    print(f"load_parquet round-trip FIT: DONE ({len(rec.timestamps)} rows)")


@pytest.mark.mytral
def test_load_parquet_empty():
    """Test load_parquet returns empty RecordingData for empty parquet."""
    # GIVEN
    parquet_bytes = fit_to_parquet(b"")

    # WHEN
    rec = load_parquet(parquet_bytes)

    # THEN
    assert rec.timestamps == []
    assert rec.hr_values == []
    assert rec.source_format == ""
    print("load_parquet empty: DONE")


@pytest.mark.mytral
def test_fit_to_parquet_all_files():
    """Test that fit_to_parquet handles all FIT files in the test data directory."""
    # GIVEN
    fit_files = sorted(_given.TEST_DATA_FIT_DIR.glob("*.fit"))
    assert fit_files

    # WHEN / THEN
    for fit_path in fit_files:
        fit_data = fit_path.read_bytes()
        parquet_bytes = fit_to_parquet(fit_data)
        rec = load_parquet(parquet_bytes)
        assert len(rec.timestamps) > 0, f"no records for {fit_path.name}"
        print(f"fit_to_parquet {fit_path.name}: DONE ({len(rec.timestamps)} rows)")
