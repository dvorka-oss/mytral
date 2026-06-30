# MyTraL: my training log
#
# Copyright (C) 2015-2026 Martin Dvorak <martin.dvorak@mindforger.com>
#
# This program is free software: you can redistribute it and/or modify
# it under the terms of the GNU Affero General Public License as published by
# the Free Software Foundation, either version 3 of the License, or
# (at your option) any later version.

"""GPX and FIT file parsing, track simplification and statistics.

Implements the same algorithms as GPXWorker.java in TopoLibrary:
  - GPX parsing via gpxpy
  - FIT binary parsing via fitdecode
  - Ramer-Douglas-Peucker track simplification
  - Track statistics (distance, elevation gain/loss, duration, pace)
  - Mean-bias elevation normalisation against SRTM reference
"""

import dataclasses
import io
import math
from typing import BinaryIO

import fitdecode
import gpxpy
import gpxpy.gpx

from mytral.gpx_terrain import coordinates


@dataclasses.dataclass
class TrackPoint:
    """A single point on a GPS track.

    Attributes
    ----------
    lat : float
        Latitude in decimal degrees.
    lon : float
        Longitude in decimal degrees.
    elevation : float
        Elevation in metres above sea level (may be 0 if unavailable).
    timestamp : float
        Unix timestamp in seconds (may be 0 if unavailable).
    heart_rate : int
        Heart rate in bpm (0 if unavailable).
    """

    lat: float
    lon: float
    elevation: float = 0.0
    timestamp: float = 0.0
    heart_rate: int = 0


@dataclasses.dataclass
class TrackSummary:
    """Aggregate statistics for a GPS track.

    Attributes
    ----------
    distance_m : float
        Total track distance in metres.
    elevation_up_m : float
        Total elevation gain in metres.
    elevation_down_m : float
        Total elevation loss in metres (positive value).
    duration_s : float
        Total elapsed time in seconds.
    min_elevation_m : float
        Lowest point in metres.
    max_elevation_m : float
        Highest point in metres.
    point_count : int
        Number of track points.
    """

    distance_m: float = 0.0
    elevation_up_m: float = 0.0
    elevation_down_m: float = 0.0
    duration_s: float = 0.0
    min_elevation_m: float = 0.0
    max_elevation_m: float = 0.0
    point_count: int = 0


def parse_gpx(source: str | bytes | BinaryIO) -> list[TrackPoint]:
    """Parse a GPX file and return a flat list of track points.

    Parameters
    ----------
    source : str | bytes | BinaryIO
        GPX content as a file path string, raw bytes, or an open binary stream.

    Returns
    -------
    list[TrackPoint]
        Ordered list of track points from all tracks and segments.
    """
    if isinstance(source, str):
        with open(source, "rb") as f:
            gpx = gpxpy.parse(f)
    elif isinstance(source, (bytes, bytearray)):
        gpx = gpxpy.parse(io.BytesIO(source))
    else:
        gpx = gpxpy.parse(source)

    points: list[TrackPoint] = []
    for track in gpx.tracks:
        for segment in track.segments:
            for pt in segment.points:
                ts = pt.time.timestamp() if pt.time else 0.0
                ele = float(pt.elevation) if pt.elevation is not None else 0.0
                hr = 0
                if pt.extensions:
                    # gpxpy stores Garmin extensions as XML elements
                    for ext in pt.extensions:
                        for child in ext:
                            if child.tag.endswith("hr") or child.tag.endswith(
                                "heartRate"
                            ):
                                try:
                                    hr = int(child.text or 0)
                                except ValueError:
                                    pass
                points.append(
                    TrackPoint(
                        lat=float(pt.latitude),
                        lon=float(pt.longitude),
                        elevation=ele,
                        timestamp=ts,
                        heart_rate=hr,
                    )
                )
    return points


