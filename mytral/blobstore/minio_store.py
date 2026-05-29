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
"""MinIO-backed blob store implementation."""

import datetime
import io
import json
import typing

from mytral.blobstore._object_store_utils import data_object_name as _data_object_name
from mytral.blobstore._object_store_utils import object_prefix as _object_prefix
from mytral.blobstore.abc import BlobStoreAbc
from mytral.blobstore.exceptions import BlobConfigurationError
from mytral.blobstore.exceptions import BlobConflictError
from mytral.blobstore.exceptions import BlobNotFoundError
from mytral.blobstore.exceptions import BlobStoreError
from mytral.blobstore.models import BLOB_VARIANT_ORIGINAL
from mytral.blobstore.models import BlobMetadata

_METADATA_OBJECT_NAME = "metadata.json"


def _locate_prefix(client, bucket: str, user_id: str, blob_key: str) -> str | None:
    """Scan known prefix patterns to find the blob prefix."""
    scans = [
        (f"users/{user_id}/activities/", 6),  # activities/<ak>/<kind>/<blob_key>/
        (f"users/{user_id}/profile/", 5),  # profile/<blob_key>/
        (f"users/{user_id}/acoaches/", 6),  # acoaches/<coach_key>/<blob_key>/
        (f"users/{user_id}/gear/", 6),  # gear/<gk>/photos/<blob_key>/
        (f"users/{user_id}/exercises/", 6),  # exercises/<ek>/photos/<blob_key>/
        (f"users/{user_id}/goals/", 6),  # goals/<gk>/photos/<blob_key>/
    ]
    for scan_prefix, min_parts in scans:
        try:
            objects = client.list_objects(bucket, prefix=scan_prefix, recursive=True)
            for obj in objects:
                name = obj.object_name
                parts = name.split("/")
                if (
                    len(parts) >= min_parts
                    and parts[min_parts - 1] == blob_key
                    and name.endswith(_METADATA_OBJECT_NAME)
                ):
                    return "/".join(parts[:min_parts]) + "/"
        except Exception:
            pass
    return None


