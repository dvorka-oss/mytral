# MyTraL: my trailing log
#
# Copyright (C) 2022-2026 Martin Dvorak <martin.dvorak@mindforger.com>
#
# This program is free software: you can redistribute it and/or modify
# it under the terms of the GNU Affero General Public License as published by
# the Free Software Foundation, either version 3 of the License, or
# (at your option) any later version.
#
# This program is distributed in the hope that it will be useful,
# but WITHOUT ANY WARRANTY; without even the implied warranty of
# MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the
# GNU Affero General Public License for more details.
#
# You should have received a copy of the GNU Affero General Public License
# along with this program. If not, see <http://www.gnu.org/licenses/>.

"""
3D terrain viewer routes for GPX recordings.

URL scheme
----------
Page  : GET /app/activities/<key>/view3d
API   : GET /api/terrain/<key>.geojson
        GET /api/terrain/<key>.gltf          (accepts ?maptype=osm|standard|satellite)
        GET /api/terrain/tiles/<maptype>/<z>/<x>/<y>.png  (tile proxy, avoids CORS)
"""

import io
import os

import flask
import PIL.Image
import requests

import mytral
from mytral import app_config
from mytral import app_logger as logger
from mytral import app_user_ds as ds
from mytral import blobstore as blob_pkg
from mytral.blobstore import activity_service as blob_svc_module
from mytral.gpx_terrain import gpx_worker
from mytral.gpx_terrain import TerrainService
from mytral.gpx_terrain import tile_cache as tile_cache_module
from mytral.recordings import parquet_converter
from mytral.routes import COOKIE_USER
from mytral.routes import flask_app

# MapTiler API key is optional — OSM is used when the key is absent.
_MAPTILER_KEY: str = os.environ.get("MYTRAL_MAPTILER_KEY", "")

# Lazy singletons: created once on first request.
_terrain_svc: TerrainService | None = None
_tile_cache: tile_cache_module.TileCache | None = None


def _svc() -> TerrainService:
    """Return (or lazily create) the shared TerrainService singleton."""
    global _terrain_svc
    if _terrain_svc is None:
        hgt_dir = app_config.persistence_data_dir / "hgt"
        _terrain_svc = TerrainService(
            hgt_dir=hgt_dir,
            maptiler_key=_MAPTILER_KEY,
            tile_proxy_base="/api/terrain/tiles",
        )
    return _terrain_svc


def _tiles() -> tile_cache_module.TileCache:
    """Return (or lazily create) the shared on-disk map-tile cache.

    Tiles live under the purgeable cache dir so they survive restarts (offline
    support) but can be cleared at any time.
    """
    global _tile_cache
    if _tile_cache is None:
        _tile_cache = tile_cache_module.TileCache(
            app_config.paths.work_path / "map_tiles"
        )
    return _tile_cache


def _blob_service() -> blob_svc_module.ActivityBlobService:
    """Return an ActivityBlobService bound to the global blobstore and dataset."""
    return blob_svc_module.ActivityBlobService(
        store=mytral.app_blobstore,
        dataset=ds,
        config=app_config,
    )


def _require_user() -> str | None:
    """Return the logged-in user_id, or None if not authenticated."""
    return flask.session.get(COOKIE_USER)


# ---------------------------------------------------------------------------
# Page route
# ---------------------------------------------------------------------------


@flask_app.route(
    "/app/activities/<activity_key>/view3d",
    methods=["GET"],
)
def activity_view3d(activity_key: str):
    """Render the 3D terrain viewer page for an activity."""
    user_id = _require_user()
    if not user_id:
        return flask.redirect(flask.url_for("login"))

    blob_svc = _blob_service()
    if not _has_gpx(blob_svc, user_id, activity_key):
        flask.flash("No GPX recording attached to this activity.", "warning")
        return flask.redirect(flask.url_for("get_activity", key=activity_key))

    maptype = flask.request.args.get("maptype", "osm")
    if maptype not in ("osm", "standard", "satellite"):
        maptype = "osm"

    return flask.render_template(
        "activity-view3d.html",
        user_profile=ds.profile(user_id),
        activity_key=activity_key,
        maptype=maptype,
        maptiler_available=bool(_MAPTILER_KEY),
    )


