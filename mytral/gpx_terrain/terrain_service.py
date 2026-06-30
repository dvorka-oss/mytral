# MyTraL: my training log
#
# Copyright (C) 2015-2026 Martin Dvorak <martin.dvorak@mindforger.com>
#
# This program is free software: you can redistribute it and/or modify
# it under the terms of the GNU Affero General Public License as published by
# the Free Software Foundation, either version 3 of the License, or
# (at your option) any later version.

"""High-level terrain visualisation service.

Orchestrates all gpx_terrain sub-modules to produce GLTF terrain meshes
and GeoJSON track overlays from stored GPX activity data.

Matching CubeTrek's TrackViewerService.java responsibilities.
"""

import json
import pathlib

import numpy as np

from mytral.gpx_terrain import coordinates
from mytral.gpx_terrain import gltf_writer
from mytral.gpx_terrain import gpx_worker
from mytral.gpx_terrain import hgt_loader
from mytral.gpx_terrain import map_tile
from mytral.gpx_terrain import mesh_builder

# default CubeTrek mesh parameters
_SCALE_FACTOR: float = 0.0001
_Z_EXAGGERATION: float = 1.5
_HEIGHT_OFFSET_M: float = 500.0  # ensure terrain base stays above zero
_PADDING_M: float = 500.0  # bounding box padding around track
_MAX_TILES: int = 48
_GRID_CELLS_PER_TILE: int = 40  # DEM sample density per map tile
_GLTF_CACHE_MAX: int = 16  # cap in-memory GLTF cache (each entry is large base64)

# OSM raster tile template (no API key required)
OSM_TILE_TEMPLATE: str = "https://tile.openstreetmap.org/{z}/{x}/{y}.png"
# MapTiler template — caller substitutes the actual key
MAPTILER_STANDARD_TEMPLATE: str = (
    "https://api.maptiler.com/maps/basic/{z}/{x}/{y}.png?key={key}"
)
MAPTILER_SATELLITE_TEMPLATE: str = (
    "https://api.maptiler.com/tiles/satellite-v2/{z}/{x}/{y}.jpg?key={key}"
)


def _tile_template(tile_type: str, proxy_base: str = "") -> str:
    """Return the tile URL template for the given type.

    Parameters
    ----------
    tile_type : str
        One of ``"osm"``, ``"standard"``, or ``"satellite"``.
    proxy_base : str
        Base URL for the MytraL tile proxy, e.g. ``/api/terrain/tiles``.
        When non-empty, the template points to the proxy instead of the
        external CDN (avoids CORS issues when Babylon.js loads textures).
        When empty, the raw CDN URL is returned (useful for testing/CLI).

    Returns
    -------
    str
        Tile URL template with ``{z}/{x}/{y}`` placeholders.
    """
    if proxy_base:
        return f"tiles/{tile_type}/{{z}}/{{x}}/{{y}}.png"
    # direct CDN URLs (no proxy) — kept for tests and CLI usage
    if tile_type == "osm":
        return OSM_TILE_TEMPLATE
    if tile_type == "satellite":
        return MAPTILER_SATELLITE_TEMPLATE
    return MAPTILER_STANDARD_TEMPLATE


