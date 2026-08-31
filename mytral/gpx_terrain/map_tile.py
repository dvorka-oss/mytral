# MyTraL: my training log
#
# Copyright (C) 2015-2026 Martin Dvorak <martin.dvorak@mindforger.com>
#
# This program is free software: you can redistribute it and/or modify
# it under the terms of the GNU Affero General Public License as published by
# the Free Software Foundation, either version 3 of the License, or
# (at your option) any later version.

"""Web Mercator tile coordinate conversions and tile grid utilities.

Implements the same formulas as MapTile.java in TopoLibrary.
All tile coordinates use the standard XYZ (Slippy Map) convention.
"""

import dataclasses
import math

from mytral.gpx_terrain import coordinates


@dataclasses.dataclass(frozen=True)
class MapTile:
    """A single Web Mercator map tile.

    Attributes
    ----------
    zoom : int
        Zoom level (0 = whole world in one tile).
    x : int
        Tile column (west-to-east).
    y : int
        Tile row (north-to-south).
    """

    zoom: int
    x: int
    y: int

    @staticmethod
    def from_latlon(lat: float, lon: float, zoom: int) -> "MapTile":
        """Convert a WGS-84 coordinate to the containing tile.

        Exact port of MapTile(zoom, latLon) constructor in TopoLibrary.

        Parameters
        ----------
        lat : float
            Latitude in decimal degrees.
        lon : float
            Longitude in decimal degrees.
        zoom : int
            Tile zoom level.

        Returns
        -------
        MapTile
            The tile containing the given coordinate.
        """
        z2 = 2**zoom
        sin_lat = math.sin(math.radians(lat))
        tx = z2 * (lon / 360.0 + 0.5)
        ty = z2 * (0.5 - math.log((1 + sin_lat) / (1 - sin_lat)) / (4 * math.pi))
        return MapTile(zoom=zoom, x=int(tx % z2), y=int(ty))

    def bbox(self) -> coordinates.BoundingBox:
        """Return the geographic bounding box of this tile.

        Exact port of MapTile.getLatLon() inverse Mercator from TopoLibrary.

        Returns
        -------
        BoundingBox
            The tile's bounding box in WGS-84 decimal degrees.
        """
        z2 = 2**self.zoom

        def tile_lon(tx: int) -> float:
            return tx / z2 * 360.0 - 180.0

        def tile_lat(ty: int) -> float:
            n = math.pi - 2 * math.pi * ty / z2
            return math.degrees(math.atan(0.5 * (math.exp(n) - math.exp(-n))))

        return coordinates.BoundingBox(
            north=tile_lat(self.y),
            south=tile_lat(self.y + 1),
            west=tile_lon(self.x),
            east=tile_lon(self.x + 1),
        )

    def url(self, template: str) -> str:
        """Format a tile URL from a template.

        Parameters
        ----------
        template : str
            URL template with ``{z}``, ``{x}``, ``{y}`` placeholders,
            or printf-style ``%d/%d/%d`` (z/x/y order, CubeTrek style).

        Returns
        -------
        str
            Formatted tile URL.
        """
        if "{z}" in template:
            return template.format(z=self.zoom, x=self.x, y=self.y)
        # CubeTrek-style printf: %d/%d/%d = zoom/x/y
        return template % (self.zoom, self.x, self.y)


def tiles_for_bbox(bbox: coordinates.BoundingBox, zoom: int) -> list[MapTile]:
    """Return all tiles that overlap the given bounding box at a zoom level.

    Parameters
    ----------
    bbox : BoundingBox
        Geographic extent to cover.
    zoom : int
        Tile zoom level.

    Returns
    -------
    list[MapTile]
        All overlapping tiles, ordered west-to-east then north-to-south.
    """
    nw = MapTile.from_latlon(bbox.north, bbox.west, zoom)
    se = MapTile.from_latlon(bbox.south, bbox.east, zoom)
    tiles = []
    for ty in range(nw.y, se.y + 1):
        for tx in range(nw.x, se.x + 1):
            tiles.append(MapTile(zoom=zoom, x=tx, y=ty))
    return tiles


def auto_zoom(
    bbox: coordinates.BoundingBox, max_tiles: int = 48, start_zoom: int = 14
) -> tuple[int, list[MapTile]]:
    """Select the highest zoom level that stays within the tile count limit.

    Matches the auto-zoom logic in GLTFWorker.java (starts at 14, decrements
    until tile count ≤ max_tiles).

    Parameters
    ----------
    bbox : BoundingBox
        Geographic extent to cover.
    max_tiles : int
        Maximum number of tiles (CubeTrek default: 48).
    start_zoom : int
        Starting zoom level.

    Returns
    -------
    tuple[int, list[MapTile]]
        Selected zoom level and the corresponding tile list.
    """
    zoom = start_zoom
    while zoom > 0:
        tiles = tiles_for_bbox(bbox, zoom)
        if len(tiles) <= max_tiles:
            return zoom, tiles
        zoom -= 1
    tiles = tiles_for_bbox(bbox, zoom)
    return zoom, tiles
