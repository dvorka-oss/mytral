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
"""TCX file activity-level summary extractor."""

import datetime
import math
import statistics

import defusedxml.ElementTree

from mytral import commons
from mytral.recordings.models import RecordingSummary

_NS_TCX = "http://www.garmin.com/xmlschemas/TrainingCenterDatabase/v2"
_NS_TPX = "http://www.garmin.com/xmlschemas/ActivityExtension/v2"


def _parse_tcx_root(tcx_data: bytes):
    """Parse TCX bytes and return XML root element."""
    try:
        cleaned = tcx_data.lstrip(b"\xef\xbb\xbf")
        # XML declaration must be at byte 0 for Python's XML parser;
        # strip leading ASCII whitespace that some exporters emit.
        cleaned = cleaned.lstrip()
        return defusedxml.ElementTree.fromstring(cleaned)
    except Exception as exc:
        raise ValueError(f"Invalid TCX XML payload: {exc}") from exc


def _extract_namespace(root) -> str:
    if "}" in root.tag:
        return root.tag.split("}")[0] + "}"
    return ""


def _parse_iso_datetime(value: str) -> datetime.datetime | None:
    if not value:
        return None
    try:
        return datetime.datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError:
        return None


def _safe_float(value: str | None) -> float | None:
    if value is None:
        return None
    try:
        return float(value)
    except ValueError:
        return None


def _safe_int(value: str | None) -> int | None:
    if value is None:
        return None
    try:
        return int(float(value))
    except ValueError:
        return None


def _sport_to_activity_type(sport: str) -> str:
    normalized = "".join(ch for ch in sport.lower() if ch.isalnum())
    sport_map = {
        "biking": commons.AT_RIDE,
        "bicycle": commons.AT_RIDE,
        "cycling": commons.AT_RIDE,
        "mountainbiking": commons.AT_RIDE_MOUNTAIN,
        "running": commons.AT_RUN,
        "trailrunning": commons.AT_RUN,
        "walking": commons.AT_WALK,
        "hiking": commons.AT_HIKE,
        "rowing": commons.AT_ROW,
        "ergrowing": commons.AT_ROW_ERG,
        "paddleboarding": commons.AT_PADDLE,
        "multisport": commons.AT_MULTISPORT,
    }
    return sport_map.get(normalized, commons.AT_WORKOUT)


def _haversine_m(lat1: float, lon1: float, lat2: float, lon2: float) -> float:
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


def parse_tcx(tcx_data: bytes) -> tuple[int, int]:
    """Return track and trackpoint counts from a TCX payload."""
    root = _parse_tcx_root(tcx_data)
    ns = _extract_namespace(root)
    track_count = 0
    track_point_count = 0

    for track in root.iter(f"{ns}Track"):
        track_count += 1
        for trackpoint in track.iter(f"{ns}Trackpoint"):
            lat = trackpoint.find(f"{ns}Position/{ns}LatitudeDegrees")
            lon = trackpoint.find(f"{ns}Position/{ns}LongitudeDegrees")
            if lat is not None and lon is not None:
                track_point_count += 1

    return track_count, track_point_count


def extract_gps_points(tcx_data: bytes) -> list[tuple[float, float]]:
    """Extract ordered latitude/longitude pairs from TCX trackpoints."""
    root = _parse_tcx_root(tcx_data)
    ns = _extract_namespace(root)
    points: list[tuple[float, float]] = []

    for trackpoint in root.iter(f"{ns}Trackpoint"):
        lat_el = trackpoint.find(f"{ns}Position/{ns}LatitudeDegrees")
        lon_el = trackpoint.find(f"{ns}Position/{ns}LongitudeDegrees")
        if lat_el is None or lon_el is None or not lat_el.text or not lon_el.text:
            continue
        try:
            points.append((float(lat_el.text), float(lon_el.text)))
        except ValueError as exc:
            raise ValueError("TCX trackpoint has invalid latitude/longitude.") from exc

    return points


