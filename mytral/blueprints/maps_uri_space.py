# MyTraL: my trailing log
#
# Copyright (C) 2015-2026 Martin Dvorak <martin.dvorak@mindforger.com>
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
import flask

from mytral import app_user_ds as ds
from mytral.backends import entities as entities_mod
from mytral.blobstore import exceptions as blob_exceptions
from mytral.routes import _blob_service
from mytral.routes import COOKIE_USER
from mytral.routes import flask_app


@flask_app.route("/api/activities/<activity_key>/track-data", methods=["GET"])
def api_activity_track_data(activity_key: str):
    """Return GPX map payload for the first GPX recording of the activity."""
    user_id = flask.session.get(COOKIE_USER)
    if not user_id:
        return flask.abort(401)

    user_profile = ds.profile(user_id)
    try:
        activity = ds.get_activity(
            user_id=user_id,
            dataset_name=user_profile.dataset_name,
            key=activity_key,
        )
    except ValueError:
        return flask.abort(404)

    gpx_entry = None
    for entry in activity.recorded_blob_keys:
        ext = entities_mod.recording_ext(entry)
        if ext in (".gpx", ".tcx"):
            gpx_entry = entry
            break

    if gpx_entry is None:
        return flask.abort(404)

    blob_uuid = entities_mod.recording_blob_uuid(gpx_entry)
    try:
        meta = _blob_service().ensure_gpx_map_data(
            user_id=user_id,
            activity_key=activity_key,
            blob_key=blob_uuid,
        )
    except (blob_exceptions.BlobStoreError, blob_exceptions.BlobValidationError):
        return flask.abort(500)

    if not meta.summary_polyline:
        return flask.abort(404)

    return flask.jsonify(
        {
            "summary_polyline": meta.summary_polyline,
            "full_polyline": meta.full_polyline,
            "summary_bbox": list(meta.summary_bbox) if meta.summary_bbox else None,
            "track_point_count": meta.track_point_count,
        }
    )
