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
"""AWS S3-backed blob store implementation."""

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


class S3BlobStore(BlobStoreAbc):
    """Blob store backed by AWS S3.

    Parameters
    ----------
    bucket : str
        S3 bucket name.
    region : str
        AWS region.
    access_key : str
        AWS access key ID. When empty, boto3 uses the default credential chain.
    secret_key : str
        AWS secret access key.
    session_token : str
        Optional session token for temporary credentials.
    """

    def __init__(
        self,
        bucket: str,
        region: str = "",
        access_key: str = "",
        secret_key: str = "",
        session_token: str = "",
    ) -> None:
        try:
            import boto3  # type: ignore[import-untyped]
        except ImportError as exc:
            raise BlobConfigurationError(
                "boto3 package is required for the S3 blob store. "
                "Install it with: uv sync --group blob-s3"
            ) from exc

        if not bucket:
            raise BlobConfigurationError("S3 bucket must be configured.")

        self._bucket = bucket
        kwargs: dict = {}
        if region:
            kwargs["region_name"] = region
        if access_key and secret_key:
            kwargs["aws_access_key_id"] = access_key
            kwargs["aws_secret_access_key"] = secret_key
        if session_token:
            kwargs["aws_session_token"] = session_token

        self._s3 = boto3.client("s3", **kwargs)

    def _locate_prefix(self, user_id: str, blob_key: str) -> str | None:
        scans = [
            (f"users/{user_id}/activities/", 6),  # activities/<ak>/<kind>/<blob_key>/
            (f"users/{user_id}/profile/", 5),  # profile/<blob_key>/
            (f"users/{user_id}/acoaches/", 6),  # acoaches/<coach_key>/<blob_key>/
            (f"users/{user_id}/gear/", 6),  # gear/<gk>/photos/<blob_key>/
            (f"users/{user_id}/exercises/", 6),  # exercises/<ek>/photos/<blob_key>/
            (f"users/{user_id}/goals/", 6),  # goals/<gk>/photos/<blob_key>/
        ]
        for scan, min_parts in scans:
            paginator = self._s3.get_paginator("list_objects_v2")
            for page in paginator.paginate(
                Bucket=self._bucket, Prefix=scan, Delimiter=""
            ):
                for obj in page.get("Contents", []):
                    name: str = obj["Key"]
                    if not name.endswith(_METADATA_OBJECT_NAME):
                        continue
                    parts = name.split("/")
                    if len(parts) >= min_parts and parts[min_parts - 1] == blob_key:
                        return "/".join(parts[:min_parts]) + "/"
        return None

    def _get_prefix(self, user_id: str, blob_key: str) -> str:
        prefix = self._locate_prefix(user_id, blob_key)
        if prefix is None:
            raise BlobNotFoundError(
                f"Blob '{blob_key}' not found for user '{user_id}'."
            )
        return prefix

    def _read_metadata(self, prefix: str) -> BlobMetadata:
        key = prefix + _METADATA_OBJECT_NAME
        try:
            resp = self._s3.get_object(Bucket=self._bucket, Key=key)
            data = resp["Body"].read()
            return BlobMetadata.from_dict(json.loads(data))
        except Exception as exc:
            raise BlobStoreError(f"Failed to read metadata at '{key}': {exc}") from exc

    def _write_metadata(self, prefix: str, metadata: BlobMetadata) -> None:
        key = prefix + _METADATA_OBJECT_NAME
        data = json.dumps(metadata.to_dict(), indent=2, ensure_ascii=False).encode()
        try:
            self._s3.put_object(
                Bucket=self._bucket,
                Key=key,
                Body=data,
                ContentType="application/json",
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
            self._s3.put_object(
                Bucket=self._bucket,
                Key=data_key,
                Body=payload,
                ContentType=metadata.content_type,
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
        paginator = self._s3.get_paginator("list_objects_v2")
        for page in paginator.paginate(Bucket=self._bucket, Prefix=scan):
            for obj in page.get("Contents", []):
                if not obj["Key"].endswith(_METADATA_OBJECT_NAME):
                    continue
                try:
                    resp = self._s3.get_object(Bucket=self._bucket, Key=obj["Key"])
                    data = resp["Body"].read()
                    meta = BlobMetadata.from_dict(json.loads(data))
                    if kind is not None and meta.kind != kind:
                        continue
                    results.append(meta)
                except Exception:
                    continue

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
            resp = self._s3.get_object(Bucket=self._bucket, Key=key)
            return io.BytesIO(resp["Body"].read())
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

        # collect all objects under the prefix
        keys_to_delete: list[str] = []
        paginator = self._s3.get_paginator("list_objects_v2")
        for page in paginator.paginate(Bucket=self._bucket, Prefix=prefix):
            for obj in page.get("Contents", []):
                keys_to_delete.append(obj["Key"])

        if not keys_to_delete:
            raise BlobNotFoundError(f"No objects found for blob '{blob_key}'.")

        # delete in batches of 1000 (S3 limit)
        batch_size = 1000
        try:
            for i in range(0, len(keys_to_delete), batch_size):
                batch = [{"Key": k} for k in keys_to_delete[i : i + batch_size]]
                self._s3.delete_objects(Bucket=self._bucket, Delete={"Objects": batch})
        except Exception as exc:
            raise BlobStoreError(f"Failed to delete blob objects: {exc}") from exc

        # verify no relics
        remaining_pages = list(
            self._s3.get_paginator("list_objects_v2").paginate(
                Bucket=self._bucket, Prefix=prefix
            )
        )
        remaining = [
            obj["Key"] for page in remaining_pages for obj in page.get("Contents", [])
        ]
        if remaining:
            raise BlobStoreError(
                f"Blob objects still present after deletion: {remaining}. "
                "Manual cleanup required."
            )

    def blob_exists(self, user_id: str, blob_key: str) -> bool:
        return self._locate_prefix(user_id, blob_key) is not None

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
            self._s3.put_object(
                Bucket=self._bucket,
                Key=key,
                Body=data,
                ContentType=content_type,
            )
        except Exception as exc:
            raise BlobStoreError(f"Failed to write variant '{variant}': {exc}") from exc
