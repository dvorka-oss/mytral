# MyTraL: my training log
#
# Copyright (C) 2015-2026 Martin Dvorak <martin.dvorak@mindforger.com>
#
# This program is free software: you can redistribute it and/or modify
# it under the terms of the GNU General Public License as published by
# the Free Software Foundation, either version 3 of the License, or
# (at your option) any later version.

"""
CUBETREK 3D GPX VISUALIZATION: Analysis & Python Implementation Plan
=====================================================================

This file analyzes the CubeTrek + TopoLibrary open-source Java projects
and provides a concrete Python implementation plan for MytraL.

CubeTrek sources:     /home/dvorka/p/mytral/git/cube-trek/CubeTrek
TopoLibrary sources:  /home/dvorka/p/mytral/git/cube-trek/TopoLibrary
MytraL sources:       /home/dvorka/p/mytral/git/my-training-log

CORRECTION FROM INITIAL ANALYSIS
---------------------------------
TopoLibrary is OPEN SOURCE (Gradle project, MIT-style license).
All algorithms are available and are straightforward NumPy/Python translations.
The full CubeTrek port is now feasible — much more so than originally assessed.

VERDICT
-------
Port TopoLibrary to Python (~600-900 lines) and keep the Babylon.js frontend
unchanged. The Java algorithms map 1:1 to NumPy. This gives MytraL the exact
same 3D terrain + GPX visualization as CubeTrek.
"""

# =============================================================================
# SECTION 1: CUBETREK ARCHITECTURE (full pipeline)
# =============================================================================

CUBETREK_PIPELINE = """
END-TO-END VISUALIZATION PIPELINE
===================================

  [1] GPX/FIT file upload (POST /upload)
         │
         ▼
  [2] StorageService.java (CubeTrek)
         ├── Parse:    GPXWorker.loadGPXTracks()     ← jpx library
         ├── Parse:    GPXWorker.loadFitTracks()     ← Garmin FIT SDK
         ├── Simplify: GPXWorker.reduceTrackSegments(epsilon=2m)
         │             algorithm: Ramer-Douglas-Peucker
         ├── Elevate:  GPXWorker.replaceElevationData()
         │             source: HGT SRTM files (1DEM 30m OR 3DEM 90m)
         ├── Smooth:   GPXWorker.normalizeElevationData()
         │             algorithm: mean-bias correction (shift GPS to DEM mean)
         └── Stats:    GPXWorker.getTrackSummary()
         │
         ▼
  [3] PostgreSQL + PostGIS (CubeTrek persistence)
         ├── trackgeodata.multilinestring  GEOMETRY(MULTILINESTRING,4326)
         ├── trackgeodata.altitudes        BYTEA (serialized int[])
         ├── trackgeodata.times            BYTEA (serialized ZonedDateTime[])
         └── osm_peaks                     GEOMETRY(POINT) — OSM summit data
         │
         ▼
  [4] TrackViewerService.getGLTF()  (on browser request /view/{id})
         │   Cached 1 hour (Caffeine)
         ├── Compute bounding box (track + ~500 m padding)
         ├── Auto-select zoom level (target ≤ 48 map tiles)
         └── TopoLibrary.GLTFWorker.build()
                 │
                 ▼
  [5] GLTFWorker / GLTFDatafile (TopoLibrary core)
         ├── For each map tile in bbox grid:
         │     ├── Load HGT elevation cells (HGTWorker.load_3DEM)
         │     ├── Generate triangle mesh (vertices + index buffer)
         │     │       indices: 6 per grid quad (2 CCW triangles)
         │     │       vertices: (x_m, height*scale, y_m) relative to center
         │     ├── Generate UV texture coordinates (0..1 over tile)
         │     └── Encode all buffers as base64 data URIs
         ├── Optionally: generate enclosure walls (4 vertical boundary walls)
         └── Emit GLTF 2.0 JSON (one mesh node per tile + per wall)
         │
         ▼
  [6] Browser: Babylon.js 6.7.0 (WebGL)
         ├── BABYLON.SceneLoader.ImportMesh() loads GLTF
         ├── Reads tile metadata from mesh.extras (Z/X/Y, bounds, cell widths)
         ├── Fetches map tile PNGs: /api/gltf/map/{type}/{z}/{x}/{y}.png
         ├── Arc-rotate camera + pinch zoom + touch pan
         └── GeoJSON overlay: GPX polyline + OSM peaks as 3D markers
         │
         ▼
  [7] Elevation/speed graph (D3.js 7)
         └── Synchronized via EventBus: hover → 3D marker + graph crosshair
"""

