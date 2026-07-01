# MyTraL: my training log
#
# Copyright (C) 2015-2026 Martin Dvorak <martin.dvorak@mindforger.com>
#
# This program is free software: you can redistribute it and/or modify
# it under the terms of the GNU Affero General Public License as published by
# the Free Software Foundation, either version 3 of the License, or
# (at your option) any later version.

"""SRTM HGT tile loading and multi-tile stitching.

Implements the same binary parsing and grid-stitching logic as
HGTFileLoader_LocalStorage.java and HGTWorker.load_3DEM() in TopoLibrary.

HGT file format (NASA SRTM):
  - Big-endian signed 16-bit integers, row-major order
  - 3DEM: 1201×1201 cells, ~90 m resolution
  - 1DEM: 3601×3601 cells, ~30 m resolution
  - File naming: N/S##E/W###.hgt  e.g. N47E011.hgt
  - Covers exactly 1°×1° with one-cell overlap between adjacent tiles
  - Values below -500 indicate voids; clamped to -500 (below Dead Sea ~-430 m)

Downloads are handled automatically by the ``srtm.py`` library which fetches
tiles from NASA/CGIAR mirrors and caches them locally.
"""

import logging
import math
import pathlib

import numpy as np
import srtm

from mytral.gpx_terrain import coordinates

logger = logging.getLogger(__name__)

# SRTM-3 (3 arc-second, ~90 m resolution)
CELLS_3DEM: int = 1201
# SRTM-1 (1 arc-second, ~30 m resolution)
CELLS_1DEM: int = 3601

_VOID_THRESHOLD: int = -500


def _fill_remaining_voids(out_float: np.ndarray) -> np.ndarray:
    """Fill remaining NaN holes by nearest/linear interpolation in 2D."""
    if not np.isnan(out_float).any():
        return out_float

    filled = out_float.copy()
    valid_values = filled[~np.isnan(filled)]
    if valid_values.size == 0:
        return np.zeros_like(filled)

    x_all = np.arange(filled.shape[1], dtype=np.float64)
    for row_i in range(filled.shape[0]):
        row = filled[row_i]
        valid = ~np.isnan(row)
        if not valid.any():
            continue
        filled[row_i] = np.interp(x_all, x_all[valid], row[valid])

    y_all = np.arange(filled.shape[0], dtype=np.float64)
    for col_i in range(filled.shape[1]):
        col = filled[:, col_i]
        valid = ~np.isnan(col)
        if not valid.any():
            continue
        filled[:, col_i] = np.interp(y_all, y_all[valid], col[valid])

    if np.isnan(filled).any():
        fallback = float(np.median(valid_values))
        filled = np.nan_to_num(filled, nan=fallback)

    return filled


def hgt_filename(lat: float, lon: float) -> str:
    """Return the SRTM HGT filename for the 1°×1° tile containing (lat, lon).

    Parameters
    ----------
    lat : float
        Latitude in decimal degrees.
    lon : float
        Longitude in decimal degrees.

    Returns
    -------
    str
        Filename such as ``N47E011.hgt``.
    """
    lat_i = math.floor(lat)
    lon_i = math.floor(lon)
    ns = "N" if lat_i >= 0 else "S"
    ew = "E" if lon_i >= 0 else "W"
    return f"{ns}{abs(lat_i):02d}{ew}{abs(lon_i):03d}.hgt"


