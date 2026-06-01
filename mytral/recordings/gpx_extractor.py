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
"""GPX file activity-level summary extractor."""

import datetime
import math
import statistics

import defusedxml.ElementTree

from mytral import commons
from mytral.recordings.models import RecordingSummary

# GPX namespace
_NS_GPX = "http://www.topografix.com/GPX/1/1"
_SUMMARY_POINT_LIMIT = 150
_FULL_POLYLINE_POINT_LIMIT = 30000
_PROFILE_POINT_LIMIT = 600
GPX_POLYLINE_METHOD_FAST = "sample"
GPX_POLYLINE_METHOD_LEGACY = "current"
GPX_POLYLINE_METHOD = GPX_POLYLINE_METHOD_FAST

try:
    import polyline as polyline_module
except ImportError:  # pragma: no cover - dependency is expected in runtime
    polyline_module = None

try:
    import rdp as rdp_module
except ImportError:  # pragma: no cover - dependency is expected in runtime
    rdp_module = None


def _parse_gpx_root(gpx_data: bytes):
    """Parse GPX bytes and return XML root element.

    Parameters
    ----------
    gpx_data : bytes
        Raw GPX file bytes.

    Returns
    -------
    defusedxml.ElementTree.Element
        Root XML element.

    Raises
    ------
    ValueError
        If GPX payload cannot be parsed as XML.
    """
    try:
        cleaned = gpx_data.lstrip(b"\xef\xbb\xbf")
        return defusedxml.ElementTree.fromstring(cleaned)
    except Exception as exc:
        raise ValueError(f"Invalid GPX XML payload: {exc}") from exc


def _extract_namespace(root) -> str:
    """Extract namespace prefix from GPX root tag."""
    if "}" in root.tag:
        return root.tag.split("}")[0] + "}"
    return ""


def _extract_track_samples(
    gpx_data: bytes,
) -> list[tuple[float, float, float | None]]:
    """Extract ordered latitude/longitude/elevation samples from GPX trackpoints."""
    root = _parse_gpx_root(gpx_data=gpx_data)
    ns = _extract_namespace(root=root)

    samples: list[tuple[float, float, float | None]] = []
    for trkpt in root.iter(f"{ns}trkpt"):
        lat_raw = trkpt.attrib.get("lat")
        lon_raw = trkpt.attrib.get("lon")
        if lat_raw is None or lon_raw is None:
            raise ValueError("GPX trackpoint is missing latitude or longitude.")

        try:
            lat = float(lat_raw)
            lon = float(lon_raw)
        except ValueError as exc:
            raise ValueError("GPX trackpoint has invalid latitude/longitude.") from exc

        if not (-90 <= lat <= 90):
            raise ValueError(f"Invalid latitude value in GPX: {lat}.")
        if not (-180 <= lon <= 180):
            raise ValueError(f"Invalid longitude value in GPX: {lon}.")

        ele_val: float | None = None
        ele_el = trkpt.find(f"{ns}ele")
        if ele_el is not None and ele_el.text:
            try:
                ele_val = float(ele_el.text)
            except ValueError:
                ele_val = None

        samples.append((lat, lon, ele_val))

    if not samples:
        raise ValueError("GPX file contains no valid trackpoints.")
    return samples


def extract_gps_points(gpx_data: bytes) -> list[tuple[float, float]]:
    """Extract ordered latitude/longitude pairs from GPX trackpoints.

    Parameters
    ----------
    gpx_data : bytes
        Raw GPX file content.

    Returns
    -------
    list[tuple[float, float]]
        Ordered list of ``(latitude, longitude)`` pairs.

    Raises
    ------
    ValueError
        If the GPX is malformed, contains invalid coordinates, or has no points.
    """
    samples = _extract_track_samples(gpx_data=gpx_data)
    return [(sample[0], sample[1]) for sample in samples]


def _haversine_m(lat1: float, lon1: float, lat2: float, lon2: float) -> float:
    """Calculate great-circle distance in meters between two WGS84 points."""
    radius_m = 6371000.0
    phi1 = math.radians(lat1)
    phi2 = math.radians(lat2)
    d_phi = math.radians(lat2 - lat1)
    d_lambda = math.radians(lon2 - lon1)
    a = (
        math.sin(d_phi / 2.0) ** 2
        + math.cos(phi1) * math.cos(phi2) * math.sin(d_lambda / 2.0) ** 2
    )
    c = 2 * math.atan2(math.sqrt(a), math.sqrt(1 - a))
    return radius_m * c


