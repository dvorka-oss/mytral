# MyTraL: my training log
#
# Copyright (C) 2015-2026 Martin Dvorak <martin.dvorak@mindforger.com>
#
# This program is free software: you can redistribute it and/or modify
# it under the terms of the GNU Affero General Public License as published by
# the Free Software Foundation, either version 3 of the License, or
# (at your option) any later version.

"""Tests for mytral.gpx_terrain modules (no network, no disk I/O)."""

import base64
import io
import json
import pathlib
import textwrap

import numpy as np
import pytest

from mytral.gpx_terrain import coordinates
from mytral.gpx_terrain import gltf_writer
from mytral.gpx_terrain import gpx_worker
from mytral.gpx_terrain import hgt_loader
from mytral.gpx_terrain import map_tile
from mytral.gpx_terrain import mesh_builder
from mytral.gpx_terrain import terrain_service
from mytral.gpx_terrain import tile_cache

# ---------------------------------------------------------------------------
# coordinates.py
# ---------------------------------------------------------------------------


@pytest.mark.mytral
def test_haversine_known_distance():
    # GIVEN two points roughly 1 degree of latitude apart (~111 km)
    lat1, lon1 = 47.0, 11.0
    lat2, lon2 = 48.0, 11.0

    # WHEN distance is computed
    dist = coordinates.haversine_m(lat1, lon1, lat2, lon2)

    # THEN result is within 500 m of the accepted value
    assert abs(dist - 111_319.5) < 500, f"haversine distance off: {dist}"


@pytest.mark.mytral
def test_haversine_same_point():
    # GIVEN the same point twice
    lat, lon = 51.5, -0.1

    # WHEN distance is computed
    dist = coordinates.haversine_m(lat, lon, lat, lon)

    # THEN distance is zero
    assert dist == pytest.approx(0.0, abs=1e-6)


@pytest.mark.mytral
def test_meters_per_degree_lon_equator_vs_pole():
    # GIVEN equator latitude (0) and near-pole latitude (89)

    # WHEN metres per degree of longitude are computed
    lon_eq = coordinates.meters_per_degree_lon(0.0)
    lon_pole = coordinates.meters_per_degree_lon(89.0)

    # THEN equator value is close to METERS_PER_DEGREE_LAT
    assert lon_eq == pytest.approx(coordinates.METERS_PER_DEGREE_LAT, rel=1e-3)
    # THEN near-pole value is much smaller
    assert lon_pole < lon_eq / 10


@pytest.mark.mytral
def test_bounding_box_from_center():
    # GIVEN a centre point and a 1000 m half-width
    lat, lon = 47.0, 11.0

    # WHEN a bounding box is constructed
    bb = coordinates.BoundingBox.from_center(lat, lon, 1000.0)

    # THEN north > south and east > west
    assert bb.north > bb.south
    assert bb.east > bb.west
    # THEN centre is preserved
    assert bb.center_lat == pytest.approx(lat, abs=1e-9)
    assert bb.center_lon == pytest.approx(lon, abs=1e-9)
    # THEN height in metres is approximately 2000 m (2 × 1000 m padding)
    assert abs(bb.height_m() - 2000.0) < 5.0


@pytest.mark.mytral
def test_bounding_box_from_track():
    # GIVEN a small set of track coordinates
    lats = [47.0, 47.01, 47.02]
    lons = [11.0, 11.01, 11.02]

    # WHEN bounding box is built with 500 m padding
    bb = coordinates.BoundingBox.from_track(lats, lons, padding_m=500.0)

    # THEN all track points are inside the bbox
    assert bb.north > max(lats)
    assert bb.south < min(lats)
    assert bb.east > max(lons)
    assert bb.west < min(lons)


# ---------------------------------------------------------------------------
# gpx_worker.py
# ---------------------------------------------------------------------------

