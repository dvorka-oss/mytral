# MyTraL: my training log
#
# Copyright (C) 2015-2026 Martin Dvorak <martin.dvorak@mindforger.com>
#
# This program is free software: you can redistribute it and/or modify
# it under the terms of the GNU Affero General Public License as published by
# the Free Software Foundation, either version 3 of the License, or
# (at your option) any later version.

"""Track point extraction, simplification and statistics.

Track points are read from the canonical normalized recording Parquet (produced
by ``mytral.recordings.parquet_converter`` for GPX/FIT/TCX/HRM), so no
format-specific parser is duplicated here.

  - Ramer-Douglas-Peucker track simplification
  - Track statistics (distance, elevation gain/loss, duration, pace)
  - Mean-bias elevation normalisation against SRTM reference
"""

import dataclasses
import io
import math

import polars

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


def points_from_parquet(parquet_bytes: bytes) -> list[TrackPoint]:
    """Build track points from a normalized recording Parquet.

    Reads the canonical Parquet produced by
    ``mytral.recordings.parquet_converter`` (columns ``lat``, ``lon``,
    ``altitude``, ``hr``, ``ts_unix_ms``) and returns the GPS track points,
    dropping rows that have no latitude/longitude fix. This is the single
    parsing path shared with the rest of MyTraL — GPX, FIT and TCX recordings
    are all converted to this Parquet, so the 3D pipeline needs no format-
    specific parser of its own.

    Parameters
    ----------
    parquet_bytes : bytes
        Raw normalized-recording Parquet content.

    Returns
    -------
    list[TrackPoint]
        Ordered GPS track points.
    """
    df = polars.read_parquet(io.BytesIO(parquet_bytes))
    cols = set(df.columns)
    if "lat" not in cols or "lon" not in cols:
        return []

    points: list[TrackPoint] = []
    for row in df.iter_rows(named=True):
        lat = row.get("lat")
        lon = row.get("lon")
        if lat is None or lon is None:
            continue
        ele = row.get("altitude")
        ts_ms = row.get("ts_unix_ms")
        hr = row.get("hr")
        points.append(
            TrackPoint(
                lat=float(lat),
                lon=float(lon),
                elevation=float(ele) if ele is not None else 0.0,
                timestamp=(float(ts_ms) / 1000.0) if ts_ms is not None else 0.0,
                heart_rate=int(hr) if hr is not None else 0,
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
