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
"""Tests for FIT and GPX extractors."""

import datetime
import math

import pytest

from mytral.recordings.fit_extractor import extract_fit_summary
from mytral.recordings.gpx_extractor import decode_polyline
from mytral.recordings.gpx_extractor import encode_gps_polylines
from mytral.recordings.gpx_extractor import extract_elevation_profile
from mytral.recordings.gpx_extractor import extract_gps_points
from mytral.recordings.gpx_extractor import extract_gpx_summary
from mytral.recordings.models import RecordingSummary
from tests import _given


def _distance_meters(
    point_a: tuple[float, float],
    point_b: tuple[float, float],
) -> float:
    """Compute haversine distance between two points in meters."""
    earth_radius_m = 6371000.0
    lat1_rad = math.radians(point_a[0])
    lat2_rad = math.radians(point_b[0])
    delta_lat_rad = math.radians(point_b[0] - point_a[0])
    delta_lon_rad = math.radians(point_b[1] - point_a[1])
    haversine = (
        math.sin(delta_lat_rad / 2.0) ** 2
        + math.cos(lat1_rad) * math.cos(lat2_rad) * math.sin(delta_lon_rad / 2.0) ** 2
    )
    return (
        2.0
        * earth_radius_m
        * math.atan2(math.sqrt(haversine), math.sqrt(1.0 - haversine))
    )


def _polyline_length_meters(points: list[tuple[float, float]]) -> float:
    """Compute total polyline length in meters."""
    return sum(
        _distance_meters(point_a=point_a, point_b=point_b)
        for point_a, point_b in zip(points, points[1:])
    )


@pytest.mark.mytral
def test_extract_fit_summary_returns_summary():
    """Test that extract_fit_summary returns a RecordingSummary."""
    # GIVEN
    fit_files = sorted(_given.TEST_DATA_FIT_DIR.glob("*.fit"))
    assert fit_files, f"no .fit files in {_given.TEST_DATA_FIT_DIR}"
    fit_data = fit_files[0].read_bytes()

    # WHEN
    summary = extract_fit_summary(fit_data)

    # THEN
    assert isinstance(summary, RecordingSummary)
    print("extract_fit_summary returns RecordingSummary: DONE")


@pytest.mark.mytral
def test_extract_fit_summary_corrupt_data():
    """Test that extract_fit_summary handles corrupt/empty data gracefully."""
    # GIVEN
    fit_data = b"not a fit file"

    # WHEN
    summary = extract_fit_summary(fit_data)

    # THEN
    assert isinstance(summary, RecordingSummary)
    # all fields should remain None when parsing fails
    assert summary.activity_type_key is None
    assert summary.when is None
    print("extract_fit_summary corrupt data: DONE")


@pytest.mark.mytral
def test_extract_fit_summary_all_files():
    """Test that extract_fit_summary processes all test FIT files without error."""
    # GIVEN
    fit_files = sorted(_given.TEST_DATA_FIT_DIR.glob("*.fit"))
    assert fit_files

    # WHEN / THEN
    for fit_path in fit_files:
        fit_data = fit_path.read_bytes()
        summary = extract_fit_summary(fit_data)
        assert isinstance(summary, RecordingSummary)
        print(
            f"extract_fit_summary {fit_path.name}: DONE ({summary.activity_type_key=})"
        )