def load_hgt_tile(path: pathlib.Path, cells: int = CELLS_3DEM) -> np.ndarray:
    """Load one HGT binary tile into a NumPy array.

    Matches HGTFileLoader_LocalStorage.loadHGT() from TopoLibrary.
    Rows are ordered north-to-south, columns west-to-east.

    Parameters
    ----------
    path : pathlib.Path
        Path to the .hgt file.
    cells : int
        Grid size (1201 for 3DEM, 3601 for 1DEM).

    Returns
    -------
    np.ndarray
        Shape (cells, cells) int16 array of elevation values in metres.

    Raises
    ------
    FileNotFoundError
        If the HGT file does not exist.
    ValueError
        If the file size does not match the expected grid.
    """
    if not path.exists():
        raise FileNotFoundError(f"HGT tile not found: {path}")
    data = np.fromfile(path, dtype=">i2")
    expected = cells * cells
    if data.size != expected:
        raise ValueError(
            f"HGT file {path.name}: expected {expected} values, got {data.size}"
        )
    data = data.reshape(cells, cells)
    # fill voids — matches Java: if height < -500, clamp to -500
    data = np.where(data < _VOID_THRESHOLD, _VOID_THRESHOLD, data)
    return data.astype(np.int16)


def get_elevation(
    tile: np.ndarray,
    lat: float,
    lon: float,
    tile_lat: int,
    tile_lon: int,
) -> int:
    """Nearest-neighbour elevation query from a loaded HGT tile.

    Parameters
    ----------
    tile : np.ndarray
        Shape (cells, cells) array returned by :func:`load_hgt_tile`.
    lat : float
        Query latitude in decimal degrees.
    lon : float
        Query longitude in decimal degrees.
    tile_lat : int
        SW-corner integer latitude of this tile (floor of lat).
    tile_lon : int
        SW-corner integer longitude of this tile (floor of lon).

    Returns
    -------
    int
        Elevation in metres above sea level.
    """
    cells = tile.shape[0]
    cell_size = 1.0 / (cells - 1)
    ix = int((lon - tile_lon) / cell_size)
    iy = int((tile_lat + 1 - lat) / cell_size)
    ix = max(0, min(cells - 1, ix))
    iy = max(0, min(cells - 1, iy))
    return int(tile[iy, ix])


class HgtCache:
    """On-demand SRTM elevation loader backed by the ``srtm.py`` library.

    ``srtm.py`` handles tile discovery, download, and local caching automatically.
    This class wraps it to provide the same interface as before and to keep a
    fast in-memory numpy array cache for tiles used during mesh generation.

    Parameters
    ----------
    hgt_dir : pathlib.Path
        Directory used by ``srtm.py`` to cache downloaded tiles.
    cells : int
        HGT grid size per tile (CELLS_3DEM or CELLS_1DEM). Used only when
        loading pre-existing raw HGT files via ``load_hgt_tile()``.
    """

    def __init__(self, hgt_dir: pathlib.Path, cells: int = CELLS_3DEM) -> None:
        self._hgt_dir = hgt_dir
        self._cells = cells
        # in-memory numpy cache: filename -> ndarray (for raw HGT files)
        self._cache: dict[str, np.ndarray] = {}
        # srtm.py instance (lazy — created on first use)
        self._srtm: srtm.data.GeoElevationData | None = None
        hgt_dir.mkdir(parents=True, exist_ok=True)

    def _get_srtm(self) -> srtm.data.GeoElevationData:
        """Lazily initialise the srtm.py data object."""
        if self._srtm is None:
            self._srtm = srtm.get_data(
                local_cache_dir=str(self._hgt_dir),
                srtm1=False,  # use SRTM-3 (~90 m), smaller files
            )
        return self._srtm

    def load(self, lat: float, lon: float) -> np.ndarray | None:
        """Return the raw HGT tile array if a pre-downloaded .hgt file exists.

        Falls back to None (srtm.py is used for point queries instead).
        """
        filename = hgt_filename(lat, lon)
        if filename in self._cache:
            return self._cache[filename]
        path = self._hgt_dir / filename
        if path.exists():
            try:
                tile = load_hgt_tile(path, self._cells)
                self._cache[filename] = tile
                return tile
            except (FileNotFoundError, ValueError) as exc:
                logger.error(f"failed to load HGT tile {filename}: {exc}")
        return None

    def elevation_at(self, lat: float, lon: float) -> int:
        """Return SRTM elevation in metres at a single point.

        Uses a pre-downloaded raw HGT file when available; falls back to
        ``srtm.py`` which downloads the tile automatically on first access.

        Parameters
        ----------
        lat : float
            Latitude in decimal degrees.
        lon : float
            Longitude in decimal degrees.

        Returns
        -------
        int
            Elevation in metres, or 0 if data is unavailable.
        """
        # fast path: raw HGT file already loaded into numpy cache
        tile = self.load(lat, lon)
        if tile is not None:
            tile_lat = math.floor(lat)
            tile_lon = math.floor(lon)
            return get_elevation(tile, lat, lon, tile_lat, tile_lon)

        # slow path: srtm.py (downloads tile on first call for this region)
        ele = self._get_srtm().get_elevation(lat, lon)
        if ele is None:
            return 0
        ele_i = int(ele)
        if ele_i < _VOID_THRESHOLD:
            return _VOID_THRESHOLD
        return ele_i