# =============================================================================
# SECTION 2: TOPOLIBRARY — ALGORITHM-BY-ALGORITHM PYTHON MAPPING
# =============================================================================

TOPOLIBRARY_JAVA_TO_PYTHON = """
TopoLibrary is 7 Java classes, ~2,300 lines total.
Every algorithm maps directly to Python + NumPy with no major conceptual gaps.

───────────────────────────────────────────────────────────────────────────────
CLASS: LatLon & LatLonBoundingBox  (~200 lines Java)
───────────────────────────────────────────────────────────────────────────────
Java algorithm:
  Haversine distance:
    dLat = radians(lat1 - lat2)
    dLon = radians(lon1 - lon2)
    a = sin²(dLat/2) + cos(lat1) * cos(lat2) * sin²(dLon/2)
    return 6_378_137 * 2 * atan2(√a, √(1-a))

  Degree ↔ meter conversions:
    meters_per_degree_lat = 6_378_137 * π/180 ≈ 111,319.5 m  (constant)
    meters_per_degree_lon = 6_378_137 * cos(radians(lat)) * π/180

Python mapping:
  USE: numpy scalar math or pyproj.Geod for vectorized haversine.
  COMPLEXITY: ~50 lines, trivial.

───────────────────────────────────────────────────────────────────────────────
CLASS: HGTFileLoader_LocalStorage  (~100 lines Java)
───────────────────────────────────────────────────────────────────────────────
Java algorithm:
  File format: big-endian signed int16, row-major, N→S, W→E
  Grid sizes: 1201×1201 (3DEM, 90m) or 3601×3601 (1DEM, 30m)
  Hole fill: values < -500 clamped to -500 (no land below Dead Sea)
  Query: nearest-neighbor (integer indices, no interpolation)

Python mapping:
  import numpy as np
  data = np.fromfile(path, dtype='>i2').reshape(cells, cells)
  data = np.where(data < -500, -500, data)
  # Query:
  ix = int((lon - bbox_w) / cell_width_lon)
  iy = int((bbox_n - lat) / cell_width_lat)
  elevation = data[iy, ix]

  COMPLEXITY: ~30 lines, trivial (NumPy does all the work).

───────────────────────────────────────────────────────────────────────────────
CLASS: HGTWorker.load_3DEM()  (~400 lines Java, but mostly bookkeeping)
───────────────────────────────────────────────────────────────────────────────
Java algorithm:
  Goal: stitch multiple HGT tiles into one contiguous elevation array.
  Logic:
    1. Determine which HGT files are needed (tiles span bbox)
    2. For each file (outer=longitude, inner=latitude loop):
       - Calculate which rows/columns to copy from that file
       - Handle 1-cell overlap between adjacent tiles
       - System.arraycopy() into output buffer
  File naming: N/S##E/W###.hgt  e.g. "N47E011.hgt"

Python mapping:
  def load_elevation_grid(bbox, cells_lon, cells_lat, hgt_dir):
      out = np.zeros((cells_lat, cells_lon), dtype=np.int16)
      # iterate needed tiles, slice numpy arrays, np.copyto()
      # numpy slicing replaces the Java arraycopy bookkeeping cleanly

  COMPLEXITY: ~100-150 lines. Medium difficulty.
  Main challenge: correctly computing tile boundary overlaps.
  NumPy slicing makes this cleaner than Java.

───────────────────────────────────────────────────────────────────────────────
CLASS: GPXWorker  (~688 lines Java)
───────────────────────────────────────────────────────────────────────────────

loadGPXTracks():
  Java: uses jpx library → returns List<Track>
  Python: gpxpy.parse(f) → same structure
  COMPLEXITY: ~20 lines

loadFitTracks():
  Java: Garmin FIT SDK (fit.jar)
  Python: fitdecode library (pip install fitdecode)
  COMPLEXITY: ~50 lines

reduceTrackSegments() — Ramer-Douglas-Peucker:
  Java: custom implementation, epsilon in meters
  Python:
    Option A: rdp library (pip install rdp) — pure Python
    Option B: shapely.simplify(tolerance, preserve_topology=False)
              Note: shapely uses degrees not meters → convert epsilon
    Option C: reimplement from Java (only ~60 lines)
  COMPLEXITY: ~20 lines (using a library)

normalizeElevationData() — mean bias correction:
  Java: mean_gps = avg(gps_ele); mean_dem = avg(dem_ele)
        corrected = gps + (mean_dem - mean_gps)
  Python:
    offset = np.mean(dem_ele) - np.mean(gps_ele)
    corrected = gps_ele + offset
  COMPLEXITY: ~10 lines, trivial.

getTrackSummary():
  Java: iterate waypoint pairs → haversine distance, elevation gain/loss
  Python: vectorized with numpy diff() and cumsum()
  COMPLEXITY: ~30 lines.

OVERALL GPXWorker COMPLEXITY: ~150 lines Python

───────────────────────────────────────────────────────────────────────────────
CLASS: MapTile  (~100 lines Java)
───────────────────────────────────────────────────────────────────────────────
Java algorithm — Web Mercator tile math:
  lat/lon → tile x/y:
    x = 2^z * (lon/360 + 0.5)
    y = 2^z * (0.5 - ln((1+sin(lat))/(1-sin(lat))) / (4π))

  tile x/y → lat/lon (inverse Mercator):
    n = π - 2π * tile_y / 2^z
    lat = atan(0.5 * (e^n - e^-n)) * 180/π
    lon = tile_x / 2^z * 360 - 180

Python mapping:
  Exact same formulas, ~40 lines. Often already in mapping libraries.
  COMPLEXITY: trivial.

───────────────────────────────────────────────────────────────────────────────
CLASS: GLTFWorker  (~218 lines Java, orchestration)
───────────────────────────────────────────────────────────────────────────────
Java algorithm:
  1. Get tile grid from bbox + zoom
  2. Auto-reduce zoom until tile count ≤ 48
  3. For each tile: load HGT cells, store in MeshHolder
  4. Optional: adjust all heights so minimum = heightOffset
  5. Call GLTFDatafile to generate mesh for each tile

Python mapping:
  def build_gltf(bbox, hgt_dir, z_scale=1.5, height_offset=500,
                 tile_url_template=None, with_enclosure=True):
      tiles = get_tiles_for_bbox(bbox, zoom=14)
      while len(tiles) > 48:
          zoom -= 1; tiles = get_tiles_for_bbox(bbox, zoom)
      meshes = []
      for tile in tiles:
          elev_grid = load_elevation_grid(tile.bbox, ...)
          meshes.append(build_terrain_mesh(elev_grid, tile, ...))
      if with_enclosure:
          meshes.extend(build_enclosure_walls(meshes))
      return assemble_gltf(meshes)

  COMPLEXITY: ~100 lines Python.

───────────────────────────────────────────────────────────────────────────────
CLASS: GLTFDatafile  (~757 lines Java, THE CORE MESH GENERATOR)
───────────────────────────────────────────────────────────────────────────────
This is the most complex class. Full algorithm:

TERRAIN MESH — GLTFMeshTerrain constructor:

  Index buffer (triangles):
    For each grid quad (x,y):
      # upper-left, upper-right, lower-left  (triangle 1, CCW)
      indices += [(y-1)*W+(x-1), (y-1)*W+x, y*W+(x-1)]
      # upper-right, lower-left, lower-right (triangle 2, CCW)
      indices += [(y-1)*W+x,     y*W+(x-1), y*W+x    ]

  Python (vectorized with NumPy):
    x = np.arange(1, W);  y = np.arange(1, H)
    xx, yy = np.meshgrid(x, y)
    t1 = np.stack([(yy-1)*W+(xx-1), (yy-1)*W+xx, yy*W+(xx-1)], axis=-1)
    t2 = np.stack([(yy-1)*W+xx,     yy*W+(xx-1), yy*W+xx    ], axis=-1)
    indices = np.concatenate([t1, t2], axis=-1).reshape(-1)

  Vertex buffer (positions, Y-up convention):
    For y in range(H): y_m = -y * cell_lat_m + offset_y
      For x in range(W): x_m = x * cell_lon_m + offset_x
        vertices[y,x] = [y_m * scale, height[x,y] * scale * z_scale, x_m * scale]
    # Note: X and Y axes swapped (Y-up: axis order is [lat, height, lon])

  Python (vectorized):
    xs = np.arange(W) * cell_lon_m + offset_x       # (W,)
    ys = -np.arange(H) * cell_lat_m + offset_y      # (H,)
    xx, yy = np.meshgrid(xs, ys)                     # (H,W) each
    zz = elev_grid * z_scale * scale_factor          # (H,W)
    # Y-up: [lat_m, height, lon_m]
    verts = np.stack([yy * sf, zz, xx * sf], axis=-1)  # (H,W,3)

  UV texture coordinates:
    x_uv = (x - overlap/2) / (W - 1 - overlap)     # → 0..1, clamped
    y_uv = 1 - (y - overlap/2) / (H - 1 - overlap) # Y flipped, clamped

  Python:
    xs_uv = np.clip((np.arange(W) - ov/2) / (W - 1 - ov), 0, 1)
    ys_uv = np.clip(1 - (np.arange(H) - ov/2) / (H - 1 - ov), 0, 1)
    uu, vv = np.meshgrid(xs_uv, ys_uv)              # (H,W) each
    uvs = np.stack([uu, vv], axis=-1)                # (H,W,2)

ENCLOSURE WALLS — GLTFMeshEnclosement:
  4 walls along bbox edges (N, E, S, W).
  Each wall: 2 vertices per edge cell (bottom at z=0, top at terrain height).
  Wall index buffer: 6 indices per cell pair (same CCW triangle pattern).
  Python: ~80 lines, straightforward loop or vectorized with numpy.

GLTF JSON ASSEMBLY:
  Binary buffers encoded as base64 data URIs.
  Structure: scenes/nodes/meshes/materials/textures/images/
             samplers/buffers/bufferViews/accessors
  Per-mesh extras: tile Z/X/Y, bbox bounds, cell widths in meters.
  Python: use pygltflib OR build dict manually + json.dumps()

  COMPLEXITY: ~150 lines (mostly JSON dict construction).

TOTAL GLTFDatafile: ~300-400 lines of Python (vs 757 Java due to NumPy).
"""