@pytest.mark.mytral
def test_extract_fit_summary_filters_sentinel_values():
    """Test that FIT protocol invalid-sentinel values are filtered out.

    The FIT protocol uses max-uint values (0xFF for uint8, 0xFFFF for uint16,
    0xFFFFFFFF for uint32) to signal "invalid / not set".  The extractor must
    treat these as missing data and leave the corresponding summary fields at
    None.

    The test file ``920xt-triathlon.fit`` has four sentinel fields in its
    session message:

    - avg_power  = 65535 (0xFFFF, uint16 sentinel)
    - max_power  = 65535 (0xFFFF, uint16 sentinel)
    - avg_hr     = 255   (0xFF,   uint8  sentinel)
    - max_hr     = 255   (0xFF,   uint8  sentinel)

    Valid fields (total_calories=148, total_distance=681.67, avg_speed=0.773,
    avg_cadence=32, max_cadence=42) must still be extracted correctly.
    """
    # GIVEN
    fit_path = _given.TEST_DATA_FIT_DIR / "920xt-triathlon.fit"
    fit_data = fit_path.read_bytes()

    # WHEN
    summary = extract_fit_summary(fit_data)

    # THEN — sentinel fields must be None (filtered out)
    assert summary.avg_watts is None, (
        f"avg_power sentinel 65535 should be filtered, got {summary.avg_watts}"
    )
    assert summary.max_watts is None, (
        f"max_power sentinel 65535 should be filtered, got {summary.max_watts}"
    )
    assert summary.avg_hr is None, (
        f"avg_hr sentinel 255 should be filtered, got {summary.avg_hr}"
    )
    assert summary.max_hr is None, (
        f"max_hr sentinel 255 should be filtered, got {summary.max_hr}"
    )

    # THEN — valid fields must still be extracted
    assert summary.kcal == 148, f"expected kcal=148, got {summary.kcal}"
    assert summary.distance == 681, f"expected distance=681 m, got {summary.distance}"
    assert summary.avg_speed == pytest.approx(2.78, abs=0.1), (
        f"expected avg_speed ~2.78 km/h (0.773 m/s), got {summary.avg_speed}"
    )
    assert summary.avg_cadence == 32, (
        f"expected avg_cadence=32, got {summary.avg_cadence}"
    )
    assert summary.max_cadence == 42, (
        f"expected max_cadence=42, got {summary.max_cadence}"
    )
    assert summary.activity_type_key is not None
    assert summary.when is not None

    print(
        f"FIT sentinel filtering: avg_power={summary.avg_watts}, "
        f"max_power={summary.max_watts}, avg_hr={summary.avg_hr}, "
        f"max_hr={summary.max_hr} all None: DONE"
    )


@pytest.mark.mytral
def test_extract_gpx_summary_minimal_gpx():
    """Test extract_gpx_summary with a minimal GPX file."""
    # GIVEN
    minimal_gpx = b"""<?xml version="1.0"?>
<gpx version="1.1" xmlns="http://www.topografix.com/GPX/1/1">
  <trk><trkseg>
    <trkpt lat="50.0" lon="14.0">
      <ele>200.0</ele>
      <time>2024-06-01T10:00:00Z</time>
    </trkpt>
    <trkpt lat="50.1" lon="14.1">
      <ele>250.0</ele>
      <time>2024-06-01T11:00:00Z</time>
    </trkpt>
  </trkseg></trk>
</gpx>"""

    # WHEN
    summary = extract_gpx_summary(minimal_gpx)

    # THEN
    assert isinstance(summary, RecordingSummary)
    assert summary.activity_type_key == "run"
    assert summary.when is not None
    assert isinstance(summary.when, datetime.datetime)
    assert summary.hours == 1
    assert summary.minutes == 0
    assert summary.seconds == 0
    assert summary.elevation_gain == 50
    assert summary.distance is not None
    assert 13000 < summary.distance < 15000, (
        f"expected ~14 km haversine distance for 0.1 deg, got {summary.distance} m"
    )
    print(f"extract_gpx_summary minimal: DONE (distance={summary.distance} m)")


@pytest.mark.mytral
def test_extract_gpx_summary_with_hr():
    """Test extract_gpx_summary extracts HR from TrackPointExtension."""
    # GIVEN
    gpx_with_hr = b"""<?xml version="1.0"?>
<gpx version="1.1" xmlns="http://www.topografix.com/GPX/1/1"
     xmlns:gpxtpx="http://www.garmin.com/xmlschemas/TrackPointExtension/v1">
  <trk><trkseg>
    <trkpt lat="50.0" lon="14.0">
      <time>2024-06-01T10:00:00Z</time>
      <extensions>
        <gpxtpx:TrackPointExtension>
          <gpxtpx:hr>140</gpxtpx:hr>
        </gpxtpx:TrackPointExtension>
      </extensions>
    </trkpt>
    <trkpt lat="50.001" lon="14.001">
      <time>2024-06-01T10:00:05Z</time>
      <extensions>
        <gpxtpx:TrackPointExtension>
          <gpxtpx:hr>150</gpxtpx:hr>
        </gpxtpx:TrackPointExtension>
      </extensions>
    </trkpt>
  </trkseg></trk>
</gpx>"""

    # WHEN
    summary = extract_gpx_summary(gpx_with_hr)

    # THEN
    assert isinstance(summary, RecordingSummary)
    assert summary.avg_hr == 145
    assert summary.max_hr == 150
    print("extract_gpx_summary with HR: DONE")