class TerrainService:
    """Converts GPX activity data to GLTF terrain meshes and GeoJSON overlays.

    Parameters
    ----------
    hgt_dir : pathlib.Path
        Directory for cached SRTM HGT elevation files.
    maptiler_key : str
        Optional MapTiler API key. When empty, OSM raster tiles are used.
    tile_proxy_base : str
        Base URL of the MytraL tile proxy, e.g. ``/api/terrain/tiles``.
        Tile URLs embedded in GLTF textures will point here so Babylon.js
        does not hit external CDNs directly (avoids CORS).
        Defaults to the empty string (direct CDN URLs — for tests/CLI).
    """

    def __init__(
        self,
        hgt_dir: pathlib.Path,
        maptiler_key: str = "",
        tile_proxy_base: str = "",
    ) -> None:
        self._hgt_cache = hgt_loader.HgtCache(hgt_dir, cells=hgt_loader.CELLS_3DEM)
        self._maptiler_key = maptiler_key
        self._tile_proxy_base = tile_proxy_base
        # bounded in-memory GLTF cache keyed by (activity_key, tile_type, proxy)
        self._gltf_cache: dict[tuple[str, str, str], str] = {}

    def build_geojson(self, gpx_stream: object, activity_name: str = "") -> str:
        """Parse a GPX stream and return a GeoJSON string.

        Parameters
        ----------
        gpx_stream : file-like
            Open binary stream of the GPX file.
        activity_name : str
            Human-readable track name written to GeoJSON properties.

        Returns
        -------
        str
            GeoJSON Feature JSON string.
        """
        points = gpx_worker.parse_gpx(gpx_stream)
        points = gpx_worker.simplify_track(points, epsilon_m=2.0)

        lats = [p.lat for p in points]
        lons = [p.lon for p in points]
        bbox = coordinates.BoundingBox.from_track(lats, lons, padding_m=_PADDING_M)
        gps_min_ele = float(min(p.elevation for p in points)) if points else 0.0

        # normalize GPS elevation against SRTM so the track tube Y matches
        # the terrain mesh Y (both referencing the same SRTM surface)
        try:
            srtm_eles = [
                float(self._hgt_cache.elevation_at(p.lat, p.lon)) for p in points
            ]
            if any(e > 0 for e in srtm_eles):
                points = gpx_worker.normalize_elevation(points, srtm_eles)
        except Exception:
            pass  # leave GPS elevations as-is on error

        # compute tiles once — used for terrain min/max, tileBBoxes in GeoJSON,
        # and shared with _generate_gltf() so both outputs use the same tile set
        zoom, tiles = map_tile.auto_zoom(bbox, max_tiles=_MAX_TILES)
        tile_bboxes: list[dict] = []
        for tile in tiles:
            tb = tile.bbox()
            tile_bboxes.append(
                {
                    "n_Bound": tb.north,
                    "s_Bound": tb.south,
                    "w_Bound": tb.west,
                    "e_Bound": tb.east,
                    "widthLatDegree": tb.height_deg_lat,
                    "widthLonDegree": tb.width_deg_lon,
                    "tile_zoom": tile.zoom,
                    "tile_x": tile.x,
                    "tile_y": tile.y,
                }
            )

        # compute the global SRTM minimum used by _generate_gltf() so that
        # the track tube and terrain mesh share the same Y origin
        terrain_min_ele = gps_min_ele
        terrain_max_ele = gps_min_ele + 100.0  # fallback
        try:
            cells = max(4, _GRID_CELLS_PER_TILE)
            all_mins: list[float] = []
            all_maxs: list[float] = []
            for tile in tiles:
                eg = hgt_loader.load_elevation_grid(
                    tile.bbox(), cells, cells, self._hgt_cache
                )
                all_mins.append(float(eg.min()))
                all_maxs.append(float(eg.max()))
            if all_mins:
                terrain_min_ele = min(all_mins)
                terrain_max_ele = max(all_maxs)
        except Exception:
            pass  # fall back to GPS track minimum

        # scene_params lets terrain3d.js map lat/lon/ele → scene XYZ
        # using the exact same formulas as mesh_builder.py
        scene_params = {
            "center_lat": bbox.center_lat,
            "center_lon": bbox.center_lon,
            "meters_per_degree_lat": coordinates.METERS_PER_DEGREE_LAT,
            "meters_per_degree_lon": coordinates.meters_per_degree_lon(bbox.center_lat),
            "scale_factor": _SCALE_FACTOR,
            "z_exaggeration": _Z_EXAGGERATION,
            "height_offset_m": _HEIGHT_OFFSET_M,
            "terrain_min_elevation_m": terrain_min_ele,
            "terrain_max_elevation_m": terrain_max_ele,
            "gps_min_elevation_m": gps_min_ele,
        }

        # label points for 3D signposts: start, end, highest elevation
        labels: dict[str, dict] = {}
        if points:
            start = points[0]
            end = points[-1]
            labels["start"] = {
                "lat": start.lat,
                "lon": start.lon,
                "ele": start.elevation,
                "label": "Start",
            }
            labels["end"] = {
                "lat": end.lat,
                "lon": end.lon,
                "ele": end.elevation,
                "label": "Finish",
            }
            highest = max(points, key=lambda p: p.elevation)
            if highest.elevation > 0:
                labels["highest"] = {
                    "lat": highest.lat,
                    "lon": highest.lon,
                    "ele": highest.elevation,
                    "label": f"{int(highest.elevation)} m",
                }

        feature = gpx_worker.points_to_geojson(
            points,
            name=activity_name,
            scene_params=scene_params,
            tile_bboxes=tile_bboxes,
            labels=labels,
        )
        return json.dumps(feature)

    def build_gltf(
        self,
        gpx_stream: object,
        activity_key: str,
        tile_type: str = "osm",
        with_enclosure: bool = False,
    ) -> str:
        """Build a GLTF terrain mesh for a GPX track.

        Results are cached in memory by (activity_key, tile_type).

        Parameters
        ----------
        gpx_stream : file-like
            Open binary stream of the GPX file.
        activity_key : str
            Unique activity identifier used as cache key.
        tile_type : str
            Tile texture style: ``"osm"``, ``"standard"``, or ``"satellite"``.
        with_enclosure : bool
            Whether to add vertical boundary walls.

        Returns
        -------
        str
            GLTF 2.0 JSON string.
        """
        cache_key = (activity_key, tile_type, self._tile_proxy_base)
        if cache_key in self._gltf_cache:
            # mark as most-recently-used
            result = self._gltf_cache.pop(cache_key)
            self._gltf_cache[cache_key] = result
            return result

        result = self._generate_gltf(gpx_stream, tile_type, with_enclosure)
        self._gltf_cache[cache_key] = result
        # evict least-recently-used entries beyond the cap (dict keeps order)
        while len(self._gltf_cache) > _GLTF_CACHE_MAX:
            oldest = next(iter(self._gltf_cache))
            del self._gltf_cache[oldest]
        return result

    def _generate_gltf(
        self,
        gpx_stream: object,
        tile_type: str,
        with_enclosure: bool,
    ) -> str:
        """Internal: parse GPX, load elevation, build mesh, assemble GLTF."""
        points = gpx_worker.parse_gpx(gpx_stream)
        points = gpx_worker.simplify_track(points, epsilon_m=2.0)

        lats = [p.lat for p in points]
        lons = [p.lon for p in points]
        bbox = coordinates.BoundingBox.from_track(lats, lons, padding_m=_PADDING_M)

        zoom, tiles = map_tile.auto_zoom(bbox, max_tiles=_MAX_TILES)

        template = _tile_template(tile_type, self._tile_proxy_base)

        terrain_meshes: list[mesh_builder.MeshBuffers] = []
        tile_metadata: list[dict] = []

        center_lat = bbox.center_lat
        center_lon = bbox.center_lon
        cells_lon = max(4, _GRID_CELLS_PER_TILE)
        cells_lat = max(4, _GRID_CELLS_PER_TILE)

        # Build one DEM grid over the full tile lattice, then slice individual
        # tile meshes from it. This guarantees that neighbouring tiles share the
        # exact same border samples and cannot form vertical seam walls.
        min_tile_x = min(tile.x for tile in tiles)
        max_tile_x = max(tile.x for tile in tiles)
        min_tile_y = min(tile.y for tile in tiles)
        max_tile_y = max(tile.y for tile in tiles)

        tile_nw = map_tile.MapTile(zoom=zoom, x=min_tile_x, y=min_tile_y).bbox()
        tile_se = map_tile.MapTile(zoom=zoom, x=max_tile_x, y=max_tile_y).bbox()
        lattice_bbox = coordinates.BoundingBox(
            north=tile_nw.north,
            south=tile_se.south,
            west=tile_nw.west,
            east=tile_se.east,
        )

        tile_cols = max_tile_x - min_tile_x + 1
        tile_rows = max_tile_y - min_tile_y + 1
        master_cells_lon = tile_cols * (cells_lon - 1) + 1
        master_cells_lat = tile_rows * (cells_lat - 1) + 1

        master_grid = hgt_loader.load_elevation_grid(
            lattice_bbox,
            master_cells_lon,
            master_cells_lat,
            self._hgt_cache,
        )

        # global minimum: one shift for all tiles so seams align
        global_min_ele = float(master_grid.min())
        global_shift = global_min_ele - _HEIGHT_OFFSET_M

        cell_lat_m = coordinates.METERS_PER_DEGREE_LAT

        for tile in tiles:
            tb = tile.bbox()
            tile_col = tile.x - min_tile_x
            tile_row = tile.y - min_tile_y
            x0 = tile_col * (cells_lon - 1)
            y0 = tile_row * (cells_lat - 1)
            elev_grid = master_grid[y0 : y0 + cells_lat, x0 : x0 + cells_lon]
            cell_lon_m = coordinates.meters_per_degree_lon(tb.center_lat)
            offset_x_m = (tb.west - center_lon) * cell_lon_m
            offset_y_m = (tb.north - center_lat) * cell_lat_m
            step_lon_m = tb.width_m() / (cells_lon - 1)
            step_lat_m = tb.height_m() / (cells_lat - 1)
            elev_shifted = elev_grid.astype(np.float32) - global_shift

            buf = mesh_builder.build_terrain_mesh(
                elev_shifted,
                offset_x_m=offset_x_m,
                offset_y_m=offset_y_m,
                cell_lon_m=step_lon_m,
                cell_lat_m=step_lat_m,
                scale_factor=_SCALE_FACTOR,
                z_exaggeration=_Z_EXAGGERATION,
                with_uvs=True,
            )
            terrain_meshes.append(buf)
            tile_metadata.append(
                {
                    "_tile": tile,  # stripped before writing to GLTF extras
                    "Tile_Z": str(tile.zoom),
                    "Tile_X": str(tile.x),
                    "Tile_Y": str(tile.y),
                    "NBound": str(tb.north),
                    "SBound": str(tb.south),
                    "WBound": str(tb.west),
                    "EBound": str(tb.east),
                    "cellWidth_LatMeters": str(round(step_lat_m, 4)),
                    "cellWidth_LonMeters": str(round(step_lon_m, 4)),
                }
            )

        wall_meshes: list[mesh_builder.MeshBuffers] = []
        if with_enclosure and terrain_meshes:
            # Use the same master-grid geometry so wall top edges align exactly
            # with the terrain boundary and no gaps appear at the enclosure seam.
            elev_shifted = master_grid.astype(np.float32) - global_shift
            lattice_cell_lon_m = coordinates.meters_per_degree_lon(
                lattice_bbox.center_lat
            )
            step_lon_m = lattice_bbox.width_m() / (master_cells_lon - 1)
            step_lat_m = lattice_bbox.height_m() / (master_cells_lat - 1)
            wall_meshes = mesh_builder.build_enclosure_walls(
                elev_shifted,
                offset_x_m=(lattice_bbox.west - center_lon) * lattice_cell_lon_m,
                offset_y_m=(lattice_bbox.north - center_lat) * cell_lat_m,
                cell_lon_m=step_lon_m,
                cell_lat_m=step_lat_m,
                scale_factor=_SCALE_FACTOR,
                z_exaggeration=_Z_EXAGGERATION,
            )

        return gltf_writer.assemble_gltf(
            terrain_meshes=terrain_meshes,
            wall_meshes=wall_meshes,
            tile_metadata=tile_metadata,
            tile_url_template=template,
        )

    def invalidate(self, activity_key: str) -> None:
        """Remove cached GLTF data for an activity (e.g. after GPX replacement).

        Parameters
        ----------
        activity_key : str
            Activity identifier to evict from the cache.
        """
        stale = [key for key in self._gltf_cache if key[0] == activity_key]
        for key in stale:
            del self._gltf_cache[key]
