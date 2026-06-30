# MyTraL: my training log
#
# Copyright (C) 2015-2026 Martin Dvorak <martin.dvorak@mindforger.com>
#
# This program is free software: you can redistribute it and/or modify
# it under the terms of the GNU Affero General Public License as published by
# the Free Software Foundation, either version 3 of the License, or
# (at your option) any later version.

"""GPX terrain visualisation package.

Provides 3D terrain mesh generation from GPX activity files, matching the
visual output of CubeTrek (https://cubetrek.com) using Babylon.js on the
frontend and pure Python + NumPy on the backend.

Public API
----------
TerrainService
    High-level service: GPX stream → GLTF string / GeoJSON string.

Sub-modules
-----------
coordinates
    WGS-84 coordinate math (haversine, degree↔metre, BoundingBox).
hgt_loader
    SRTM HGT binary tile loading, multi-tile stitching, on-demand download.
gpx_worker
    GPX / FIT parsing, RDP simplification, track statistics.
map_tile
    Web Mercator tile conversions, auto-zoom selection.
mesh_builder
    DEM grid → indexed triangle mesh (NumPy, CCW winding, Y-up).
gltf_writer
    GLTF 2.0 JSON assembly with base64-encoded binary buffers.
terrain_service
    Orchestration: parse → load elevation → build mesh → assemble GLTF.
"""

from mytral.gpx_terrain.terrain_service import TerrainService

__all__ = ["TerrainService"]