_MINIMAL_GPX = textwrap.dedent("""\
    <?xml version="1.0" encoding="UTF-8"?>
    <gpx version="1.1" creator="test">
      <trk>
        <trkseg>
          <trkpt lat="47.0" lon="11.0"><ele>1000</ele></trkpt>
          <trkpt lat="47.01" lon="11.01"><ele>1050</ele></trkpt>
          <trkpt lat="47.02" lon="11.02"><ele>1100</ele></trkpt>
          <trkpt lat="47.03" lon="11.03"><ele>1080</ele></trkpt>
          <trkpt lat="47.04" lon="11.04"><ele>1060</ele></trkpt>
        </trkseg>
      </trk>
    </gpx>
""")


@pytest.mark.mytral
def test_parse_gpx_point_count():
    # GIVEN a minimal GPX with 5 track points
    stream = io.BytesIO(_MINIMAL_GPX.encode())

    # WHEN the GPX is parsed
    points = gpx_worker.parse_gpx(stream)

    # THEN all 5 points are returned with correct coordinates
    assert len(points) == 5
    assert points[0].lat == pytest.approx(47.0)
    assert points[0].lon == pytest.approx(11.0)
    assert points[0].elevation == pytest.approx(1000.0)


@pytest.mark.mytral
def test_parse_gpx_elevation_preserved():
    # GIVEN a GPX with known elevation sequence
    stream = io.BytesIO(_MINIMAL_GPX.encode())

    # WHEN parsed
    points = gpx_worker.parse_gpx(stream)

    # THEN elevation values match the XML
    eles = [p.elevation for p in points]
    assert eles == [1000.0, 1050.0, 1100.0, 1080.0, 1060.0]


@pytest.mark.mytral
def test_simplify_track_reduces_points():
    # GIVEN 5 points where the middle 3 are nearly collinear
    pts = [
        gpx_worker.TrackPoint(lat=47.0, lon=11.0, elevation=1000.0),
        gpx_worker.TrackPoint(lat=47.005, lon=11.005, elevation=1000.1),
        gpx_worker.TrackPoint(lat=47.01, lon=11.01, elevation=1000.2),
        gpx_worker.TrackPoint(lat=47.015, lon=11.015, elevation=1000.3),
        gpx_worker.TrackPoint(lat=47.02, lon=11.02, elevation=1000.4),
    ]

    # WHEN simplified with a 5 m epsilon
    simplified = gpx_worker.simplify_track(pts, epsilon_m=5.0)

    # THEN only endpoints survive (near-collinear interior points removed)
    assert len(simplified) < len(pts)
    assert simplified[0].lat == pytest.approx(47.0)
    assert simplified[-1].lat == pytest.approx(47.02)


@pytest.mark.mytral
def test_simplify_track_keeps_significant_deviation():
    # GIVEN 3 points where the middle one is far off the line
    pts = [
        gpx_worker.TrackPoint(lat=47.0, lon=11.0, elevation=1000.0),
        gpx_worker.TrackPoint(lat=47.05, lon=11.0, elevation=1000.0),  # off east
        gpx_worker.TrackPoint(lat=47.1, lon=11.1, elevation=1000.0),
    ]

    # WHEN simplified with 2 m epsilon
    simplified = gpx_worker.simplify_track(pts, epsilon_m=2.0)

    # THEN all 3 points are retained (deviation >> 2 m)
    assert len(simplified) == 3


@pytest.mark.mytral
def test_track_summary_distance():
    # GIVEN two points exactly 1 degree of latitude apart
    pts = [
        gpx_worker.TrackPoint(lat=47.0, lon=11.0, elevation=1000.0),
        gpx_worker.TrackPoint(lat=48.0, lon=11.0, elevation=1000.0),
    ]

    # WHEN summary is computed
    summary = gpx_worker.track_summary(pts)

    # THEN distance matches haversine expectation within 500 m
    assert abs(summary.distance_m - 111_319.5) < 500