@pytest.mark.mytral
def test_extract_gpx_summary_corrupt_data():
    """Test that extract_gpx_summary handles corrupt/empty data gracefully."""
    # GIVEN
    gpx_data = b"not xml at all"

    # WHEN
    summary = extract_gpx_summary(gpx_data)

    # THEN
    assert isinstance(summary, RecordingSummary)
    assert summary.activity_type_key is None
    assert summary.when is None
    print("extract_gpx_summary corrupt data: DONE")


@pytest.mark.mytral
def test_extract_gpx_summary_empty():
    """Test extract_gpx_summary handles empty bytes."""
    # GIVEN
    gpx_data = b""

    # WHEN
    summary = extract_gpx_summary(gpx_data)

    # THEN
    assert isinstance(summary, RecordingSummary)
    assert summary.when is None
    print("extract_gpx_summary empty: DONE")


@pytest.mark.mytral
def test_extract_gpx_summary_no_timestamps():
    """Distance/elevation should be extracted even when trackpoints lack time."""
    # GIVEN — like Strava exports which omit <time> from trackpoints
    gpx = b"""<?xml version="1.0"?>
<gpx version="1.1" xmlns="http://www.topografix.com/GPX/1/1">
  <trk><trkseg>
    <trkpt lat="50.0" lon="14.0"><ele>100</ele></trkpt>
    <trkpt lat="50.1" lon="14.1"><ele>200</ele></trkpt>
    <trkpt lat="50.2" lon="14.2"><ele>250</ele></trkpt>
  </trkseg></trk>
</gpx>"""

    # WHEN
    summary = extract_gpx_summary(gpx)

    # THEN
    assert isinstance(summary, RecordingSummary)
    assert summary.when is None, "no timestamps → when must be None"
    # duration is estimated from distance using 7 km/h pace
    assert summary.hours is not None, "duration estimated from distance"
    assert summary.minutes is not None, "duration estimated from distance"
    assert summary.seconds is not None, "duration estimated from distance"
    assert summary.distance is not None, "distance must be set from GPS coords"
    assert summary.distance > 0
    assert summary.elevation_gain == 150
    assert summary.activity_type_key == "run"
    print(
        f"extract_gpx_summary no-timestamps: DONE "
        f"(distance={summary.distance} m, "
        f"duration={summary.hours}h{summary.minutes}m{summary.seconds}s, "
        f"ele_gain={summary.elevation_gain} m)"
    )


@pytest.mark.mytral
def test_extract_gps_points_returns_ordered_points():
    """Test extract_gps_points returns ordered GPS points from GPX."""
    # GIVEN
    gpx_data = b"""<?xml version="1.0"?>
<gpx version="1.1" xmlns="http://www.topografix.com/GPX/1/1">
  <trk><trkseg>
    <trkpt lat="50.0001" lon="14.1001" />
    <trkpt lat="50.0002" lon="14.1002" />
    <trkpt lat="50.0003" lon="14.1003" />
  </trkseg></trk>
</gpx>"""

    # WHEN
    points = extract_gps_points(gpx_data=gpx_data)

    # THEN
    assert len(points) == 3
    assert points[0] == (50.0001, 14.1001)
    assert points[2] == (50.0003, 14.1003)
    print("extract_gps_points returns ordered points: DONE")


@pytest.mark.mytral
def test_extract_gps_points_rejects_invalid_coordinates():
    """Test extract_gps_points rejects invalid latitude values."""
    # GIVEN
    gpx_data = b"""<?xml version="1.0"?>
<gpx version="1.1" xmlns="http://www.topografix.com/GPX/1/1">
  <trk><trkseg>
    <trkpt lat="120.0" lon="14.0" />
  </trkseg></trk>
</gpx>"""

    # WHEN / THEN
    with pytest.raises(ValueError):
        extract_gps_points(gpx_data=gpx_data)
    print("extract_gps_points rejects invalid coordinates: DONE")


