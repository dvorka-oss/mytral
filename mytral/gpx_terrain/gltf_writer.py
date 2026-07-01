# MyTraL: my training log
#
# Copyright (C) 2015-2026 Martin Dvorak <martin.dvorak@mindforger.com>
#
# This program is free software: you can redistribute it and/or modify
# it under the terms of the GNU Affero General Public License as published by
# the Free Software Foundation, either version 3 of the License, or
# (at your option) any later version.

"""GLTF 2.0 JSON document assembly from mesh buffers.

Implements the same output format as GLTFDatafile.getString() in TopoLibrary.
All binary buffers are embedded as base64 data URIs within the JSON document.

GLTF 2.0 structure emitted:
  scenes / nodes / meshes / materials / textures / images / samplers
  buffers / bufferViews / accessors / asset
"""

import base64
import json

from mytral.gpx_terrain import map_tile
from mytral.gpx_terrain import mesh_builder

# GLTF component type constants
_COMPONENT_UINT32: int = 5125  # unsigned int
_COMPONENT_FLOAT32: int = 5126  # float

# GLTF buffer target constants
_TARGET_ARRAY_BUFFER: int = 34962  # vertex / UV data
_TARGET_ELEMENT_ARRAY_BUFFER: int = 34963  # index data

# GLTF texture sampler filter constants
_FILTER_LINEAR: int = 9729
_FILTER_LINEAR_MIPMAP_LINEAR: int = 9987
_WRAP_MIRRORED_REPEAT: int = 33648


def _b64_uri(data: bytes) -> str:
    return "data:application/octet-stream;base64," + base64.b64encode(data).decode()