# ---------------------------------------------------------------------------
# GeoJSON API
# ---------------------------------------------------------------------------


@flask_app.route(
    "/api/terrain/<activity_key>.geojson",
    methods=["GET"],
)
def terrain_geojson(activity_key: str):
    """Return the GeoJSON track for a 3D terrain viewer."""
    user_id = _require_user()
    if not user_id:
        return flask.abort(401)

    blob_svc = _blob_service()
    points = _load_track_points(blob_svc, user_id, activity_key)
    if not points:
        return flask.abort(404)

    svc = _svc()
    try:
        geojson = svc.build_geojson(points)
    except Exception as exc:
        logger.warning(f"terrain: geojson build failed for {activity_key}: {exc}")
        return flask.abort(500)

    return flask.Response(
        geojson,
        mimetype="application/geo+json",
        headers={"Cache-Control": "private, max-age=300"},
    )


# ---------------------------------------------------------------------------
# GLTF API
# ---------------------------------------------------------------------------


@flask_app.route(
    "/api/terrain/<activity_key>.gltf",
    methods=["GET"],
)
def terrain_gltf(activity_key: str):
    """Return the GLTF terrain mesh for a 3D terrain viewer.

    Query params
    ------------
    maptype : str
        ``osm`` (default), ``standard`` (MapTiler), or ``satellite`` (MapTiler).
    """
    user_id = _require_user()
    if not user_id:
        return flask.abort(401)

    maptype = flask.request.args.get("maptype", "osm")
    if maptype not in ("osm", "standard", "satellite"):
        maptype = "osm"
    # satellite requires a MapTiler key; fall back to OSM silently
    if maptype in ("standard", "satellite") and not _MAPTILER_KEY:
        maptype = "osm"

    blob_svc = _blob_service()
    points = _load_track_points(blob_svc, user_id, activity_key)
    if not points:
        return flask.abort(404)

    svc = _svc()
    try:
        gltf_json = svc.build_gltf(
            activity_key=activity_key,
            points=points,
            tile_type=maptype,
            with_enclosure=True,
        )
    except Exception as exc:
        logger.warning(f"terrain: gltf build failed for {activity_key}: {exc}")
        return flask.abort(500)

    return flask.Response(
        gltf_json,
        mimetype="model/gltf+json",
        headers={"Cache-Control": "private, max-age=300"},
    )


# ---------------------------------------------------------------------------
# Tile proxy (avoids CORS between the browser and tile CDNs)
# ---------------------------------------------------------------------------

_TILE_TIMEOUT_S = 10
_TILE_URLS: dict[str, str] = {
    "osm": "https://tile.openstreetmap.org/{z}/{x}/{y}.png",
    "standard": f"https://api.maptiler.com/maps/basic/{{z}}/{{x}}/{{y}}.png?key={_MAPTILER_KEY}",
    "satellite": f"https://api.maptiler.com/tiles/satellite-v2/{{z}}/{{x}}/{{y}}.jpg?key={_MAPTILER_KEY}",
}
_TILE_MIMETYPES: dict[str, str] = {
    "osm": "image/png",
    "standard": "image/png",
    "satellite": "image/jpeg",
}

# lazily-built muted grey-green placeholder, served when a tile cannot be
# fetched so a single missing tile never aborts the whole GLTF texture load
_placeholder_png: bytes | None = None


def _placeholder_tile() -> bytes:
    """Return a solid placeholder PNG tile (built once, then cached)."""
    global _placeholder_png
    if _placeholder_png is None:
        img = PIL.Image.new("RGB", (256, 256), (150, 156, 150))
        buf = io.BytesIO()
        img.save(buf, format="PNG")
        _placeholder_png = buf.getvalue()
    return _placeholder_png