def load_elevation_grid(
    bbox: coordinates.BoundingBox,
    cells_lon: int,
    cells_lat: int,
    cache: HgtCache,
) -> np.ndarray:
    """Build a stitched elevation grid covering the bounding box.

    Matches HGTWorker.load_3DEM() multi-tile stitching logic in TopoLibrary.
    Adjacent HGT tiles share one boundary row/column; this is handled by
    reading each tile's sub-region and copying into the output grid.

    SRTM void values (≤ -500 in HGT files, None→0 from srtm.py) are detected
    and filled by iteratively propagating the median of valid neighbours.

    Parameters
    ----------
    bbox : BoundingBox
        Geographic extent to cover.
    cells_lon : int
        Number of grid columns in the output (X / longitude direction).
    cells_lat : int
        Number of grid rows in the output (Y / latitude direction).
    cache : HgtCache
        HGT tile loader.

    Returns
    -------
    np.ndarray
        Shape (cells_lat, cells_lon) int16 elevation grid, north-to-south,
        west-to-east. Void cells are filled with interpolated values.
    """
    out = np.zeros((cells_lat, cells_lon), dtype=np.int16)

    # sample points across the bounding box
    lats = np.linspace(bbox.north, bbox.south, cells_lat)
    lons = np.linspace(bbox.west, bbox.east, cells_lon)

    for row_i, lat in enumerate(lats):
        for col_i, lon in enumerate(lons):
            out[row_i, col_i] = cache.elevation_at(float(lat), float(lon))

    # fill void cells: SRTM voids are ≤ -500; also treat 0 as void when
    # the grid's 90th-percentile elevation exceeds 100 m (coastal areas
    # with real sea-level terrain are left alone)
    void_mask = out <= _VOID_THRESHOLD
    if np.percentile(out, 90) > 100:
        void_mask = void_mask | (out <= 0)
    if not void_mask.any():
        return out

    # iterative median-fill: each pass fills void cells that have ≥ 3 valid
    # neighbours, repeating until no more cells can be filled
    out_float = out.astype(np.float64)
    out_float[void_mask] = np.nan
    max_passes = max(cells_lat, cells_lon)
    for _ in range(max_passes):
        nan_mask = np.isnan(out_float)
        if not nan_mask.any():
            break
        # pad with NaN to handle edges cleanly
        padded = np.pad(out_float, 1, mode="constant", constant_values=np.nan)
        filled_any = False
        for ri in range(1, padded.shape[0] - 1):
            for ci in range(1, padded.shape[1] - 1):
                if not nan_mask[ri - 1, ci - 1]:
                    continue
                window = padded[ri - 1 : ri + 2, ci - 1 : ci + 2]
                valid = window[~np.isnan(window)]
                if len(valid) >= 3:
                    out_float[ri - 1, ci - 1] = float(np.median(valid))
                    filled_any = True
        if not filled_any:
            break

    # robust fallback for large sparse voids where neighbour-count threshold
    # can leave isolated NaNs behind.
    out_float = _fill_remaining_voids(out_float)
    return out_float.astype(np.int16)