@pytest.mark.mytral
def test_track_summary_elevation_gain_loss():
    # GIVEN a track: climb 100 m then descend 50 m
    pts = [
        gpx_worker.TrackPoint(lat=47.0, lon=11.0, elevation=1000.0),
        gpx_worker.TrackPoint(lat=47.01, lon=11.0, elevation=1100.0),
        gpx_worker.TrackPoint(lat=47.02, lon=11.0, elevation=1050.0),
    ]

    # WHEN summary is computed
    summary = gpx_worker.track_summary(pts)

    # THEN elevation gain is 100 m and loss is 50 m
    assert summary.elevation_up_m == pytest.approx(100.0)
    assert summary.elevation_down_m == pytest.approx(50.0)


@pytest.mark.mytral
def test_normalize_elevation_shifts_mean():
    # GIVEN track points with GPS elevation mean of 1000 m
    pts = [
        gpx_worker.TrackPoint(lat=47.0, lon=11.0, elevation=900.0),
        gpx_worker.TrackPoint(lat=47.01, lon=11.0, elevation=1000.0),
        gpx_worker.TrackPoint(lat=47.02, lon=11.0, elevation=1100.0),
    ]
    # AND SRTM elevations with mean 1050 m (50 m higher)
    srtm = [950.0, 1050.0, 1150.0]

    # WHEN normalization is applied
    corrected = gpx_worker.normalize_elevation(pts, srtm)

    # THEN all points are shifted up by 50 m
    assert corrected[0].elevation == pytest.approx(950.0)
    assert corrected[1].elevation == pytest.approx(1050.0)
    assert corrected[2].elevation == pytest.approx(1150.0)


@pytest.mark.mytral
def test_points_to_geojson_structure():
    # GIVEN two track points
    pts = [
        gpx_worker.TrackPoint(lat=47.0, lon=11.0, elevation=1000.0, timestamp=0.0),
        gpx_worker.TrackPoint(lat=47.01, lon=11.01, elevation=1010.0, timestamp=60.0),
    ]

    # WHEN GeoJSON is generated
    feature = gpx_worker.points_to_geojson(pts, name="Test")

    # THEN structure is a valid GeoJSON Feature with LineString geometry
    assert feature["type"] == "Feature"
    assert feature["geometry"]["type"] == "LineString"
    coords = feature["geometry"]["coordinates"]
    assert len(coords) == 2
    # THEN first coordinate is [lon, lat, ele, ts, dist, hr]
    assert coords[0][0] == pytest.approx(11.0)  # lon
    assert coords[0][1] == pytest.approx(47.0)  # lat
    assert coords[0][2] == pytest.approx(1000.0)  # elevation
    assert coords[0][4] == pytest.approx(0.0)  # cumulative distance at start


# ---------------------------------------------------------------------------
# map_tile.py
# ---------------------------------------------------------------------------


@pytest.mark.mytral
def test_map_tile_from_latlon_zoom14():
    # GIVEN a known coordinate (Innsbruck, Austria)
    lat, lon = 47.27, 11.39

    # WHEN tile is computed at zoom 14
    tile = map_tile.MapTile.from_latlon(lat, lon, zoom=14)

    # THEN tile coordinates are in expected range for zoom 14 Europe
    assert tile.zoom == 14
    assert 8700 < tile.x < 9000
    assert 5600 < tile.y < 5900


@pytest.mark.mytral
def test_map_tile_bbox_contains_point():
    # GIVEN a tile derived from a coordinate
    lat, lon = 47.27, 11.39

    # WHEN the tile bbox is computed
    tile = map_tile.MapTile.from_latlon(lat, lon, zoom=12)
    bb = tile.bbox()

    # THEN the original coordinate is inside the tile bbox
    assert bb.south <= lat <= bb.north
    assert bb.west <= lon <= bb.east


