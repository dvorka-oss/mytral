# MyTraL: my training log
#
# Copyright (C) 2015-2026 Martin Dvorak <martin.dvorak@mindforger.com>
#
# This program is free software: you can redistribute it and/or modify
# it under the terms of the GNU Affero General Public License as published by
# the Free Software Foundation, either version 3 of the License, or
# (at your option) any later version.

"""DEM elevation grid → indexed triangle mesh generator.

Implements the same algorithms as GLTFDatafile.java in TopoLibrary:
  - GLTFMeshTerrain: terrain surface with CCW triangles, Y-up convention
  - GLTFMeshEnclosement: four vertical boundary walls

All NumPy operations are vectorised equivalents of the Java loops.
"""

import dataclasses

import numpy as np


@dataclasses.dataclass
class MeshBuffers:
    """Raw binary mesh data for one GLTF primitive.

    Attributes
    ----------
    indices : bytes
        Flat uint32 index buffer (triangle list, CCW winding).
    vertices : bytes
        Flat float32 position buffer, 3 floats per vertex [x, y, z].
    normals : bytes
        Flat float32 normal buffer, 3 floats per vertex [nx, ny, nz]. Empty if absent.
    uvs : bytes
        Flat float32 UV buffer, 2 floats per vertex [u, v]. Empty if no texture.
    index_count : int
        Total number of index values.
    vertex_count : int
        Total number of vertices.
    min_pos : list[float]
        Per-component minimum of vertex positions [x, y, z].
    max_pos : list[float]
        Per-component maximum of vertex positions [x, y, z].
    min_uv : list[float]
        Per-component minimum of UV values [u, v].
    max_uv : list[float]
        Per-component maximum of UV values [u, v].
    has_uvs : bool
        True when UV data is present.
    has_normals : bool
        True when normal data is present.
    """

    indices: bytes
    vertices: bytes
    normals: bytes
    uvs: bytes
    index_count: int
    vertex_count: int
    min_pos: list[float]
    max_pos: list[float]
    min_uv: list[float]
    max_uv: list[float]
    has_uvs: bool
    has_normals: bool