# =============================================================================
# SECTION 3: PYTHON IMPLEMENTATION PLAN
# =============================================================================

PYTHON_IMPLEMENTATION_PLAN = """
PROPOSED MODULE: mytral/gpx_terrain/

  mytral/gpx_terrain/
  ├── __init__.py           # public API: build_gltf(), parse_gpx()
  ├── coordinates.py        # LatLon, BoundingBox, haversine, degree↔meter
  ├── hgt_loader.py         # HGT binary parsing + multi-tile stitching
  ├── gpx_worker.py         # GPX/FIT parsing, RDP simplification, stats
  ├── map_tile.py           # Web Mercator tile math
  ├── mesh_builder.py       # DEM grid → indexed triangle mesh (NumPy)
  ├── gltf_writer.py        # GLTF 2.0 JSON assembly + base64 buffers
  └── terrain_service.py    # High-level: GPX → GLTF (Flask cache wrapper)

NEW DEPENDENCIES (add to pyproject.toml):
  "gpxpy~=1.6",          # GPX XML parsing  (replaces JPX)
  "fitdecode~=0.7",      # Garmin FIT parsing (replaces Garmin SDK)
  "numpy~=2.0",          # mesh math — already transitively present
  "pygltflib~=1.16",     # GLTF 2.0 JSON/binary output
  "requests~=2.32",      # already present — used for map tile fetching

NOT NEEDED (no PostGIS/Java equivalents required):
  - shapely: not needed for the mesh, haversine is custom
  - rasterio: not needed, HGT files are parsed directly with NumPy
  - elevation: not needed, HGT files loaded from local storage

FRONTEND (NO CHANGES NEEDED):
  The Babylon.js code from CubeTrek (/static/js/map3d.js, 18.8 KB) can be
  reused as-is. It expects:
    - GET /api/gltf/{id}.gltf   → GLTF string
    - GET /api/geojson/{id}.geojson → GeoJSON (coords + elevation + time)
    - GET /api/gltf/map/{type}/{z}/{x}/{y}.png → map tile proxy
  All three are Flask routes returning JSON/PNG — straightforward to implement.

SRTM DATA STORAGE (PythonAnywhere considerations):
  CubeTrek stores HGT files locally. Two options:
  Option 1 — On-demand download + local cache (recommended):
    First request for a track downloads only the needed HGT tiles.
    Storage: ~5-20 MB per track bbox (manageable on PythonAnywhere).
    Source: https://e4ftl01.cr.usgs.gov/ or https://opentopography.org/
    Use requests + automatic file naming (N47E011.hgt convention).
  Option 2 — Pre-download region:
    Europe 3DEM: ~1.5 GB  (90m resolution)
    Europe 1DEM: ~12 GB   (30m resolution, probably too large)
    Gives fastest response, but needs storage.
"""