@pytest.mark.mytral
def test_tiles_for_bbox_count():
    # GIVEN a small bounding box (roughly 1×1 degree)
    bb = coordinates.BoundingBox(north=48.0, south=47.0, west=11.0, east=12.0)

    # WHEN tiles are computed at zoom 10
    tiles = map_tile.tiles_for_bbox(bb, zoom=10)

    # THEN at least 1 tile and at most max_tiles is returned
    assert 1 <= len(tiles) <= 48


@pytest.mark.mytral
def test_auto_zoom_respects_max_tiles():
    # GIVEN a large bounding box that would exceed 48 tiles at zoom 14
    bb = coordinates.BoundingBox(north=50.0, south=45.0, west=5.0, east=15.0)

    # WHEN auto_zoom is called
    zoom, tiles = map_tile.auto_zoom(bb, max_tiles=48)

    # THEN the returned tile list does not exceed the limit
    assert len(tiles) <= 48
    assert zoom >= 1


@pytest.mark.mytral
def test_map_tile_url_template():
    # GIVEN a tile
    tile = map_tile.MapTile(zoom=14, x=8765, y=5743)

    # WHEN URL is formatted with {z}/{x}/{y} template
    url = tile.url("https://tile.openstreetmap.org/{z}/{x}/{y}.png")

    # THEN the URL contains the correct values
    assert "14" in url
    assert "8765" in url
    assert "5743" in url


# ---------------------------------------------------------------------------
# hgt_loader.py
# ---------------------------------------------------------------------------


class _SequentialElevationCache:
    """Test cache that returns prepared elevation values in row-major order."""

    def __init__(self, values: list[int]) -> None:
        self._values = values
        self._idx = 0

    def elevation_at(self, lat: float, lon: float) -> int:
        del lat
        del lon
        value = self._values[self._idx]
        self._idx += 1
        return value


@pytest.mark.mytral
def test_load_elevation_grid_fills_large_void_regions():
    # GIVEN a grid with mostly void samples and only a few known elevations
    raw = np.full((7, 7), -32768, dtype=np.int32)
    raw[0, 0] = 1500
    raw[0, -1] = 1600
    raw[-1, 0] = 1550
    raw[-1, -1] = 1650
    cache = _SequentialElevationCache(raw.reshape(-1).tolist())
    bbox = coordinates.BoundingBox(north=1.0, south=0.0, west=0.0, east=1.0)

    # WHEN elevation grid is loaded and voids are filled
    filled = hgt_loader.load_elevation_grid(
        bbox=bbox,
        cells_lon=7,
        cells_lat=7,
        cache=cache,
    )

    # THEN no zero/negative collapse samples remain
    assert np.all(filled > 0)
    # THEN values stay within the expected mountain-elevation range
    assert int(filled.min()) >= 1500
    assert int(filled.max()) <= 1650


@pytest.mark.mytral
def test_hgt_cache_clamps_srtm_void_sentinel(tmp_path):
    # GIVEN an HgtCache using an srtm provider that returns -32768 (void)
    cache = hgt_loader.HgtCache(tmp_path)

    class _StubSrtm:
        def get_elevation(self, lat: float, lon: float) -> int:
            del lat
            del lon
            return -32768

    cache._srtm = _StubSrtm()

    # WHEN elevation is queried
    value = cache.elevation_at(47.1, 11.2)

    # THEN the value is clamped to the configured void threshold
    assert value == -500


# ---------------------------------------------------------------------------
# mesh_builder.py
# ---------------------------------------------------------------------------


@pytest.mark.mytral
def test_build_terrain_mesh_index_count():
    # GIVEN a 4×4 elevation grid (flat, all zeros)
    H, W = 4, 4
    elev = np.zeros((H, W), dtype=np.int16)

    # WHEN mesh is built
    buf = mesh_builder.build_terrain_mesh(
        elev,
        offset_x_m=0.0,
        offset_y_m=0.0,
        cell_lon_m=10.0,
        cell_lat_m=10.0,
    )

    # THEN index count = (H-1)*(W-1)*6 triangles
    expected_indices = (H - 1) * (W - 1) * 6
    assert buf.index_count == expected_indices