def extract_elevation_profile(gpx_data: bytes) -> list[tuple[float, float]]:
    """Extract distance/elevation samples for rendering a gradient profile.

    Parameters
    ----------
    gpx_data : bytes
        Raw GPX file bytes.

    Returns
    -------
    list[tuple[float, float]]
        Ordered list of ``(distance_m, elevation_m)`` samples.
        Empty list is returned when no elevation values are present in GPX.
    """
    samples = _extract_track_samples(gpx_data=gpx_data)
    if not samples:
        return []

    profile: list[tuple[float, float]] = []
    total_distance_m = 0.0
    prev_lat, prev_lon, _ = samples[0]
    first_elevation = samples[0][2]
    if first_elevation is not None:
        profile.append((0.0, float(first_elevation)))

    for sample in samples[1:]:
        lat, lon, elevation = sample
        total_distance_m += _haversine_m(prev_lat, prev_lon, lat, lon)
        if elevation is not None:
            profile.append((float(total_distance_m), float(elevation)))
        prev_lat, prev_lon = lat, lon

    return profile


def _sample_points(
    points: list[tuple[float, float]], max_points: int
) -> list[tuple[float, float]]:
    """Downsample points while preserving order and endpoints."""
    if len(points) <= max_points:
        return list(points)

    sampled: list[tuple[float, float]] = []
    scale = (len(points) - 1) / (max_points - 1)
    for index in range(max_points):
        point_index = int(round(index * scale))
        sampled.append(points[point_index])
    return sampled


def simplify_elevation_profile(
    profile_points: list[tuple[float, float]],
    max_points: int = _PROFILE_POINT_LIMIT,
) -> list[tuple[float, float]]:
    """Downsample elevation profile points for rendering and storage."""
    return _sample_points(points=profile_points, max_points=max_points)


def _simplify_points_sample(
    points: list[tuple[float, float]], max_points: int
) -> list[tuple[float, float]]:
    """Simplify points with deterministic endpoint-preserving sampling."""
    return _sample_points(points=points, max_points=max_points)


def _simplify_points_current(
    points: list[tuple[float, float]], max_points: int
) -> list[tuple[float, float]]:
    """Simplify points for preview rendering."""
    if len(points) <= max_points:
        return list(points)

    if rdp_module is not None and hasattr(rdp_module, "rdp"):
        path = [[point[0], point[1], 0.0] for point in points]
        epsilon = 0.00001
        simplified: list[tuple[float, float]] = []
        for _ in range(18):
            simplified_raw = rdp_module.rdp(path, epsilon=epsilon)
            simplified = [
                (float(point[0]), float(point[1])) for point in simplified_raw
            ]
            if len(simplified) <= max_points:
                return simplified
            epsilon *= 1.8
        if simplified:
            return _sample_points(simplified, max_points=max_points)

    return _sample_points(points, max_points=max_points)


def _simplify_points(
    points: list[tuple[float, float]],
    max_points: int,
    *,
    method: str = GPX_POLYLINE_METHOD,
) -> list[tuple[float, float]]:
    """Simplify points for preview rendering with a selectable method."""
    if method == GPX_POLYLINE_METHOD_FAST:
        return _simplify_points_sample(points=points, max_points=max_points)
    if method == GPX_POLYLINE_METHOD_LEGACY:
        return _simplify_points_current(points=points, max_points=max_points)
    raise ValueError(f"Unsupported GPX polyline method: {method}")


def _compute_bbox(
    points: list[tuple[float, float]],
) -> tuple[float, float, float, float]:
    """Compute a bounding box from GPS points."""
    latitudes = [point[0] for point in points]
    longitudes = [point[1] for point in points]
    return (
        min(latitudes),
        min(longitudes),
        max(latitudes),
        max(longitudes),
    )


def encode_gps_polylines(
    points: list[tuple[float, float]],
    *,
    polyline_method: str = GPX_POLYLINE_METHOD,
) -> tuple[str, tuple[float, float, float, float], str | None]:
    """Encode summary/full GPX polylines and compute bounding box.

    Parameters
    ----------
    points : list[tuple[float, float]]
        Ordered list of GPS points.

    Returns
    -------
    tuple[str, tuple[float, float, float, float], str | None]
        ``(summary_polyline, summary_bbox, full_polyline)``
    """
    if polyline_module is None:
        raise RuntimeError("polyline dependency is missing.")

    summary_points = _simplify_points(
        points,
        max_points=_SUMMARY_POINT_LIMIT,
        method=polyline_method,
    )
    summary_polyline = polyline_module.encode(summary_points, precision=5)
    summary_bbox = _compute_bbox(points=points)
    full_polyline = None
    if len(points) <= _FULL_POLYLINE_POINT_LIMIT:
        full_polyline = polyline_module.encode(points, precision=5)

    return summary_polyline, summary_bbox, full_polyline