# =============================================================================
# SECTION 4: LINE COUNT AND COMPLEXITY ESTIMATE
# =============================================================================

COMPLEXITY_ESTIMATE = """
MODULE                 JAVA LINES  PYTHON LINES  DIFFICULTY   NOTES
─────────────────────────────────────────────────────────────────────────────
coordinates.py               200           50      TRIVIAL    pure math
hgt_loader.py                500          130      EASY       numpy fromfile
gpx_worker.py                688          150      EASY       gpxpy does heavy lifting
map_tile.py                  100           40      TRIVIAL    Web Mercator formulas
mesh_builder.py              757          300      MEDIUM     numpy vectorization
gltf_writer.py               218          150      EASY       JSON dict + base64
terrain_service.py             -          100      EASY       Flask caching wrapper
─────────────────────────────────────────────────────────────────────────────
TOTAL                      2,463          920      MEDIUM     vs initial "4 weeks HIGH"

Flask routes (GeoJSON, GLTF, tile proxy):
  ~150 lines (new routes in mytral/routes.py or new blueprint)

Jinja template (activity 3D view):
  ~200 lines (copy map3d.js from CubeTrek, adapt Jinja template)

TOTAL NEW CODE:              ~1,270 lines Python + 200 lines HTML/JS

TOKEN ESTIMATE:
  Each module ~200-400 lines → ~1,000-2,000 tokens per module to generate
  Total generation: ~8,000-12,000 tokens (prompting + review)
  Compare to initial "40,000-60,000 tokens" estimate: 4-5× LESS work now
  that all algorithms are known from OSS sources.

DEVELOPMENT TIME ESTIMATE:
  1 developer, TDD with pytest:
  ├── coordinates.py + tests:        0.5 days
  ├── hgt_loader.py + tests:         1.0 day
  ├── gpx_worker.py + tests:         1.0 day
  ├── map_tile.py + tests:           0.5 days
  ├── mesh_builder.py + tests:       2.0 days   ← hardest part
  ├── gltf_writer.py + tests:        1.0 day
  ├── terrain_service.py + routes:   1.0 day
  └── Frontend template:             1.0 day
  TOTAL:                             8 days (2 weeks with review/polish)
"""

