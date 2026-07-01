# MyTraL: my training log
#
# Copyright (C) 2015-2026 Martin Dvorak <martin.dvorak@mindforger.com>
#
# This program is free software: you can redistribute it and/or modify
# it under the terms of the GNU Affero General Public License as published by
# the Free Software Foundation, either version 3 of the License, or
# (at your option) any later version.

"""On-disk cache for raster map tiles.

Map tiles (OSM, MapTiler) are fetched once and stored on disk so the 3D
terrain viewer works offline on subsequent loads and does not re-download the
same tiles on every page open. Mirrors the on-disk caching approach used by
``hgt_loader.HgtCache`` for SRTM elevation data.

Tiles are stored as ``<tiles_dir>/<maptype>/<z>/<x>/<y>.tile``. The byte
content is opaque (PNG or JPEG depending on the source); callers track the
mimetype separately.
"""

import pathlib

# only these map styles may be used as a path segment (defence in depth — the
# blueprint already validates, but the cache must never write outside its dir)
_ALLOWED_MAPTYPES: frozenset[str] = frozenset({"osm", "standard", "satellite"})


class TileCache:
    """Filesystem cache for raster map tiles.

    Parameters
    ----------
    tiles_dir : pathlib.Path
        Root directory for cached tiles. Created on construction.
    """

    def __init__(self, tiles_dir: pathlib.Path) -> None:
        self._tiles_dir = tiles_dir
        tiles_dir.mkdir(parents=True, exist_ok=True)

    def _path(self, maptype: str, z: int, x: int, y: int) -> pathlib.Path:
        """Return the on-disk path for a tile (validates maptype and coords)."""
        if maptype not in _ALLOWED_MAPTYPES:
            raise ValueError(f"unknown maptype: {maptype!r}")
        # z, x, y are integers from the route converter — coerce defensively
        return self._tiles_dir / maptype / str(int(z)) / str(int(x)) / f"{int(y)}.tile"

    def get(self, maptype: str, z: int, x: int, y: int) -> bytes | None:
        """Return cached tile bytes, or None on a cache miss.

        Parameters
        ----------
        maptype : str
            Tile style: ``"osm"``, ``"standard"``, or ``"satellite"``.
        z, x, y : int
            Tile coordinates.

        Returns
        -------
        bytes | None
            Tile content, or None if not cached.
        """
        path = self._path(maptype, z, x, y)
        if not path.is_file():
            return None
        return path.read_bytes()

    def put(self, maptype: str, z: int, x: int, y: int, data: bytes) -> None:
        """Store tile bytes on disk (atomic write).

        Parameters
        ----------
        maptype : str
            Tile style: ``"osm"``, ``"standard"``, or ``"satellite"``.
        z, x, y : int
            Tile coordinates.
        data : bytes
            Raw tile content.
        """
        path = self._path(maptype, z, x, y)
        path.parent.mkdir(parents=True, exist_ok=True)
        # write to a temp sibling then rename so readers never see a partial file
        tmp = path.with_suffix(".tile.tmp")
        tmp.write_bytes(data)
        tmp.replace(path)
