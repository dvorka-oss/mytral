# MyTraL: my training log
#
# Copyright (C) 2015-2026 Martin Dvorak <martin.dvorak@mindforger.com>
#
# This program is free software: you can redistribute it and/or modify
# it under the terms of the GNU Affero General Public License as published by
# the Free Software Foundation, either version 3 of the License, or
# (at your option) any later version.

"""WGS-84 coordinate math matching LatLon.java and LatLonBoundingBox.java.

All distance formulas are exact ports of TopoLibrary's Java implementation
so that bounding box and mesh calculations produce identical results.
"""

import dataclasses
import math

# OSM standard Earth radius used by TopoLibrary (matches LatLon.java)
EARTH_RADIUS_M: float = 6_378_137.0

# Constant: metres per degree of latitude (independent of position)
METERS_PER_DEGREE_LAT: float = EARTH_RADIUS_M * math.pi / 180  # ≈ 111,319.5


def meters_per_degree_lon(lat_deg: float) -> float:
    """Metres per degree of longitude at the given latitude.

    Parameters
    ----------
    lat_deg : float
        Latitude in decimal degrees.

    Returns
    -------
    float
        Metres per degree of longitude at that latitude.
    """
    return EARTH_RADIUS_M * math.cos(math.radians(lat_deg)) * math.pi / 180


def haversine_m(lat1: float, lon1: float, lat2: float, lon2: float) -> float:
    """Great-circle distance in metres (Haversine formula).

    Exact port of LatLon.calculateEuclidianDistance() from TopoLibrary.

    Parameters
    ----------
    lat1 : float
        Latitude of point 1 in decimal degrees.
    lon1 : float
        Longitude of point 1 in decimal degrees.
    lat2 : float
        Latitude of point 2 in decimal degrees.
    lon2 : float
        Longitude of point 2 in decimal degrees.

    Returns
    -------
    float
        Distance in metres.
    """
    dlat = math.radians(lat1 - lat2)
    dlon = math.radians(lon1 - lon2)
    a = (
        math.sin(dlat / 2) ** 2
        + math.cos(math.radians(lat1))
        * math.cos(math.radians(lat2))
        * math.sin(dlon / 2) ** 2
    )
    return EARTH_RADIUS_M * 2 * math.atan2(math.sqrt(a), math.sqrt(1 - a))


def meters_to_degrees_lat(meters: float) -> float:
    """Convert a north-south distance in metres to degrees of latitude.

    Parameters
    ----------
    meters : float
        Distance in metres.

    Returns
    -------
    float
        Equivalent degrees of latitude.
    """
    return meters / METERS_PER_DEGREE_LAT


def meters_to_degrees_lon(meters: float, lat_deg: float) -> float:
    """Convert an east-west distance in metres to degrees of longitude.

    Parameters
    ----------
    meters : float
        Distance in metres.
    lat_deg : float
        Reference latitude in decimal degrees.

    Returns
    -------
    float
        Equivalent degrees of longitude at that latitude.
    """
    return meters / meters_per_degree_lon(lat_deg)


@dataclasses.dataclass
class BoundingBox:
    """Axis-aligned geographic bounding box in WGS-84 decimal degrees.

    Attributes
    ----------
    north : float
        Northern bound (max latitude).
    south : float
        Southern bound (min latitude).
    west : float
        Western bound (min longitude).
    east : float
        Eastern bound (max longitude).
    """

    north: float
    south: float
    west: float
    east: float

    @staticmethod
    def from_center(lat: float, lon: float, half_width_m: float) -> "BoundingBox":
        """Create a bounding box centred on a point with given half-width.

        Matches LatLonBoundingBox(LatLon, width_meters) in TopoLibrary.

        Parameters
        ----------
        lat : float
            Centre latitude in decimal degrees.
        lon : float
            Centre longitude in decimal degrees.
        half_width_m : float
            Half the side length in metres.

        Returns
        -------
        BoundingBox
            The resulting bounding box.
        """
        dlat = meters_to_degrees_lat(half_width_m)
        dlon = meters_to_degrees_lon(half_width_m, lat)
        return BoundingBox(
            north=lat + dlat,
            south=lat - dlat,
            west=lon - dlon,
            east=lon + dlon,
        )

    @staticmethod
    def from_track(
        lats: list[float], lons: list[float], padding_m: float = 500.0
    ) -> "BoundingBox":
        """Create a bounding box enclosing all track points with optional padding.

        Parameters
        ----------
        lats : list[float]
            List of latitude values in decimal degrees.
        lons : list[float]
            List of longitude values in decimal degrees.
        padding_m : float
            Padding distance in metres applied on all four sides.

        Returns
        -------
        BoundingBox
            The padded bounding box.
        """
        center_lat = (max(lats) + min(lats)) / 2
        dlat = meters_to_degrees_lat(padding_m)
        dlon = meters_to_degrees_lon(padding_m, center_lat)
        return BoundingBox(
            north=max(lats) + dlat,
            south=min(lats) - dlat,
            west=min(lons) - dlon,
            east=max(lons) + dlon,
        )

    @property
    def center_lat(self) -> float:
        """Centre latitude of the bounding box."""
        return (self.north + self.south) / 2

    @property
    def center_lon(self) -> float:
        """Centre longitude of the bounding box."""
        return (self.east + self.west) / 2

    @property
    def width_deg_lon(self) -> float:
        """Width of the box in degrees of longitude."""
        return self.east - self.west

    @property
    def height_deg_lat(self) -> float:
        """Height of the box in degrees of latitude."""
        return self.north - self.south

    def width_m(self) -> float:
        """Approximate width of the box in metres at the centre latitude."""
        return self.width_deg_lon * meters_per_degree_lon(self.center_lat)

    def height_m(self) -> float:
        """Approximate height of the box in metres."""
        return self.height_deg_lat * METERS_PER_DEGREE_LAT