def build_terrain_mesh(
    elev_grid: np.ndarray,
    offset_x_m: float,
    offset_y_m: float,
    cell_lon_m: float,
    cell_lat_m: float,
    scale_factor: float = 0.0001,
    z_exaggeration: float = 1.5,
    uv_overlap: float = 0.0,
    with_uvs: bool = True,
) -> MeshBuffers:
    """Convert a DEM elevation grid to triangle mesh buffers.

    Exact port of GLTFDatafile.GLTFMeshTerrain in TopoLibrary.

    Coordinate convention (Y-up, matches CubeTrek Babylon.js):
      vertex = [lat_offset * scale, elevation * scale * z_exag, lon_offset * scale]

    Triangle winding: counter-clockwise (CCW) matching OpenGL / GLTF convention.

    Parameters
    ----------
    elev_grid : np.ndarray
        Shape (H, W) int16 or float elevation values in metres, north-to-south.
    offset_x_m : float
        Longitude offset of the grid's western edge from scene centre, metres.
    offset_y_m : float
        Latitude offset of the grid's northern edge from scene centre, metres.
    cell_lon_m : float
        Width of one grid cell in metres (longitude / X direction).
    cell_lat_m : float
        Height of one grid cell in metres (latitude / Y direction).
    scale_factor : float
        Global XY scale applied to all positions. CubeTrek default: 0.0001.
    z_exaggeration : float
        Vertical exaggeration multiplier. CubeTrek default: 1.5.
    uv_overlap : float
        Fractional edge overlap correction for UV seam handling.
    with_uvs : bool
        Whether to generate UV texture coordinates.

    Returns
    -------
    MeshBuffers
        Binary buffers ready for GLTF assembly.
    """
    H, W = elev_grid.shape
    sf = scale_factor

    # --- index buffer (CCW triangles) ---
    # Each grid quad (x, y) → two triangles matching Java GLTFMeshTerrain:
    #   t1: above_index, across_index, left_index  → [ur, ul, ll]
    #   t2: above_index, left_index, index          → [ur, ll, lr]
    # ul=across, ur=above, ll=left, lr=index  (CubeTrek naming)
    x_idx = np.arange(1, W, dtype=np.uint32)
    y_idx = np.arange(1, H, dtype=np.uint32)
    xx, yy = np.meshgrid(x_idx, y_idx)  # (H-1, W-1)

    ul = (yy - 1) * W + (xx - 1)  # across_index — NW
    ur = (yy - 1) * W + xx  # above_index  — NE
    ll = yy * W + (xx - 1)  # left_index   — SW
    lr = yy * W + xx  # index        — SE

    t1 = np.stack([ur, ul, ll], axis=-1)  # Java: above, across, left
    t2 = np.stack([ur, ll, lr], axis=-1)  # Java: above, left, index
    indices_np = np.concatenate([t1, t2], axis=-1).reshape(-1).astype(np.uint32)

    # --- vertex buffer (Y-up: [lat_m, height, lon_m]) ---
    xs_m = np.arange(W, dtype=np.float32) * cell_lon_m + offset_x_m  # (W,)
    ys_m = -np.arange(H, dtype=np.float32) * cell_lat_m + offset_y_m  # (H,) flipped

    xx_m, yy_m = np.meshgrid(xs_m, ys_m)  # (H, W) each
    zz = elev_grid.astype(np.float32) * sf * z_exaggeration  # (H, W)

    # Y-up axis order: [lat(y), height(z), lon(x)] — CubeTrek convention
    vx = yy_m * sf
    vy = zz
    vz = xx_m * sf
    verts_np = np.stack([vx, vy, vz], axis=-1).reshape(-1, 3)  # (H*W, 3)

    # --- UV coords (clamped 0..1) ---
    # GLTF 2.0 spec: V=0 is at the top-left of the texture image (north for OSM tiles).
    # Row 0 = north edge → V=0; row H-1 = south edge → V=1. No V-flip.
    if with_uvs:
        ov = float(uv_overlap)
        denom_w = max(W - 1 - ov, 1.0)
        denom_h = max(H - 1 - ov, 1.0)
        us = np.clip((np.arange(W, dtype=np.float32) - ov / 2) / denom_w, 0.0, 1.0)
        vs = np.clip((np.arange(H, dtype=np.float32) - ov / 2) / denom_h, 0.0, 1.0)
        uu, vv = np.meshgrid(us, vs)
        uvs_np = np.stack([uu, vv], axis=-1).reshape(-1, 2).astype(np.float32)
        uvs_bytes = uvs_np.tobytes()
        min_uv = uvs_np.min(axis=0).tolist()
        max_uv = uvs_np.max(axis=0).tolist()
    else:
        uvs_bytes = b""
        min_uv = [0.0, 0.0]
        max_uv = [0.0, 0.0]

    # --- smooth vertex normals via central finite differences ---
    # For a height field in Y-up coords [vx=lat*sf, vy=ele*sf*ze, vz=lon*sf]:
    # tangent row-dir (south): [-cell_lat*sf, drow*sf*ze, 0]
    # tangent col-dir (east):  [0, dcol*sf*ze, cell_lon*sf]
    # Normal = T_row × T_col → n = [drow*ze/lat, 1, -dcol*ze/lon], normalised
    elev_f = elev_grid.astype(np.float32)
    drow, dcol = np.gradient(elev_f)  # central diffs, shape (H, W)
    n_x = drow * z_exaggeration / cell_lat_m
    n_y = np.ones_like(n_x)
    n_z = -dcol * z_exaggeration / cell_lon_m
    mag = np.sqrt(n_x**2 + n_y**2 + n_z**2)
    mag = np.maximum(mag, 1e-8)
    n_x /= mag
    n_y /= mag
    n_z /= mag
    normals_np = np.stack([n_x, n_y, n_z], axis=-1).reshape(-1, 3).astype(np.float32)

    return MeshBuffers(
        indices=indices_np.tobytes(),
        vertices=verts_np.tobytes(),
        normals=normals_np.tobytes(),
        uvs=uvs_bytes,
        index_count=int(indices_np.size),
        vertex_count=int(H * W),
        min_pos=verts_np.min(axis=0).tolist(),
        max_pos=verts_np.max(axis=0).tolist(),
        min_uv=min_uv,
        max_uv=max_uv,
        has_uvs=with_uvs,
        has_normals=True,
    )