def extract_elevation_profile(tcx_data: bytes) -> list[tuple[float, float]]:
    """Extract distance/elevation samples for rendering a gradient profile."""
    root = _parse_tcx_root(tcx_data)
    ns = _extract_namespace(root)
    profile: list[tuple[float, float]] = []
    total_distance_m = 0.0
    prev_lat: float | None = None
    prev_lon: float | None = None

    for trackpoint in root.iter(f"{ns}Trackpoint"):
        lat_el = trackpoint.find(f"{ns}Position/{ns}LatitudeDegrees")
        lon_el = trackpoint.find(f"{ns}Position/{ns}LongitudeDegrees")
        ele_el = trackpoint.find(f"{ns}AltitudeMeters")
        if lat_el is None or lon_el is None or not lat_el.text or not lon_el.text:
            continue

        try:
            lat = float(lat_el.text)
            lon = float(lon_el.text)
        except ValueError:
            continue

        if prev_lat is not None and prev_lon is not None:
            total_distance_m += _haversine_m(prev_lat, prev_lon, lat, lon)

        if ele_el is not None and ele_el.text:
            ele = _safe_float(ele_el.text)
            if ele is not None:
                profile.append((float(total_distance_m), ele))

        prev_lat = lat
        prev_lon = lon

    return profile


def extract_all_from_tcx(
    tcx_data: bytes,
) -> tuple[int, int, list[tuple[float, float]], list[tuple[float, float]]]:
    """Parse TCX once and extract track counts, GPS points, and elevation profile.

    Avoids the triple-parse overhead of calling ``parse_tcx``,
    ``extract_gps_points``, and ``extract_elevation_profile`` separately.

    Parameters
    ----------
    tcx_data : bytes
        Raw TCX file content.

    Returns
    -------
    tuple[int, int, list[tuple[float, float]], list[tuple[float, float]]]
        ``(track_count, track_point_count, gps_points, elevation_profile)``
    """
    root = _parse_tcx_root(tcx_data)
    ns = _extract_namespace(root)

    track_count = 0
    track_point_count = 0
    gps_points: list[tuple[float, float]] = []
    profile: list[tuple[float, float]] = []

    total_distance_m = 0.0
    prev_lat: float | None = None
    prev_lon: float | None = None

    for track in root.iter(f"{ns}Track"):
        track_count += 1
        for trackpoint in track.iter(f"{ns}Trackpoint"):
            lat_el = trackpoint.find(f"{ns}Position/{ns}LatitudeDegrees")
            lon_el = trackpoint.find(f"{ns}Position/{ns}LongitudeDegrees")
            if lat_el is None or lon_el is None or not lat_el.text or not lon_el.text:
                continue

            try:
                lat = float(lat_el.text)
                lon = float(lon_el.text)
            except ValueError:
                continue

            gps_points.append((lat, lon))
            track_point_count += 1

            if prev_lat is not None and prev_lon is not None:
                total_distance_m += _haversine_m(prev_lat, prev_lon, lat, lon)

            ele_el = trackpoint.find(f"{ns}AltitudeMeters")
            if ele_el is not None and ele_el.text:
                ele = _safe_float(ele_el.text)
                if ele is not None:
                    profile.append((float(total_distance_m), ele))

            prev_lat = lat
            prev_lon = lon

    return track_count, track_point_count, gps_points, profile