# =============================================================================
# SECTION 5: KEY ALGORITHMS — PYTHON CODE SKETCHES
# =============================================================================

ALGORITHM_SKETCHES = '''
# --- coordinates.py ---

import math
import numpy as np

EARTH_RADIUS_M = 6_378_137.0  # OSM standard, matches CubeTrek


def haversine_m(lat1: float, lon1: float, lat2: float, lon2: float) -> float:
    """Haversine distance in meters (exact match to LatLon.java)."""
    dlat = math.radians(lat1 - lat2)
    dlon = math.radians(lon1 - lon2)
    a = math.sin(dlat / 2) ** 2 + math.cos(math.radians(lat1)) * math.cos(math.radians(lat2)) * math.sin(dlon / 2) ** 2
    return EARTH_RADIUS_M * 2 * math.atan2(math.sqrt(a), math.sqrt(1 - a))


def meters_per_degree_lon(lat_deg: float) -> float:
    return EARTH_RADIUS_M * math.cos(math.radians(lat_deg)) * math.pi / 180


METERS_PER_DEGREE_LAT = EARTH_RADIUS_M * math.pi / 180  # ≈ 111,319.5 m


# --- hgt_loader.py ---

import numpy as np
from pathlib import Path


CELLS_3DEM = 1201  # SRTM-3 arc-second, 90m resolution
CELLS_1DEM = 3601  # SRTM-1 arc-second, 30m resolution


def hgt_filename(lat: float, lon: float) -> str:
    """SRTM tile filename for the tile containing (lat, lon)."""
    lat_i = int(math.floor(lat))
    lon_i = int(math.floor(lon))
    ns = "N" if lat_i >= 0 else "S"
    ew = "E" if lon_i >= 0 else "W"
    return f"{ns}{abs(lat_i):02d}{ew}{abs(lon_i):03d}.hgt"


def load_hgt_tile(path: Path, cells: int = CELLS_3DEM) -> np.ndarray:
    """Load one HGT tile. Returns (cells, cells) int16 array, N-to-S, W-to-E."""
    data = np.fromfile(path, dtype=">i2").reshape(cells, cells)
    data = np.where(data < -500, -500, data)  # hole fill (matches Java)
    return data


def get_elevation(data: np.ndarray, lat: float, lon: float,
                  tile_lat: int, tile_lon: int) -> int:
    """Nearest-neighbor elevation query from a loaded HGT tile."""
    cells = data.shape[0]
    cell_size = 1.0 / (cells - 1)
    ix = int((lon - tile_lon) / cell_size)
    iy = int((tile_lat + 1 - lat) / cell_size)
    ix = max(0, min(cells - 1, ix))
    iy = max(0, min(cells - 1, iy))
    return int(data[iy, ix])


# --- mesh_builder.py ---

import numpy as np
import base64
import struct


def build_terrain_mesh(
    elev_grid: np.ndarray,
    offset_x_m: float,
    offset_y_m: float,
    cell_lon_m: float,
    cell_lat_m: float,
    scale_factor: float = 0.0001,
    z_exaggeration: float = 1.5,
    uv_overlap: float = 0.0,
) -> dict:
    """Convert DEM elevation grid to GLTF mesh buffers (matches GLTFDatafile.java).

    Parameters
    ----------
    elev_grid : np.ndarray
        Shape (H, W) elevation values in meters.
    offset_x_m : float
        Horizontal offset from scene center in meters.
    offset_y_m : float
        Vertical offset from scene center in meters.
    cell_lon_m : float
        Cell width in meters (longitude/X direction).
    cell_lat_m : float
        Cell height in meters (latitude/Y direction).
    scale_factor : float
        Global XY scale (CubeTrek default: 0.0001).
    z_exaggeration : float
        Vertical exaggeration (CubeTrek default: 1.5).
    uv_overlap : float
        UV edge overlap correction (matches considerOverlap in Java).

    Returns
    -------
    dict
        {"indices": bytes, "vertices": bytes, "uvs": bytes,
         "index_count": int, "vertex_count": int,
         "min_pos": list, "max_pos": list}
    """
    H, W = elev_grid.shape

    # --- index buffer (CCW triangles matching Java GLTFMeshTerrain) ---
    x = np.arange(1, W)
    y = np.arange(1, H)
    xx, yy = np.meshgrid(x, y)  # (H-1, W-1) each

    ul = (yy - 1) * W + (xx - 1)
    ur = (yy - 1) * W + xx
    ll = yy * W + (xx - 1)
    lr = yy * W + xx

    t1 = np.stack([ul, ur, ll], axis=-1)  # triangle 1
    t2 = np.stack([ur, ll, lr], axis=-1)  # triangle 2
    indices = np.concatenate([t1, t2], axis=-1).reshape(-1).astype(np.uint32)

    # --- vertex buffer (Y-up, matches Java "isZUp=false") ---
    xs_m = np.arange(W) * cell_lon_m + offset_x_m    # (W,)
    ys_m = -np.arange(H) * cell_lat_m + offset_y_m   # (H,) Y-axis flipped

    xx_m, yy_m = np.meshgrid(xs_m, ys_m)              # (H,W)
    zz = elev_grid.astype(float) * scale_factor * z_exaggeration  # (H,W)

    sf = scale_factor
    # Y-up axis order: [lat(y), height(z), lon(x)] — matches CubeTrek Java
    vx = yy_m * sf   # (H,W)
    vy = zz          # (H,W)
    vz = xx_m * sf   # (H,W)
    verts = np.stack([vx, vy, vz], axis=-1).astype(np.float32)  # (H,W,3)

    # --- UV coords (clamped 0..1, Y flipped) ---
    ov = uv_overlap
    us = np.clip((np.arange(W) - ov / 2) / (W - 1 - ov), 0.0, 1.0)
    vs = np.clip(1.0 - (np.arange(H) - ov / 2) / (H - 1 - ov), 0.0, 1.0)
    uu, vv = np.meshgrid(us, vs)                       # (H,W)
    uvs = np.stack([uu, vv], axis=-1).astype(np.float32)  # (H,W,2)

    v_flat = verts.reshape(-1, 3)  # (H*W, 3)
    u_flat = uvs.reshape(-1, 2)    # (H*W, 2)

    return {
        "indices": indices.tobytes(),
        "vertices": v_flat.tobytes(),
        "uvs": u_flat.tobytes(),
        "index_count": int(indices.size),
        "vertex_count": int(H * W),
        "min_pos": v_flat.min(axis=0).tolist(),
        "max_pos": v_flat.max(axis=0).tolist(),
    }
'''