def build_enclosure_walls(
    elev_grid: np.ndarray,
    offset_x_m: float,
    offset_y_m: float,
    cell_lon_m: float,
    cell_lat_m: float,
    scale_factor: float = 0.0001,
    z_exaggeration: float = 1.5,
) -> list[MeshBuffers]:
    """Build the four vertical enclosure walls around the terrain mesh.

    Matches GLTFDatafile.GLTFMeshEnclosement in TopoLibrary.
    Each wall spans one edge of the bounding box from the terrain surface
    down to z = 0.  No UV coordinates are generated for walls.

    Parameters
    ----------
    elev_grid : np.ndarray
        Shape (H, W) elevation grid used for the terrain surface.
    offset_x_m : float
        Same as passed to :func:`build_terrain_mesh`.
    offset_y_m : float
        Same as passed to :func:`build_terrain_mesh`.
    cell_lon_m : float
        Cell width in metres.
    cell_lat_m : float
        Cell height in metres.
    scale_factor : float
        Global scale factor.
    z_exaggeration : float
        Vertical exaggeration.

    Returns
    -------
    list[MeshBuffers]
        Four wall meshes: [north, east, south, west].
    """
    H, W = elev_grid.shape
    sf = scale_factor

    def _wall_mesh(
        positions: np.ndarray,  # (N, 3) float32 vertices, alternating bottom/top
        n_cells: int,
    ) -> MeshBuffers:
        """Build index buffer for a wall from alternating bottom/top vertices."""
        # 2 verts per cell (bottom=even, top=odd)
        idx: list[int] = []
        for i in range(n_cells - 1):
            b0 = 2 * i
            t0 = 2 * i + 1
            b1 = 2 * (i + 1)
            t1 = 2 * (i + 1) + 1
            idx += [b0, t0, b1, t0, t1, b1]  # CCW
        idx_np = np.array(idx, dtype=np.uint32)
        return MeshBuffers(
            indices=idx_np.tobytes(),
            vertices=positions.tobytes(),
            normals=b"",
            uvs=b"",
            index_count=int(idx_np.size),
            vertex_count=int(len(positions)),
            min_pos=positions.min(axis=0).tolist(),
            max_pos=positions.max(axis=0).tolist(),
            min_uv=[0.0, 0.0],
            max_uv=[0.0, 0.0],
            has_uvs=False,
            has_normals=False,
        )

    walls: list[MeshBuffers] = []

    # north wall (y=0 row of grid, west→east)
    verts: list[list[float]] = []
    for xi in range(W):
        x_m = xi * cell_lon_m + offset_x_m
        y_m = offset_y_m  # north edge
        z_top = float(elev_grid[0, xi]) * sf * z_exaggeration
        verts.append([y_m * sf, 0.0, x_m * sf])
        verts.append([y_m * sf, z_top, x_m * sf])
    walls.append(_wall_mesh(np.array(verts, dtype=np.float32), W))

    # east wall (x=W-1 column, north→south)
    verts = []
    for yi in range(H):
        x_m = (W - 1) * cell_lon_m + offset_x_m
        y_m = -yi * cell_lat_m + offset_y_m
        z_top = float(elev_grid[yi, W - 1]) * sf * z_exaggeration
        verts.append([y_m * sf, 0.0, x_m * sf])
        verts.append([y_m * sf, z_top, x_m * sf])
    walls.append(_wall_mesh(np.array(verts, dtype=np.float32), H))

    # south wall (y=H-1 row, east→west)
    verts = []
    for xi in range(W - 1, -1, -1):
        x_m = xi * cell_lon_m + offset_x_m
        y_m = -(H - 1) * cell_lat_m + offset_y_m
        z_top = float(elev_grid[H - 1, xi]) * sf * z_exaggeration
        verts.append([y_m * sf, 0.0, x_m * sf])
        verts.append([y_m * sf, z_top, x_m * sf])
    walls.append(_wall_mesh(np.array(verts, dtype=np.float32), W))

    # west wall (x=0 column, south→north)
    verts = []
    for yi in range(H - 1, -1, -1):
        x_m = offset_x_m
        y_m = -yi * cell_lat_m + offset_y_m
        z_top = float(elev_grid[yi, 0]) * sf * z_exaggeration
        verts.append([y_m * sf, 0.0, x_m * sf])
        verts.append([y_m * sf, z_top, x_m * sf])
    walls.append(_wall_mesh(np.array(verts, dtype=np.float32), H))

    return walls
