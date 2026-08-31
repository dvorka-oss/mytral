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

"""Build a full recording from a Polar Flow GDPR export training session.

The export stores per-second sample channels (heart rate, speed, cadence, altitude,
distance, power) plus a GPS way-point track. This module extracts them once into an
aligned 1 Hz timeline and renders two artifacts directly - without any XML round
trip - so the import stays fast:

- a TCX file (the downloadable source recording, and the source the GPS map is
  precomputed from after import), and
- canonical recording Parquet (drives the charts).
"""

import dataclasses
import datetime
import xml.sax.saxutils

from mytral.integrations import icommons
from mytral.recordings import parquet_converter

# Polar export sample channel names (1 Hz ``{type, intervalMillis, values}`` blocks)
_CH_HEART_RATE = "HEART_RATE"
_CH_SPEED = "SPEED"  # metres/second
_CH_CADENCE = "CADENCE"
_CH_ALTITUDE = "ALTITUDE"
_CH_DISTANCE = "DISTANCE"  # cumulative metres
_CH_POWER = "LEFT_CRANK_CURRENT_POWER"  # watts

# channels that establish the per-second timeline
_TIMELINE_CHANNELS = (
    _CH_HEART_RATE,
    _CH_SPEED,
    _CH_CADENCE,
    _CH_ALTITUDE,
    _CH_DISTANCE,
    _CH_POWER,
)

_NS_TCX = "http://www.garmin.com/xmlschemas/TrainingCenterDatabase/v2"
_NS_TPX = "http://www.garmin.com/xmlschemas/ActivityExtension/v2"

# Polar sport name -> TCX Sport attribute (TCX only knows Running/Biking/Other)
_TCX_SPORT = {
    "running": "Running",
    "cycling": "Biking",
    "road_biking": "Biking",
    "mountain_biking": "Biking",
}


@dataclasses.dataclass
class _Timeline:
    """Aligned 1 Hz sample arrays for one exercise (parallel lists, ``None`` gaps)."""

    ts_unix_ms: list[int]
    hr: list[int | None]
    speed_kmh: list[float | None]
    speed_ms: list[float | None]
    cadence: list[int | None]
    altitude: list[float | None]
    lat: list[float | None]
    lon: list[float | None]
    power: list[float | None]
    distance: list[float | None]
    sport_name: str
    start: datetime.datetime


@dataclasses.dataclass
class RecordingArtifacts:
    """The TCX source recording and chart Parquet, built without any re-parse."""

    tcx_bytes: bytes
    parquet_bytes: bytes


def _num(value) -> float | None:
    """Return *value* as a float, or ``None`` for missing / ``NaN`` samples."""
    if value is None:
        return None
    try:
        number = float(value)
    except (TypeError, ValueError):
        return None
    # Polar encodes gaps as the string "NaN" or a float nan
    return None if number != number else number


def _exercise(session: dict) -> dict:
    """Return the single exercise dict, or the session itself as a fallback."""
    exercises = session.get("exercises")
    if isinstance(exercises, list) and exercises and isinstance(exercises[0], dict):
        return exercises[0]
    return session


def _sample_channels(exercise: dict) -> dict[str, list]:
    """Return ``{channel_type: values}`` for the exercise's 1 Hz sample blocks."""
    blocks = (exercise.get("samples") or {}).get("samples") or []
    channels: dict[str, list] = {}
    for block in blocks:
        if not isinstance(block, dict):
            continue
        channel_type = block.get("type")
        values = block.get("values")
        if channel_type in _TIMELINE_CHANNELS and isinstance(values, list):
            channels[channel_type] = values
    return channels


def _waypoints_by_second(exercise: dict) -> dict[int, dict]:
    """Map GPS way-points onto whole-second offsets by their ``elapsedMillis``."""
    route = (exercise.get("routes") or {}).get("route") or {}
    waypoints = route.get("wayPoints") or []
    by_second: dict[int, dict] = {}
    for waypoint in waypoints:
        if not isinstance(waypoint, dict):
            continue
        elapsed = waypoint.get("elapsedMillis")
        if elapsed is None:
            continue
        by_second[round(elapsed / 1000)] = waypoint
    return by_second


