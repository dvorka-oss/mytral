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
"""Shared helpers for object-storage backends (S3 and MinIO)."""

from mytral.blobstore.models import BLOB_VARIANT_NORMALIZED
from mytral.blobstore.models import BLOB_VARIANT_ORIGINAL
from mytral.blobstore.models import BLOB_VARIANT_THUMBNAIL
from mytral.blobstore.models import BlobKind
from mytral.blobstore.models import BlobMetadata


def object_prefix(user_id: str, metadata: BlobMetadata) -> str:
    """Return the object key prefix for a blob.

    Parameters
    ----------
    user_id : str
        Owning user identifier.
    metadata : BlobMetadata
        Blob metadata (``kind``, ``owner_key``, and ``blob_key`` are used).

    Returns
    -------
    str
        Prefix string ending with ``/``, e.g.
        ``users/<uid>/activities/<ak>/photos/<blob_key>/``.
    """
    if metadata.kind == BlobKind.ACTIVITY_RECORDING.value:
        sub = "recordings"
        return (
            f"users/{user_id}/activities/{metadata.owner_key}/"
            f"{sub}/{metadata.blob_key}/"
        )
    if metadata.kind == BlobKind.ACTIVITY_PARQUET.value:
        sub = "parquet"
        return (
            f"users/{user_id}/activities/{metadata.owner_key}/"
            f"{sub}/{metadata.blob_key}/"
        )
    if metadata.kind == BlobKind.ACTIVITY_PHOTO.value:
        sub = "photos"
        return (
            f"users/{user_id}/activities/{metadata.owner_key}/"
            f"{sub}/{metadata.blob_key}/"
        )
    if metadata.kind == BlobKind.USER_AVATAR.value:
        return f"users/{user_id}/profile/{metadata.blob_key}/"
    if metadata.kind == BlobKind.ACOACH_AVATAR.value:
        return f"users/{user_id}/acoaches/{metadata.owner_key}/{metadata.blob_key}/"
    if metadata.kind == BlobKind.GEAR_PHOTO.value:
        return f"users/{user_id}/gear/{metadata.owner_key}/photos/{metadata.blob_key}/"
    if metadata.kind == BlobKind.EXERCISE_PHOTO.value:
        return (
            f"users/{user_id}/exercises/{metadata.owner_key}/photos"
            f"/{metadata.blob_key}/"
        )
    if metadata.kind == BlobKind.GOAL_PHOTO.value:
        return f"users/{user_id}/goals/{metadata.owner_key}/photos/{metadata.blob_key}/"
    # generic fallback for unknown kinds
    return (
        f"users/{user_id}/activities/{metadata.owner_key}/"
        f"{metadata.kind}/{metadata.blob_key}/"
    )


def data_object_name(extension: str, variant: str) -> str:
    """Return the object name for a blob data file within its prefix.

    Parameters
    ----------
    extension : str
        File extension including leading dot, e.g. ``.jpg``.
    variant : str
        Blob variant constant (``original``, ``normalized``, or ``thumbnail``).

    Returns
    -------
    str
        Object name, e.g. ``normalized.jpg`` or ``thumbnail.jpg``.
    """
    if variant in (BLOB_VARIANT_ORIGINAL, BLOB_VARIANT_NORMALIZED):
        # recordings/parquet: keep a stable canonical filename
        if extension in (".fit", ".gpx", ".hrm", ".parquet"):
            return f"data{extension}"
        # photos: normalized bytes are the only stored object
        return f"normalized{extension if extension != '.jpeg' else '.jpg'}"
    if variant == BLOB_VARIANT_THUMBNAIL:
        # thumbnails are always stored as JPEG regardless of source format;
        # this keeps the serving path simple and avoids per-format special-casing
        return "thumbnail.jpg"
    return f"{variant}{extension}"