@pytest.mark.mytral
def test_build_terrain_mesh_vertex_count():
    # GIVEN a 5×6 elevation grid
    H, W = 5, 6
    elev = np.zeros((H, W), dtype=np.int16)

    # WHEN mesh is built
    buf = mesh_builder.build_terrain_mesh(
        elev,
        offset_x_m=0.0,
        offset_y_m=0.0,
        cell_lon_m=10.0,
        cell_lat_m=10.0,
    )

    # THEN vertex count = H * W
    assert buf.vertex_count == H * W


@pytest.mark.mytral
def test_build_terrain_mesh_uv_present():
    # GIVEN a 3×3 grid
    elev = np.zeros((3, 3), dtype=np.int16)

    # WHEN mesh is built with UVs
    buf = mesh_builder.build_terrain_mesh(
        elev,
        offset_x_m=0.0,
        offset_y_m=0.0,
        cell_lon_m=10.0,
        cell_lat_m=10.0,
        with_uvs=True,
    )

    # THEN UV buffer has the correct byte length (vertex_count × 2 floats × 4 bytes)
    assert buf.has_uvs
    assert len(buf.uvs) == buf.vertex_count * 2 * 4


@pytest.mark.mytral
def test_build_terrain_mesh_height_scales():
    # GIVEN a 2×2 grid with one cell at 1000 m
    elev = np.array([[1000, 1000], [1000, 1000]], dtype=np.int16)
    sf = 0.0001
    z_ex = 1.5

    # WHEN mesh is built
    buf = mesh_builder.build_terrain_mesh(
        elev,
        offset_x_m=0.0,
        offset_y_m=0.0,
        cell_lon_m=10.0,
        cell_lat_m=10.0,
        scale_factor=sf,
        z_exaggeration=z_ex,
    )

    # THEN vertex Y component (height) = 1000 * sf * z_ex
    verts = np.frombuffer(buf.vertices, dtype=np.float32).reshape(-1, 3)
    expected_y = 1000 * sf * z_ex
    # THEN all Y values match (flat terrain)
    assert np.allclose(verts[:, 1], expected_y, atol=1e-5)


@pytest.mark.mytral
def test_build_enclosure_walls_count():
    # GIVEN a 4×4 elevation grid
    elev = np.zeros((4, 4), dtype=np.int16)

    # WHEN enclosure walls are built
    walls = mesh_builder.build_enclosure_walls(
        elev,
        offset_x_m=0.0,
        offset_y_m=0.0,
        cell_lon_m=10.0,
        cell_lat_m=10.0,
    )

    # THEN exactly 4 walls are returned
    assert len(walls) == 4
    # THEN each wall has indices and vertices
    for wall in walls:
        assert wall.index_count > 0
        assert wall.vertex_count > 0


# ---------------------------------------------------------------------------
# gltf_writer.py
# ---------------------------------------------------------------------------


def _make_simple_mesh() -> mesh_builder.MeshBuffers:
    """Create a minimal 2×2 terrain mesh for testing."""
    elev = np.array([[100, 200], [150, 180]], dtype=np.int16)
    return mesh_builder.build_terrain_mesh(
        elev,
        offset_x_m=0.0,
        offset_y_m=0.0,
        cell_lon_m=10.0,
        cell_lat_m=10.0,
    )


@pytest.mark.mytral
def test_assemble_gltf_valid_json():
    # GIVEN a minimal terrain mesh
    buf = _make_simple_mesh()
    meta = [{"Tile_Z": "14", "Tile_X": "1", "Tile_Y": "1"}]

    # WHEN GLTF is assembled
    gltf_str = gltf_writer.assemble_gltf(
        terrain_meshes=[buf],
        wall_meshes=[],
        tile_metadata=meta,
        tile_url_template=None,
    )

    # THEN output is valid JSON
    doc = json.loads(gltf_str)
    assert "asset" in doc
    assert doc["asset"]["version"] == "2.0"