def assemble_gltf(
    terrain_meshes: list[mesh_builder.MeshBuffers],
    wall_meshes: list[mesh_builder.MeshBuffers],
    tile_metadata: list[dict],
    tile_url_template: str | None = None,
) -> str:
    """Assemble a GLTF 2.0 JSON string from terrain and wall mesh buffers.

    Matches the structure produced by GLTFDatafile.getString() in TopoLibrary.
    One GLTF mesh node is emitted per terrain tile; wall meshes are appended
    as additional un-textured nodes.

    Parameters
    ----------
    terrain_meshes : list[MeshBuffers]
        One mesh per map tile (with UV coords).
    wall_meshes : list[MeshBuffers]
        Four enclosure wall meshes (no UV coords).
    tile_metadata : list[dict]
        Per-tile metadata dicts written to mesh ``extras``.
        Must have the same length as ``terrain_meshes``.
    tile_url_template : str | None
        URL template for map tile textures. Supports ``{z}/{x}/{y}`` or
        ``%d/%d/%d`` (zoom/x/y) placeholders.  When None, no textures are
        embedded and materials are omitted.

    Returns
    -------
    str
        GLTF 2.0 JSON string.
    """
    doc: dict = {
        "asset": {"version": "2.0"},
        "scene": 0,
        "scenes": [{"nodes": []}],
        "nodes": [],
        "meshes": [],
        "buffers": [],
        "bufferViews": [],
        "accessors": [],
    }

    if tile_url_template:
        doc["materials"] = []
        doc["textures"] = []
        doc["images"] = []
        doc["samplers"] = [
            {
                "magFilter": _FILTER_LINEAR,
                "minFilter": _FILTER_LINEAR_MIPMAP_LINEAR,
                "wrapS": _WRAP_MIRRORED_REPEAT,
                "wrapT": _WRAP_MIRRORED_REPEAT,
            }
        ]

    def _add_buffer(data: bytes) -> int:
        idx = len(doc["buffers"])
        doc["buffers"].append({"uri": _b64_uri(data), "byteLength": len(data)})
        return idx

    def _add_buffer_view(buf_idx: int, byte_len: int, target: int) -> int:
        idx = len(doc["bufferViews"])
        doc["bufferViews"].append(
            {
                "buffer": buf_idx,
                "byteOffset": 0,
                "byteLength": byte_len,
                "target": target,
            }
        )
        return idx

    def _add_accessor_scalar(bv_idx: int, count: int, min_v: int, max_v: int) -> int:
        idx = len(doc["accessors"])
        doc["accessors"].append(
            {
                "bufferView": bv_idx,
                "byteOffset": 0,
                "componentType": _COMPONENT_UINT32,
                "count": count,
                "type": "SCALAR",
                "min": [min_v],
                "max": [max_v],
            }
        )
        return idx

    def _add_accessor_vec3(
        bv_idx: int, count: int, min_pos: list, max_pos: list
    ) -> int:
        idx = len(doc["accessors"])
        doc["accessors"].append(
            {
                "bufferView": bv_idx,
                "byteOffset": 0,
                "componentType": _COMPONENT_FLOAT32,
                "count": count,
                "type": "VEC3",
                "min": min_pos,
                "max": max_pos,
            }
        )
        return idx

    def _add_accessor_vec2(bv_idx: int, count: int, min_uv: list, max_uv: list) -> int:
        idx = len(doc["accessors"])
        doc["accessors"].append(
            {
                "bufferView": bv_idx,
                "byteOffset": 0,
                "componentType": _COMPONENT_FLOAT32,
                "count": count,
                "type": "VEC2",
                "min": min_uv,
                "max": max_uv,
            }
        )
        return idx

    def _add_mesh_node(
        buf: mesh_builder.MeshBuffers,
        extras: dict | None = None,
        material_idx: int | None = None,
    ) -> None:
        # index buffer
        idx_buf = _add_buffer(buf.indices)
        idx_bv = _add_buffer_view(
            idx_buf, len(buf.indices), _TARGET_ELEMENT_ARRAY_BUFFER
        )
        idx_acc = _add_accessor_scalar(idx_bv, buf.index_count, 0, buf.vertex_count - 1)

        # vertex buffer
        vert_buf = _add_buffer(buf.vertices)
        vert_bv = _add_buffer_view(vert_buf, len(buf.vertices), _TARGET_ARRAY_BUFFER)
        vert_acc = _add_accessor_vec3(
            vert_bv, buf.vertex_count, buf.min_pos, buf.max_pos
        )

        primitive: dict = {
            "indices": idx_acc,
            "attributes": {"POSITION": vert_acc},
        }

        if buf.has_normals and buf.normals:
            norm_buf = _add_buffer(buf.normals)
            norm_bv = _add_buffer_view(norm_buf, len(buf.normals), _TARGET_ARRAY_BUFFER)
            norm_acc = _add_accessor_vec3(
                norm_bv, buf.vertex_count, [-1.0, -1.0, -1.0], [1.0, 1.0, 1.0]
            )
            primitive["attributes"]["NORMAL"] = norm_acc

        if buf.has_uvs and buf.uvs:
            uv_buf = _add_buffer(buf.uvs)
            uv_bv = _add_buffer_view(uv_buf, len(buf.uvs), _TARGET_ARRAY_BUFFER)
            uv_acc = _add_accessor_vec2(uv_bv, buf.vertex_count, buf.min_uv, buf.max_uv)
            primitive["attributes"]["TEXCOORD_0"] = uv_acc

        if material_idx is not None:
            primitive["material"] = material_idx

        mesh_entry: dict = {"primitives": [primitive]}
        if extras:
            mesh_entry["extras"] = extras

        mesh_idx = len(doc["meshes"])
        doc["meshes"].append(mesh_entry)

        node_idx = len(doc["nodes"])
        doc["nodes"].append({"mesh": mesh_idx})
        doc["scenes"][0]["nodes"].append(node_idx)

    # --- terrain tile meshes ---
    for i, (buf, meta) in enumerate(zip(terrain_meshes, tile_metadata)):
        material_idx: int | None = None

        if tile_url_template and buf.has_uvs:
            tile: map_tile.MapTile = meta.get("_tile")  # type: ignore[assignment]
            if tile is not None:
                img_url = tile.url(tile_url_template)
            else:
                img_url = ""

            img_idx = len(doc["images"])
            doc["images"].append({"uri": img_url})
            tex_idx = len(doc["textures"])
            doc["textures"].append({"sampler": 0, "source": img_idx})
            material_idx = len(doc["materials"])
            # render the map tile mostly UNLIT: most of its colour comes through
            # the emissive channel so the map reads at near-true brightness
            # regardless of slope orientation, while a small lit base term still
            # gives gentle directional relief (CubeTrek look). Avoids the
            # "dark cave" effect of fully re-lighting a flat raster map.
            doc["materials"].append(
                {
                    "pbrMetallicRoughness": {
                        "baseColorTexture": {"index": tex_idx},
                        "baseColorFactor": [0.35, 0.35, 0.35, 1.0],
                        "metallicFactor": 0.0,
                        "roughnessFactor": 1.0,
                    },
                    "emissiveTexture": {"index": tex_idx},
                    "emissiveFactor": [0.85, 0.85, 0.85],
                }
            )

        # strip internal _tile key before writing to GLTF extras
        extras = {k: v for k, v in meta.items() if not k.startswith("_")}
        _add_mesh_node(buf, extras=extras, material_idx=material_idx)

    # --- enclosure wall meshes (no texture) ---
    for buf in wall_meshes:
        _add_mesh_node(buf)

    return json.dumps(doc, separators=(",", ":"))