def parse_fit(source: str | bytes | BinaryIO) -> list[TrackPoint]:
    """Parse a Garmin FIT binary file and return a flat list of track points.

    Matches GPXWorker.loadFitTracks() from TopoLibrary.
    FIT position values are in semicircles; converted to degrees by
    multiplying by (180 / 2^31).

    Parameters
    ----------
    source : str | bytes | BinaryIO
        FIT content as a file path string, raw bytes, or an open binary stream.

    Returns
    -------
    list[TrackPoint]
        Ordered list of track points.
    """
    _SEMICIRCLES_TO_DEG = 180.0 / (2**31)

    if isinstance(source, str):
        ctx = open(source, "rb")
    elif isinstance(source, (bytes, bytearray)):
        ctx = io.BytesIO(source)
    else:
        ctx = source

    points: list[TrackPoint] = []
    with fitdecode.FitReader(ctx) as reader:
        for frame in reader:
            if not isinstance(frame, fitdecode.FitDataMessage):
                continue
            if frame.name != "record":
                continue
            lat_semi = frame.get_value("position_lat")
            lon_semi = frame.get_value("position_long")
            if lat_semi is None or lon_semi is None:
                continue
            lat = lat_semi * _SEMICIRCLES_TO_DEG
            lon = lon_semi * _SEMICIRCLES_TO_DEG
            alt = frame.get_value("altitude") or 0.0
            ts_raw = frame.get_value("timestamp")
            ts = ts_raw.timestamp() if ts_raw else 0.0
            hr = int(frame.get_value("heart_rate") or 0)
            points.append(
                TrackPoint(
                    lat=lat, lon=lon, elevation=float(alt), timestamp=ts, heart_rate=hr
                )
            )
    return points


def _perp_distance_m(pt: TrackPoint, start: TrackPoint, end: TrackPoint) -> float:
    """Perpendicular distance in metres from pt to the line start→end.

    Accounts for Earth curvature by converting degree differences to metres
    before computing the cross-product distance. Matches the Java implementation
    in GPXWorker.ramerDouglasPeucker().
    """
    lat_m = coordinates.METERS_PER_DEGREE_LAT
    lon_m = coordinates.meters_per_degree_lon((start.lat + end.lat) / 2)

    dx = (end.lon - start.lon) * lon_m
    dy = (end.lat - start.lat) * lat_m
    px = (pt.lon - start.lon) * lon_m
    py = (pt.lat - start.lat) * lat_m

    line_len = math.hypot(dx, dy)
    if line_len == 0.0:
        return math.hypot(px, py)
    # perpendicular distance via cross product
    return abs(dx * py - dy * px) / line_len


def _rdp(points: list[TrackPoint], epsilon_m: float) -> list[TrackPoint]:
    """Recursive Ramer-Douglas-Peucker simplification."""
    if len(points) < 3:
        return list(points)
    max_dist = 0.0
    max_idx = 0
    for i in range(1, len(points) - 1):
        d = _perp_distance_m(points[i], points[0], points[-1])
        if d > max_dist:
            max_dist = d
            max_idx = i
    if max_dist > epsilon_m:
        left = _rdp(points[: max_idx + 1], epsilon_m)
        right = _rdp(points[max_idx:], epsilon_m)
        return left[:-1] + right
    return [points[0], points[-1]]


def simplify_track(
    points: list[TrackPoint], epsilon_m: float = 2.0
) -> list[TrackPoint]:
    """Reduce track point count using Ramer-Douglas-Peucker.

    Matches GPXWorker.reduceTrackSegments(track, epsilon) in TopoLibrary.

    Parameters
    ----------
    points : list[TrackPoint]
        Input track points.
    epsilon_m : float
        Maximum allowed perpendicular deviation in metres. Typical: 2–10 m.

    Returns
    -------
    list[TrackPoint]
        Simplified track points.
    """
    if len(points) < 3:
        return list(points)
    return _rdp(points, epsilon_m)