@flask_app.route(
    "/api/terrain/tiles/<maptype>/<int:z>/<int:x>/<int:y>.png",
    methods=["GET"],
)
def terrain_tile_proxy(maptype: str, z: int, x: int, y: int):
    """Proxy a map tile to avoid browser CORS restrictions.

    This lets terrain3d.js load tiles from OSM or MapTiler through the
    MytraL server, so the Babylon.js engine can use them as textures.
    """
    user_id = _require_user()
    if not user_id:
        return flask.abort(401)

    if maptype not in _TILE_URLS:
        return flask.abort(400)
    if maptype in ("standard", "satellite") and not _MAPTILER_KEY:
        return flask.abort(403)

    # serve from the on-disk cache when available (offline support, no refetch)
    cache = _tiles()
    content = cache.get(maptype, z, x, y)
    if content is None:
        template = _TILE_URLS[maptype]
        url = template.format(z=z, x=x, y=y)
        try:
            resp = requests.get(
                url,
                timeout=_TILE_TIMEOUT_S,
                headers={"User-Agent": "MytraL/1.0 (mytral.fitness; training log)"},
            )
            resp.raise_for_status()
        except Exception as exc:
            # degrade gracefully: a placeholder keeps the 3D scene intact even
            # when a single tile is unreachable (offline, CDN hiccup, 404)
            logger.warning(f"terrain: tile proxy error {url}: {exc}")
            return flask.Response(
                _placeholder_tile(),
                mimetype="image/png",
                headers={"Cache-Control": "no-store"},
            )
        content = resp.content
        cache.put(maptype, z, x, y, content)

    return flask.Response(
        content,
        mimetype=_TILE_MIMETYPES[maptype],
        headers={
            "Cache-Control": "public, max-age=86400",
        },
    )


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


# recording formats that carry a GPS track and can be normalized to Parquet
_TRACK_EXTS: tuple[str, ...] = (".gpx", ".fit", ".tcx")


def _has_gpx(
    svc: blob_svc_module.ActivityBlobService, user_id: str, activity_key: str
) -> bool:
    """Return True if the activity has a GPX/FIT/TCX recording attached."""
    try:
        recordings = svc.list_recordings(user_id, activity_key)
        for r in recordings:
            if r.extension.lower() in _TRACK_EXTS:
                return True
        return False
    except Exception:
        return False


def _raw_to_parquet(extension: str, data: bytes) -> bytes | None:
    """Normalize a raw recording to Parquet via the canonical converter."""
    ext = extension.lower()
    if ext == ".gpx":
        return parquet_converter.gpx_to_parquet(data)
    if ext == ".fit":
        return parquet_converter.fit_to_parquet(data)
    if ext == ".tcx":
        return parquet_converter.tcx_to_parquet(data)
    return None


def _load_track_points(
    svc: blob_svc_module.ActivityBlobService, user_id: str, activity_key: str
) -> list[gpx_worker.TrackPoint]:
    """Return the activity's GPS track points from its normalized Parquet.

    Reuses the canonical recording pipeline: prefers the stored normalized
    Parquet (generated at import) and regenerates it from the raw recording via
    the shared converter when missing. Returns an empty list when the activity
    has no usable GPS recording.
    """
    try:
        recordings = svc.list_recordings(user_id, activity_key)
    except Exception:
        return []

    for r in recordings:
        if r.extension.lower() not in _TRACK_EXTS:
            continue
        try:
            opened = svc.open_parquet(user_id, activity_key, r.blob_key)
            if opened is not None:
                stream, _ = opened
                parquet_bytes = stream.read()
            else:
                raw_stream, _ = svc.open_recording(user_id, activity_key, r.blob_key)
                parquet_bytes = _raw_to_parquet(r.extension, raw_stream.read())
        except (blob_pkg.BlobValidationError, blob_pkg.BlobNotFoundError):
            continue
        if not parquet_bytes:
            continue
        points = gpx_worker.points_from_parquet(parquet_bytes)
        if points:
            return points
    return []