# =============================================================================
# SECTION 6: PHASED IMPLEMENTATION PLAN FOR MYTRAL
# =============================================================================

IMPLEMENTATION_PHASES = """
PREREQUISITE: feat-100/blob-gpx-photos must land first (GPX file storage).

PHASE 1 — Core Python TopoLibrary port  (Week 1)
  ├── coordinates.py   — haversine, degree↔meter  (0.5 d)
  ├── hgt_loader.py    — HGT binary parse + tile stitch  (1 d)
  ├── gpx_worker.py    — GPX/FIT parse, RDP, stats  (1 d)
  ├── map_tile.py      — Web Mercator tile math  (0.5 d)
  └── Tests for all   (pytest, @pytest.mark.mytral)

PHASE 2 — Mesh generation + GLTF output  (Week 2)
  ├── mesh_builder.py  — NumPy DEM→mesh + enclosure walls  (2 d)
  ├── gltf_writer.py   — GLTF 2.0 JSON + base64 buffers  (1 d)
  ├── terrain_service.py — cache wrapper (Flask-Caching)  (0.5 d)
  └── Tests for mesh output (compare vertex counts, valid GLTF)

PHASE 3 — Flask integration + Frontend  (Week 3)
  ├── New blueprint: mytral/blueprints/gpx_uri_space.py
  │     GET /activity/<id>/view3d         → 3D viewer HTML
  │     GET /api/activity/<id>/gltf       → GLTF string
  │     GET /api/activity/<id>/geojson    → GeoJSON track
  │     GET /api/map-tile/<type>/<z>/<x>/<y>.png → tile proxy
  ├── Jinja template: mytral/templates/activity-view3d.html
  │     Reuse Babylon.js map3d.js from CubeTrek (copy to static/)
  │     Adapt template (Jinja variables instead of Thymeleaf)
  └── Link from activity detail page (activity-get.html)

PHASE 4 — Elevation profile chart  (Week 3, parallel)
  ├── Bokeh chart: distance vs. elevation line chart
  │     Data source: GPX points (after Phase 1 gpx_worker.py)
  │     Integrate into existing charts.py pattern
  └── Add to activity detail page alongside existing stats

SRTM DATA PLAN:
  On-demand download approach:
    1. First request for a track triggers HGT tile download
    2. Store in MYTRAL_DATA_DIR/hgt/{resolution}/{filename}.hgt
    3. Cache: once downloaded, never re-downloaded
    4. Source: https://e4ftl01.cr.usgs.gov/MEASURES/SRTMGL3.003/2000.02.11/
    5. Average: 2-4 tiles per track = 5-20 MB per activity area
    6. PythonAnywhere storage: this is fine under normal free/paid quotas
"""