def decode_polyline(polyline_text: str) -> list[tuple[float, float]]:
    """Decode an encoded polyline to ordered GPS points."""
    if not polyline_text:
        return []
    if polyline_module is None:
        raise RuntimeError("polyline dependency is missing.")
    decoded = polyline_module.decode(polyline_text, precision=5)
    return [(float(point[0]), float(point[1])) for point in decoded]


def extract_gpx_summary(gpx_data: bytes) -> RecordingSummary:
    """Parse a GPX file and derive an activity-level summary.

    Parameters
    ----------
    gpx_data : bytes
        Raw GPX file content.

    Returns
    -------
    RecordingSummary
        Summary with activity_type_key, duration, HR and other fields derived from the
        GPX track.  All fields remain None when parsing fails.
    """
    _NS_TPX = "http://www.garmin.com/xmlschemas/TrackPointExtension/v1"

    summary = RecordingSummary()

    try:
        cleaned = gpx_data.lstrip(b"\xef\xbb\xbf")
        root = defusedxml.ElementTree.fromstring(cleaned)
    except Exception:
        return summary

    tag = root.tag
    ns = ""
    if "}" in tag:
        ns = tag.split("}")[0] + "}"

    # activity name from metadata/name
    meta_el = root.find(f"{ns}metadata")
    if meta_el is not None:
        name_el = meta_el.find(f"{ns}name")
        if name_el is not None and name_el.text:
            summary.name_hint = name_el.text.strip()

    # collect all track points
    hr_values: list[int] = []
    timestamps: list[datetime.datetime] = []
    altitudes: list[float] = []
    prev_alt: float | None = None
    elevation_gain_m = 0.0
    prev_lat: float | None = None
    prev_lon: float | None = None
    total_distance_m = 0.0

    for trkpt in root.iter(f"{ns}trkpt"):
        time_el = trkpt.find(f"{ns}time")
        if time_el is not None and time_el.text:
            try:
                dt = datetime.datetime.fromisoformat(
                    time_el.text.replace("Z", "+00:00")
                )
                timestamps.append(dt)
            except ValueError:
                pass

        ele_el = trkpt.find(f"{ns}ele")
        if ele_el is not None and ele_el.text:
            try:
                alt = float(ele_el.text)
                altitudes.append(alt)
                if prev_alt is not None and alt > prev_alt:
                    elevation_gain_m += alt - prev_alt
                prev_alt = alt
            except ValueError:
                pass

        ext_el = trkpt.find(f"{ns}extensions")
        if ext_el is not None:
            hr_el = ext_el.find(f".//{{{_NS_TPX}}}hr")
            if hr_el is not None and hr_el.text:
                try:
                    hr_values.append(int(hr_el.text))
                except ValueError:
                    pass

        # accumulate haversine distance from consecutive GPS coordinates
        lat_raw = trkpt.attrib.get("lat")
        lon_raw = trkpt.attrib.get("lon")
        if lat_raw is not None and lon_raw is not None:
            try:
                lat = float(lat_raw)
                lon = float(lon_raw)
                if prev_lat is not None and prev_lon is not None:
                    total_distance_m += _haversine_m(prev_lat, prev_lon, lat, lon)
                prev_lat, prev_lon = lat, lon
            except ValueError:
                pass

    # fields that don't depend on timestamps — always populate
    if hr_values:
        summary.avg_hr = int(statistics.mean(hr_values))
        summary.max_hr = max(hr_values)
    if elevation_gain_m > 0:
        summary.elevation_gain = int(elevation_gain_m)
    if total_distance_m > 0:
        summary.distance = int(total_distance_m)
    summary.activity_type_key = commons.AT_RUN

    if not timestamps:
        # estimate duration from distance using 7 km/h pace when timestamps are missing
        if total_distance_m > 0 and not any(
            (summary.hours, summary.minutes, summary.seconds)
        ):
            estimated_seconds = int(total_distance_m * 3600 / 7000)
            summary.hours = estimated_seconds // 3600
            summary.minutes = (estimated_seconds % 3600) // 60
            summary.seconds = estimated_seconds % 60
        return summary

    # when
    summary.when = timestamps[0].replace(tzinfo=None)

    # duration
    if len(timestamps) > 1:
        delta = (timestamps[-1] - timestamps[0]).total_seconds()
        total_s = int(abs(delta))
        summary.hours = total_s // 3600
        summary.minutes = (total_s % 3600) // 60
        summary.seconds = total_s % 60

    return summary