@pytest.mark.mytral
def test_assemble_gltf_has_expected_sections():
    # GIVEN a minimal terrain mesh
    buf = _make_simple_mesh()
    meta = [{"Tile_Z": "14", "Tile_X": "1", "Tile_Y": "1"}]

    # WHEN GLTF is assembled
    doc = json.loads(gltf_writer.assemble_gltf([buf], [], meta, tile_url_template=None))

    # THEN all required GLTF 2.0 sections are present
    for section in ("scenes", "nodes", "meshes", "buffers", "bufferViews", "accessors"):
        assert section in doc, f"missing section: {section}"


@pytest.mark.mytral
def test_assemble_gltf_with_texture_url():
    # GIVEN a terrain mesh with UV coords
    buf = _make_simple_mesh()
    tile = map_tile.MapTile(zoom=14, x=8765, y=5743)
    meta = [{"_tile": tile, "Tile_Z": "14", "Tile_X": "8765", "Tile_Y": "5743"}]

    # WHEN GLTF is assembled with OSM tile template
    doc = json.loads(
        gltf_writer.assemble_gltf(
            [buf],
            [],
            meta,
            tile_url_template="https://tile.openstreetmap.org/{z}/{x}/{y}.png",
        )
    )

    # THEN materials, textures and images sections are present
    assert "materials" in doc
    assert "images" in doc
    assert len(doc["images"]) == 1
    assert "openstreetmap" in doc["images"][0]["uri"]


@pytest.mark.mytral
def test_assemble_gltf_wall_meshes_add_nodes():
    # GIVEN a terrain mesh and one wall mesh
    buf = _make_simple_mesh()
    elev = np.zeros((3, 3), dtype=np.int16)
    walls = mesh_builder.build_enclosure_walls(elev, 0.0, 0.0, 10.0, 10.0)
    meta = [{"Tile_Z": "14", "Tile_X": "1", "Tile_Y": "1"}]

    # WHEN GLTF is assembled with all 4 walls
    doc = json.loads(
        gltf_writer.assemble_gltf([buf], walls, meta, tile_url_template=None)
    )

    # THEN total node count = 1 terrain + 4 walls
    assert len(doc["nodes"]) == 5


# ---------------------------------------------------------------------------
# terrain_service.py
# ---------------------------------------------------------------------------


def _mesh_positions_from_gltf(doc: dict, mesh_idx: int) -> np.ndarray:
    """Decode POSITION vertices for one GLTF mesh as float32 [N,3]."""
    primitive = doc["meshes"][mesh_idx]["primitives"][0]
    pos_acc_idx = primitive["attributes"]["POSITION"]
    pos_acc = doc["accessors"][pos_acc_idx]
    pos_bv = doc["bufferViews"][pos_acc["bufferView"]]
    pos_buf = doc["buffers"][pos_bv["buffer"]]
    raw = base64.b64decode(pos_buf["uri"].split(",", maxsplit=1)[1])
    return np.frombuffer(raw, dtype="<f4").reshape(-1, 3)