def _start_utc(session: dict, exercise: dict) -> datetime.datetime | None:
    """Parse the exercise start time (local) into an aware UTC datetime."""
    raw = exercise.get("startTime") or session.get("startTime") or ""
    text = str(raw)[:19]
    try:
        local = datetime.datetime.fromisoformat(text)
    except ValueError:
        return None
    offset_min = session.get("timezoneOffsetMinutes")
    if offset_min is None:
        offset_min = exercise.get("timezoneOffsetMinutes", 0)
    try:
        offset = datetime.timedelta(minutes=int(offset_min or 0))
    except (TypeError, ValueError):
        offset = datetime.timedelta()
    return (local - offset).replace(tzinfo=datetime.timezone.utc)


def _at(values: list, index: int) -> float | None:
    """Return the numeric sample at *index*, or ``None`` when absent / ``NaN``."""
    if index < len(values):
        return _num(values[index])
    return None


def _build_timeline(session: dict) -> _Timeline | None:
    """Extract a session's samples and GPS track into one aligned 1 Hz timeline.

    Returns ``None`` for a session with no per-second samples and no GPS track
    (e.g. a manual entry), so callers can skip recording import for it.
    """
    if not isinstance(session, dict):
        return None
    exercise = _exercise(session)
    channels = _sample_channels(exercise)
    waypoints = _waypoints_by_second(exercise)
    if not channels and not waypoints:
        return None
    start = _start_utc(session, exercise)
    if start is None:
        return None

    length = max(
        [len(values) for values in channels.values()]
        + [max(waypoints) + 1 if waypoints else 0]
    )
    if length <= 0:
        return None

    hr_v = channels.get(_CH_HEART_RATE, [])
    speed_v = channels.get(_CH_SPEED, [])
    cadence_v = channels.get(_CH_CADENCE, [])
    altitude_v = channels.get(_CH_ALTITUDE, [])
    distance_v = channels.get(_CH_DISTANCE, [])
    power_v = channels.get(_CH_POWER, [])

    base_ms = int(start.timestamp() * 1000)
    timeline = _Timeline(
        ts_unix_ms=[],
        hr=[],
        speed_kmh=[],
        speed_ms=[],
        cadence=[],
        altitude=[],
        lat=[],
        lon=[],
        power=[],
        distance=[],
        sport_name=icommons.polar_flow_sport_name(
            exercise.get("sport") or session.get("sport")
        ),
        start=start,
    )
    for i in range(length):
        timeline.ts_unix_ms.append(base_ms + i * 1000)
        hr = _at(hr_v, i)
        timeline.hr.append(int(hr) if hr is not None else None)
        speed = _at(speed_v, i)
        timeline.speed_ms.append(speed)
        timeline.speed_kmh.append(round(speed * 3.6, 2) if speed is not None else None)
        cadence = _at(cadence_v, i)
        timeline.cadence.append(int(cadence) if cadence is not None else None)
        altitude = _at(altitude_v, i)
        power = _at(power_v, i)
        timeline.power.append(power)
        timeline.distance.append(_at(distance_v, i))
        waypoint = waypoints.get(i)
        lat = lon = None
        if waypoint is not None:
            lat = _num(waypoint.get("latitude"))
            lon = _num(waypoint.get("longitude"))
            if altitude is None:
                altitude = _num(waypoint.get("altitude"))
        timeline.lat.append(lat)
        timeline.lon.append(lon)
        timeline.altitude.append(altitude)
    return timeline