def track_summary(points: list[TrackPoint]) -> TrackSummary:
    """Compute aggregate statistics for a track.

    Matches GPXWorker.getTrackSummary() in TopoLibrary.

    Parameters
    ----------
    points : list[TrackPoint]
        Track points (typically after simplification).

    Returns
    -------
    TrackSummary
        Computed statistics.
    """
    if not points:
        return TrackSummary()

    total_dist = 0.0
    ele_up = 0.0
    ele_down = 0.0
    min_ele = points[0].elevation
    max_ele = points[0].elevation
    duration = 0.0

    for i in range(1, len(points)):
        prev = points[i - 1]
        curr = points[i]
        total_dist += coordinates.haversine_m(prev.lat, prev.lon, curr.lat, curr.lon)
        delta = curr.elevation - prev.elevation
        if delta > 0:
            ele_up += delta
        else:
            ele_down += abs(delta)
        min_ele = min(min_ele, curr.elevation)
        max_ele = max(max_ele, curr.elevation)
        if prev.timestamp and curr.timestamp:
            duration += curr.timestamp - prev.timestamp

    return TrackSummary(
        distance_m=total_dist,
        elevation_up_m=ele_up,
        elevation_down_m=ele_down,
        duration_s=duration,
        min_elevation_m=min_ele,
        max_elevation_m=max_ele,
        point_count=len(points),
    )


def normalize_elevation(
    points: list[TrackPoint], srtm_elevations: list[float]
) -> list[TrackPoint]:
    """Apply mean-bias elevation correction using SRTM as reference.

    Shifts all GPS elevation values by a constant offset so that their
    mean matches the mean of the SRTM reference elevations, while
    preserving the relative shape of the GPS elevation profile.

    Matches GPXWorker.normalizeElevationData() in TopoLibrary.

    Parameters
    ----------
    points : list[TrackPoint]
        Original track points with GPS elevations.
    srtm_elevations : list[float]
        SRTM elevation at each corresponding track point.

    Returns
    -------
    list[TrackPoint]
        New list of TrackPoints with corrected elevation values.
    """
    if not points or not srtm_elevations:
        return list(points)
    n = min(len(points), len(srtm_elevations))
    gps_mean = sum(p.elevation for p in points[:n]) / n
    srtm_mean = sum(srtm_elevations[:n]) / n
    offset = srtm_mean - gps_mean
    return [dataclasses.replace(p, elevation=p.elevation + offset) for p in points]


def points_to_geojson(
    points: list[TrackPoint],
    name: str = "",
    scene_params: dict | None = None,
    tile_bboxes: list[dict] | None = None,
    labels: dict[str, dict] | None = None,
) -> dict:
    """Serialise track points to a GeoJSON Feature with extended coordinates.

    Coordinate format matches CubeTrek's TrackGeojson.java:
    [longitude, latitude, elevation_m, unix_timestamp_s, distance_m, heart_rate]

    Parameters
    ----------
    points : list[TrackPoint]
        Track points.
    name : str
        Optional track name for the GeoJSON properties.
    scene_params : dict | None
        Optional scene coordinate parameters embedded under ``properties.scene``.
        When provided, terrain3d.js uses these to correctly position the track
        tube inside the GLTF scene coordinate space.
    tile_bboxes : list[dict] | None
        Optional list of per-tile bounding boxes matching CubeTrek's format
        (n_Bound, s_Bound, w_Bound, e_Bound, widthLatDegree, widthLonDegree,
        tile_zoom, tile_x, tile_y). Used by texture-baking to draw GPX path
        onto terrain mesh emissive textures.

    Returns
    -------
    dict
        GeoJSON Feature dict ready for json.dumps().
    """
    cumulative_dist = 0.0
    coords: list[list[float]] = []
    for i, pt in enumerate(points):
        if i > 0:
            prev = points[i - 1]
            cumulative_dist += coordinates.haversine_m(
                prev.lat, prev.lon, pt.lat, pt.lon
            )
        coords.append(
            [pt.lon, pt.lat, pt.elevation, pt.timestamp, cumulative_dist, pt.heart_rate]
        )

    props: dict = {"name": name}
    if scene_params:
        props["scene"] = scene_params
    if tile_bboxes:
        props["tileBBoxes"] = tile_bboxes
    if labels:
        props["labels"] = labels

    return {
        "type": "Feature",
        "geometry": {"type": "LineString", "coordinates": coords},
        "properties": props,
    }