@pytest.mark.mytral
def test_terrain_service_tatry_tile_seams_are_continuous(monkeypatch, tmp_path):
    # GIVEN Tatry GPX and a DEM loader with bbox-dependent bias that would
    # create seam jumps if tiles were sampled independently
    calls: list[tuple[int, int]] = []

    def _biased_loader(
        bbox: coordinates.BoundingBox,
        cells_lon: int,
        cells_lat: int,
        cache: object,
    ) -> np.ndarray:
        del cache
        calls.append((cells_lon, cells_lat))
        base = int(round((bbox.north + bbox.west) * 10_000))
        row = np.arange(cells_lat, dtype=np.int32)[:, None] * 7
        col = np.arange(cells_lon, dtype=np.int32)[None, :] * 11
        return (base + row + col).astype(np.int16)

    monkeypatch.setattr(
        terrain_service.hgt_loader,
        "load_elevation_grid",
        _biased_loader,
    )

    svc = terrain_service.TerrainService(hgt_dir=tmp_path / "hgt")
    tatry_gpx = pathlib.Path("tests/data/import/gpx/hike-tatry-9718831053.gpx")
    with tatry_gpx.open("rb") as stream:
        gltf_str = svc.build_gltf(
            gpx_stream=stream,
            activity_key="tatry-seam-regression",
            tile_type="osm",
            with_enclosure=False,
        )

    # WHEN mesh borders are compared across adjacent tiles
    doc = json.loads(gltf_str)
    tile_grids: dict[tuple[int, int], np.ndarray] = {}
    for idx, mesh in enumerate(doc["meshes"]):
        extras = mesh.get("extras")
        if not extras:
            continue
        tx = int(extras["Tile_X"])
        ty = int(extras["Tile_Y"])
        positions = _mesh_positions_from_gltf(doc, idx)
        side = int(round(np.sqrt(float(positions.shape[0]))))
        tile_grids[(tx, ty)] = positions.reshape(side, side, 3)

    # THEN all shared tile edges are geometrically continuous
    assert len(calls) == 1
    for (tx, ty), grid in tile_grids.items():
        east = tile_grids.get((tx + 1, ty))
        if east is not None:
            assert np.allclose(grid[:, -1, 1], east[:, 0, 1], atol=1e-6)
        south = tile_grids.get((tx, ty + 1))
        if south is not None:
            assert np.allclose(grid[-1, :, 1], south[0, :, 1], atol=1e-6)


@pytest.mark.mytral
def test_assemble_gltf_map_material_is_mostly_unlit():
    # GIVEN a textured terrain mesh
    buf = _make_simple_mesh()
    tile = map_tile.MapTile(zoom=14, x=8765, y=5743)
    meta = [{"_tile": tile, "Tile_Z": "14", "Tile_X": "8765", "Tile_Y": "5743"}]

    # WHEN GLTF is assembled with a tile texture
    doc = json.loads(
        gltf_writer.assemble_gltf(
            [buf], [], meta, tile_url_template="https://tile.example/{z}/{x}/{y}.png"
        )
    )

    # THEN the material emits the map texture (so the map reads at near-true
    # brightness regardless of slope), with a dim lit base term for relief
    mat = doc["materials"][0]
    assert "emissiveTexture" in mat
    assert mat["emissiveFactor"][0] > 0.5
    assert mat["pbrMetallicRoughness"]["baseColorFactor"][0] < 0.5


# ---------------------------------------------------------------------------
# tile_cache.py
# ---------------------------------------------------------------------------


@pytest.mark.mytral
def test_tile_cache_miss_then_hit_roundtrip(tmp_path):
    # GIVEN an empty tile cache
    cache = tile_cache.TileCache(tmp_path / "map_tiles")

    # WHEN a tile is requested before it is stored
    # THEN it is a miss
    assert cache.get("osm", 14, 8765, 5743) is None

    # WHEN the tile bytes are stored and re-read
    cache.put("osm", 14, 8765, 5743, b"\x89PNG-fake-tile")

    # THEN the same bytes come back (offline-capable on subsequent loads)
    assert cache.get("osm", 14, 8765, 5743) == b"\x89PNG-fake-tile"


@pytest.mark.mytral
def test_tile_cache_rejects_unknown_maptype(tmp_path):
    # GIVEN a tile cache
    cache = tile_cache.TileCache(tmp_path / "map_tiles")

    # WHEN an unknown maptype is used (defence against path traversal)
    # THEN it raises rather than writing outside the cache tree
    with pytest.raises(ValueError):
        cache.put("../etc", 1, 2, 3, b"x")