def _trackpoint_xml(timeline: _Timeline, i: int) -> str | None:
    """Render one TCX ``<Trackpoint>`` from timeline index *i*, or ``None`` if empty."""
    when = datetime.datetime.fromtimestamp(
        timeline.ts_unix_ms[i] / 1000, tz=datetime.timezone.utc
    )
    parts = [f"<Time>{when.strftime('%Y-%m-%dT%H:%M:%SZ')}</Time>"]
    if timeline.lat[i] is not None and timeline.lon[i] is not None:
        parts.append(
            f"<Position><LatitudeDegrees>{timeline.lat[i]}</LatitudeDegrees>"
            f"<LongitudeDegrees>{timeline.lon[i]}</LongitudeDegrees></Position>"
        )
    if timeline.altitude[i] is not None:
        parts.append(f"<AltitudeMeters>{timeline.altitude[i]}</AltitudeMeters>")
    if timeline.distance[i] is not None:
        parts.append(f"<DistanceMeters>{timeline.distance[i]}</DistanceMeters>")
    if timeline.hr[i] is not None:
        parts.append(f"<HeartRateBpm><Value>{timeline.hr[i]}</Value></HeartRateBpm>")
    if timeline.cadence[i] is not None:
        parts.append(f"<Cadence>{timeline.cadence[i]}</Cadence>")
    extensions = []
    if timeline.speed_ms[i] is not None:
        extensions.append(f"<Speed>{timeline.speed_ms[i]}</Speed>")
    if timeline.power[i] is not None:
        extensions.append(f"<Watts>{timeline.power[i]}</Watts>")
    if extensions:
        parts.append(
            f'<Extensions><TPX xmlns="{_NS_TPX}">'
            f"{''.join(extensions)}</TPX></Extensions>"
        )
    if len(parts) == 1:
        return None
    return f"<Trackpoint>{''.join(parts)}</Trackpoint>"


def _timeline_to_tcx(timeline: _Timeline) -> bytes | None:
    """Render a timeline into TCX bytes (the downloadable source recording)."""
    trackpoints = [
        point
        for point in (
            _trackpoint_xml(timeline, i) for i in range(len(timeline.ts_unix_ms))
        )
        if point is not None
    ]
    if not trackpoints:
        return None
    sport = _TCX_SPORT.get(timeline.sport_name, "Other")
    started_at = timeline.start.strftime("%Y-%m-%dT%H:%M:%SZ")
    document = (
        '<?xml version="1.0" encoding="UTF-8"?>'
        f'<TrainingCenterDatabase xmlns="{xml.sax.saxutils.escape(_NS_TCX)}">'
        "<Activities>"
        f'<Activity Sport="{sport}">'
        f"<Id>{started_at}</Id>"
        f'<Lap StartTime="{started_at}">'
        "<Track>"
        f"{''.join(trackpoints)}"
        "</Track>"
        "</Lap>"
        "</Activity>"
        "</Activities>"
        "</TrainingCenterDatabase>"
    )
    return document.encode("utf-8")


def session_to_tcx(session: dict) -> bytes | None:
    """Render a Polar export training session into TCX bytes (source recording)."""
    timeline = _build_timeline(session)
    if timeline is None:
        return None
    return _timeline_to_tcx(timeline)


def build_recording(session: dict) -> RecordingArtifacts | None:
    """Build the TCX source recording and chart Parquet for a session in one pass.

    Returns ``None`` when the session has no per-second samples and no GPS track.
    The GPS map is not encoded here - the import precomputes it in a parallel phase
    from the stored TCX (``recording_maps.precompute_maps``) so the activity feed,
    which renders a mini-map per activity, never blocks encoding them on first view.
    """
    timeline = _build_timeline(session)
    if timeline is None:
        return None
    tcx_bytes = _timeline_to_tcx(timeline)
    if not tcx_bytes:
        return None
    parquet_bytes = parquet_converter.lists_to_parquet(
        ts_unix_ms=timeline.ts_unix_ms,
        hr=timeline.hr,
        speed=timeline.speed_kmh,
        cadence=timeline.cadence,
        altitude=timeline.altitude,
        lat=timeline.lat,
        lon=timeline.lon,
        power=timeline.power,
        source_format="tcx",
    )
    return RecordingArtifacts(tcx_bytes=tcx_bytes, parquet_bytes=parquet_bytes)