class MinioBlobStore(BlobStoreAbc):
    """Blob store backed by a local MinIO server.

    Parameters
    ----------
    endpoint : str
        MinIO server endpoint, e.g. ``127.0.0.1:9000``.
    access_key : str
        MinIO access key.
    secret_key : str
        MinIO secret key.
    bucket : str
        Bucket name. Created automatically if absent.
    secure : bool
        Whether to use HTTPS.
    """

    def __init__(
        self,
        endpoint: str,
        access_key: str,
        secret_key: str,
        bucket: str = "mytral-blobs",
        secure: bool = False,
    ) -> None:
        try:
            import minio  # type: ignore[import-untyped]
        except ImportError as exc:
            raise BlobConfigurationError(
                "minio package is required for the MinIO blob store. "
                "Install it with: uv sync --group blob-minio"
            ) from exc

        if not endpoint:
            raise BlobConfigurationError("MinIO endpoint must be configured.")

        self._bucket = bucket
        self._client = minio.Minio(
            endpoint,
            access_key=access_key,
            secret_key=secret_key,
            secure=secure,
        )
        self._ensure_bucket()

    def _ensure_bucket(self) -> None:
        try:
            if not self._client.bucket_exists(self._bucket):
                self._client.make_bucket(self._bucket)
        except Exception as exc:
            raise BlobConfigurationError(
                f"Failed to ensure MinIO bucket '{self._bucket}': {exc}"
            ) from exc

    def _get_prefix(self, user_id: str, blob_key: str) -> str:
        prefix = _locate_prefix(self._client, self._bucket, user_id, blob_key)
        if prefix is None:
            raise BlobNotFoundError(
                f"Blob '{blob_key}' not found for user '{user_id}'."
            )
        return prefix

    def _read_metadata(self, prefix: str) -> BlobMetadata:
        key = prefix + _METADATA_OBJECT_NAME
        try:
            response = self._client.get_object(self._bucket, key)
            data = response.read()
            response.close()
            return BlobMetadata.from_dict(json.loads(data))
        except Exception as exc:
            raise BlobStoreError(f"Failed to read metadata at '{key}': {exc}") from exc

    def _write_metadata(self, prefix: str, metadata: BlobMetadata) -> None:
        key = prefix + _METADATA_OBJECT_NAME
        data = json.dumps(metadata.to_dict(), indent=2, ensure_ascii=False).encode()
        try:
            self._client.put_object(
                self._bucket,
                key,
                io.BytesIO(data),
                length=len(data),
                content_type="application/json",
            )
        except Exception as exc:
            raise BlobStoreError(f"Failed to write metadata at '{key}': {exc}") from exc

    #
    # BlobStoreAbc
    #

    def create_blob(
        self,
        metadata: BlobMetadata,
        data_stream: typing.BinaryIO,
    ) -> BlobMetadata:
        if self.blob_exists(metadata.user_id, metadata.blob_key):
            raise BlobConflictError(
                f"Blob '{metadata.blob_key}' already exists for user "
                f"'{metadata.user_id}'."
            )

        prefix = _object_prefix(metadata.user_id, metadata)
        data_key = prefix + _data_object_name(metadata.extension, BLOB_VARIANT_ORIGINAL)

        payload = data_stream.read()
        try:
            self._client.put_object(
                self._bucket,
                data_key,
                io.BytesIO(payload),
                length=len(payload),
                content_type=metadata.content_type,
            )
        except Exception as exc:
            raise BlobStoreError(f"Failed to write blob data: {exc}") from exc

        self._write_metadata(prefix, metadata)
        return metadata

    def get_blob_metadata(self, user_id: str, blob_key: str) -> BlobMetadata:
        prefix = self._get_prefix(user_id, blob_key)
        return self._read_metadata(prefix)

    def list_blobs(
        self,
        user_id: str,
        owner_kind: str,
        owner_key: str,
        kind: str | None = None,
    ) -> list[BlobMetadata]:
        if owner_kind == "activity":
            scan = f"users/{user_id}/activities/{owner_key}/"
        elif owner_kind == "gear":
            scan = f"users/{user_id}/gear/{owner_key}/"
        elif owner_kind == "exercise":
            scan = f"users/{user_id}/exercises/{owner_key}/"
        elif owner_kind == "goal":
            scan = f"users/{user_id}/goals/{owner_key}/"
        else:
            scan = f"users/{user_id}/"

        results: list[BlobMetadata] = []
        try:
            objects = self._client.list_objects(
                self._bucket, prefix=scan, recursive=True
            )
            for obj in objects:
                if not obj.object_name.endswith(_METADATA_OBJECT_NAME):
                    continue
                try:
                    response = self._client.get_object(self._bucket, obj.object_name)
                    data = response.read()
                    response.close()
                    meta = BlobMetadata.from_dict(json.loads(data))
                    if kind is not None and meta.kind != kind:
                        continue
                    results.append(meta)
                except Exception:
                    continue
        except Exception as exc:
            raise BlobStoreError(f"Failed to list blobs: {exc}") from exc

        results.sort(key=lambda m: m.created_at)
        return results

    def open_blob(
        self,
        user_id: str,
        blob_key: str,
        variant: str = BLOB_VARIANT_ORIGINAL,
    ) -> typing.BinaryIO:
        prefix = self._get_prefix(user_id, blob_key)
        meta = self._read_metadata(prefix)
        key = prefix + _data_object_name(meta.extension, variant)
        try:
            response = self._client.get_object(self._bucket, key)
            data = response.read()
            response.close()
            return io.BytesIO(data)
        except Exception as exc:
            raise BlobNotFoundError(
                f"Blob variant '{variant}' not found for key '{blob_key}': {exc}"
            ) from exc

    def update_blob_metadata(
        self,
        user_id: str,
        blob_key: str,
        *,
        name: str,
        description: str,
        keywords: list[str],
        thumbnail_available: bool | None = None,
        width: int | None = None,
        height: int | None = None,
        track_count: int | None = None,
        track_point_count: int | None = None,
        summary_polyline: str | None = None,
        summary_bbox: tuple[float, float, float, float] | None = None,
        full_polyline: str | None = None,
        elevation_profile: list[tuple[float, float]] | None = None,
    ) -> BlobMetadata:
        prefix = self._get_prefix(user_id, blob_key)
        meta = self._read_metadata(prefix)
        meta.name = name
        meta.description = description
        meta.keywords = keywords
        if thumbnail_available is not None:
            meta.thumbnail_available = thumbnail_available
        if width is not None:
            meta.width = width
        if height is not None:
            meta.height = height
        if track_count is not None:
            meta.track_count = track_count
        if track_point_count is not None:
            meta.track_point_count = track_point_count
        if summary_polyline is not None:
            meta.summary_polyline = summary_polyline
        if summary_bbox is not None:
            meta.summary_bbox = summary_bbox
        if full_polyline is not None:
            meta.full_polyline = full_polyline
        if elevation_profile is not None:
            meta.elevation_profile = elevation_profile
        meta.updated_at = datetime.datetime.now(datetime.timezone.utc).isoformat()
        self._write_metadata(prefix, meta)
        return meta

    def delete_blob(self, user_id: str, blob_key: str) -> None:
        prefix = self._get_prefix(user_id, blob_key)

        # list all objects under the prefix
        try:
            objects = list(
                self._client.list_objects(self._bucket, prefix=prefix, recursive=True)
            )
            for obj in objects:
                self._client.remove_object(self._bucket, obj.object_name)
        except Exception as exc:
            raise BlobStoreError(f"Failed to delete blob objects: {exc}") from exc

        # verify no relics remain
        remaining = list(
            self._client.list_objects(self._bucket, prefix=prefix, recursive=True)
        )
        if remaining:
            names = [o.object_name for o in remaining]
            raise BlobStoreError(
                f"Blob objects still present after deletion: {names}. "
                "Manual cleanup required."
            )

    def blob_exists(self, user_id: str, blob_key: str) -> bool:
        return _locate_prefix(self._client, self._bucket, user_id, blob_key) is not None

    def write_blob_variant(
        self,
        user_id: str,
        blob_key: str,
        variant: str,
        data: bytes,
        content_type: str = "image/jpeg",
    ) -> None:
        """Write a derived image variant object (normalized or thumbnail)."""
        prefix = self._get_prefix(user_id, blob_key)
        meta = self._read_metadata(prefix)
        key = prefix + _data_object_name(meta.extension, variant)
        try:
            self._client.put_object(
                self._bucket,
                key,
                io.BytesIO(data),
                length=len(data),
                content_type=content_type,
            )
        except Exception as exc:
            raise BlobStoreError(f"Failed to write variant '{variant}': {exc}") from exc