@pytest.mark.mytral
def test_encode_gps_polylines_creates_summary_and_bbox():
    """Test polyline encoding produces summary polyline and map bounds."""
    # GIVEN
    points = []
    for idx in range(200):
        points.append((50.0 + idx * 0.0001, 14.0 + idx * 0.0001))

    # WHEN
    summary_polyline, summary_bbox, full_polyline = encode_gps_polylines(points=points)
    decoded_summary = decode_polyline(summary_polyline)

    # THEN
    assert summary_polyline
    assert len(decoded_summary) <= 150
    assert summary_bbox[0] <= summary_bbox[2]
    assert summary_bbox[1] <= summary_bbox[3]
    assert full_polyline is not None
    print("encode_gps_polylines creates summary and bbox: DONE")


@pytest.mark.mytral
def test_encode_gps_polylines_preserves_shape_for_large_real_world_track():
    """Test summary polyline keeps the overall shape for a long GPX track."""
    # GIVEN
    gpx_path = _given.TEST_DATA_DIR / "import" / "gpx" / "ride-eda-122km-6h-spain.gpx"
    gpx_data = gpx_path.read_bytes()
    points = extract_gps_points(gpx_data=gpx_data)

    # WHEN
    summary_polyline, _, _ = encode_gps_polylines(points=points)
    summary_points = decode_polyline(summary_polyline)
    original_length_m = _polyline_length_meters(points)
    summary_length_m = _polyline_length_meters(summary_points)

    # THEN
    assert len(summary_points) <= 150
    assert summary_length_m / original_length_m >= 0.88
    print("encode_gps_polylines keeps shape for large track: DONE")


@pytest.mark.mytral
def test_extract_elevation_profile_returns_distance_elevation_points():
    """Test extraction of elevation profile data from GPX."""
    # GIVEN
    gpx_data = b"""<?xml version="1.0"?>
<gpx version="1.1" xmlns="http://www.topografix.com/GPX/1/1">
  <trk><trkseg>
    <trkpt lat="50.0000" lon="14.0000"><ele>200.0</ele></trkpt>
    <trkpt lat="50.0005" lon="14.0000"><ele>210.0</ele></trkpt>
    <trkpt lat="50.0010" lon="14.0000"><ele>205.0</ele></trkpt>
  </trkseg></trk>
</gpx>"""

    # WHEN
    profile = extract_elevation_profile(gpx_data=gpx_data)

    # THEN
    assert len(profile) == 3
    assert profile[0][0] == 0.0
    assert profile[0][1] == 200.0
    assert profile[1][0] > profile[0][0]
    assert profile[2][1] == 205.0
    print("extract_elevation_profile returns profile points: DONE")


@pytest.mark.mytral
def test_extract_fit_summary_distance_from_speed_integration():
    """Test that distance is derived from speed records when session lacks
    total_distance.
    """
    # GIVEN
    # ride-200km.fit has no total_distance in session message; distance must be
    # calculated by integrating speed data from record messages
    fit_path = _given.TEST_DATA_FIT_DIR / "ride-200km.fit"
    fit_data = fit_path.read_bytes()

    # WHEN
    summary = extract_fit_summary(fit_data)

    # THEN
    assert summary.activity_type_key == "ride"
    assert summary.distance is not None, "distance should be derived from speed records"
    assert 195_000 <= summary.distance <= 210_000, (
        f"expected ~201 km, got {summary.distance / 1000:.1f} km"
    )
    assert summary.avg_speed is not None, (
        "avg_speed should be derived from distance/time"
    )
    assert 20.0 <= summary.avg_speed <= 35.0, (
        f"expected reasonable avg speed, got {summary.avg_speed} km/h"
    )
    print(
        f"distance fallback from speed: {summary.distance / 1000:.1f} km,"
        f" avg_speed: {summary.avg_speed} km/h: DONE"
    )