def extract_tcx_summary(tcx_data: bytes) -> RecordingSummary:
    """Parse a TCX file and derive an activity-level summary."""
    summary = RecordingSummary()

    try:
        root = _parse_tcx_root(tcx_data)
    except ValueError:
        return summary

    ns = _extract_namespace(root)
    activity_el = root.find(f"{ns}Activities/{ns}Activity")
    if activity_el is None:
        return summary

    summary.activity_type_key = _sport_to_activity_type(
        activity_el.attrib.get("Sport", "")
    )

    name_el = activity_el.find(f"{ns}Name")
    if name_el is not None and name_el.text:
        summary.name_hint = name_el.text.strip()

    id_el = activity_el.find(f"{ns}Id")
    summary.when = _parse_iso_datetime(id_el.text.strip() if id_el is not None else "")

    hr_values: list[int] = []
    cadence_values: list[int] = []
    timestamps: list[datetime.datetime] = []
    prev_alt: float | None = None
    elevation_gain_m = 0.0
    total_distance_m = 0.0
    max_speed_kmh = 0.0
    kcal_total = 0
    total_time_s = 0.0

    for lap in activity_el.iter(f"{ns}Lap"):
        total_time_el = lap.find(f"{ns}TotalTimeSeconds")
        total_time = _safe_float(
            total_time_el.text if total_time_el is not None else None
        )
        if total_time is not None and total_time > 0:
            total_time_s += total_time

        distance_el = lap.find(f"{ns}DistanceMeters")
        distance = _safe_float(distance_el.text if distance_el is not None else None)
        if distance is not None and distance > 0:
            total_distance_m += distance

        calories_el = lap.find(f"{ns}Calories")
        calories = _safe_int(calories_el.text if calories_el is not None else None)
        if calories is not None and calories > 0:
            kcal_total += calories

        max_speed_el = lap.find(f"{ns}MaximumSpeed")
        max_speed = _safe_float(max_speed_el.text if max_speed_el is not None else None)
        if max_speed is not None and max_speed > 0:
            max_speed_kmh = max(max_speed_kmh, max_speed * 3.6)

        avg_hr_el = lap.find(f"{ns}AverageHeartRateBpm/{ns}Value")
        avg_hr = _safe_int(avg_hr_el.text if avg_hr_el is not None else None)
        if avg_hr is not None and summary.avg_hr is None:
            summary.avg_hr = avg_hr

        max_hr_el = lap.find(f"{ns}MaximumHeartRateBpm/{ns}Value")
        max_hr = _safe_int(max_hr_el.text if max_hr_el is not None else None)
        if max_hr is not None and summary.max_hr is None:
            summary.max_hr = max_hr

        cadence_el = lap.find(f"{ns}Cadence")
        cadence = _safe_int(cadence_el.text if cadence_el is not None else None)
        if cadence is not None:
            cadence_values.append(cadence)

        for trackpoint in lap.iter(f"{ns}Trackpoint"):
            time_el = trackpoint.find(f"{ns}Time")
            timestamp = _parse_iso_datetime(
                time_el.text.strip() if time_el is not None and time_el.text else ""
            )
            if timestamp is not None:
                timestamps.append(timestamp)

            hr_el = trackpoint.find(f"{ns}HeartRateBpm/{ns}Value")
            hr = _safe_int(hr_el.text if hr_el is not None else None)
            if hr is not None:
                hr_values.append(hr)

            altitude_el = trackpoint.find(f"{ns}AltitudeMeters")
            altitude = _safe_float(
                altitude_el.text if altitude_el is not None else None
            )
            if altitude is not None:
                if prev_alt is not None and altitude > prev_alt:
                    elevation_gain_m += altitude - prev_alt
                prev_alt = altitude

            cadence_el = trackpoint.find(f"{ns}Cadence")
            cadence = _safe_int(cadence_el.text if cadence_el is not None else None)
            if cadence is not None:
                cadence_values.append(cadence)

            speed_el = trackpoint.find(f".//{{{_NS_TPX}}}Speed")
            speed = _safe_float(speed_el.text if speed_el is not None else None)
            if speed is not None:
                max_speed_kmh = max(max_speed_kmh, speed * 3.6)

            distance_el = trackpoint.find(f"{ns}DistanceMeters")
            distance = _safe_float(
                distance_el.text if distance_el is not None else None
            )
            if distance is not None and distance > total_distance_m:
                total_distance_m = distance

    if hr_values:
        summary.avg_hr = int(statistics.mean(hr_values))
        summary.max_hr = (
            max(hr_values)
            if summary.max_hr is None
            else max(summary.max_hr, max(hr_values))
        )
    if cadence_values:
        summary.avg_cadence = int(statistics.mean(cadence_values))
        summary.max_cadence = max(cadence_values)
    if elevation_gain_m > 0:
        summary.elevation_gain = int(elevation_gain_m)
    if total_distance_m > 0 and summary.distance is None:
        summary.distance = int(total_distance_m)
    if kcal_total > 0:
        summary.kcal = kcal_total
    if max_speed_kmh > 0:
        summary.max_speed = max_speed_kmh
    if total_time_s > 0:
        total_seconds = int(total_time_s)
        summary.hours = total_seconds // 3600
        summary.minutes = (total_seconds % 3600) // 60
        summary.seconds = total_seconds % 60
    elif len(timestamps) > 1:
        delta = (timestamps[-1] - timestamps[0]).total_seconds()
        total_seconds = int(abs(delta))
        summary.hours = total_seconds // 3600
        summary.minutes = (total_seconds % 3600) // 60
        summary.seconds = total_seconds % 60

    if summary.when is None and timestamps:
        summary.when = timestamps[0].replace(tzinfo=None)

    if summary.distance and summary.hours is not None:
        total_seconds = (
            summary.hours * 3600 + (summary.minutes or 0) * 60 + (summary.seconds or 0)
        )
        if total_seconds > 0:
            summary.avg_speed = round(summary.distance / total_seconds * 3.6, 2)
    elif total_distance_m > 0 and total_time_s > 0:
        summary.avg_speed = round(total_distance_m / total_time_s * 3.6, 2)

    # fallback: guess activity type from pace when Sport is missing/unrecognized
    if summary.activity_type_key == commons.AT_WORKOUT and summary.avg_speed:
        summary.activity_type_key = commons.guess_activity_type_from_pace(
            summary.avg_speed
        )

    return summary