# =============================================================================
# SECTION 7: UPDATED OPTION COMPARISON (post-OSS discovery)
# =============================================================================

OPTIONS_REVISED = """
OPTION  APPROACH                    WOW   EFFORT  VISUAL MATCH   NOTES
────────────────────────────────────────────────────────────────────────────────
  A*    Port TopoLibrary to Python   ★★★★★   3/5    EXACT          ← RECOMMENDED
         + reuse Babylon.js frontend                               (was 5/5 effort
                                                                    before OSS)
  B     Plotly 3D Surface            ★★★★☆   2/5    80% — no       still valid as
                                                     sat texture    quick Phase 1
  C     MapLibre GL 3D terrain       ★★★★☆   2/5    90% — real     valid if no
                                                     map texture    SRTM storage
  D     Folium / Leaflet + plugin    ★★★☆☆   1/5    2D only        good Phase 0
────────────────────────────────────────────────────────────────────────────────

REVISED RECOMMENDATION:
  Option A is now the recommended path (TopoLibrary is OSS, algorithms known).
  ~920 lines of Python, ~8 days, exact visual match to CubeTrek.

  If time is short, start with Option D (Folium 2D map, ~100 lines, 1 day)
  while implementing Option A in parallel.
"""

if __name__ == "__main__":
    print("CubeTrek + TopoLibrary (OSS) → Python / MytraL Analysis")
    print("=" * 70)
    print(OPTIONS_REVISED)
    print(COMPLEXITY_ESTIMATE)
    print(IMPLEMENTATION_PHASES)
