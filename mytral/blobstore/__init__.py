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

"""Blob store package for MyTraL activity attachmentsL photos, TCX/GPX/* recordings,...

$MYTRAL_DATA_DIR/data/[user UUID]/
  blobs/

    acoaches/
      ...

    activities/
      [UUID]/                    ... BLOBs for activity
        parquet/
          [UUID]/
            metadata.json
              ... blob key, user ID, filename, ext, size, SHA, name, descr, ...
            normalized.parquet
        recordings/
          [UUID]/
            metadata.json
            data.gpx
        photos/
          [UUID]/
            metadata.json
            normalized.jpg
            thumbnail.jpg

    exercises/
      ...

    gear/
      ...

    goals/
      ...

    profile/
      [UUID]/                    ... avatar BLOBs for user profile
        metadata.json            ... same as metadata above
        normalized.jpg
        thumbnail.jpg

    misc/                        ... FALLBACK
        [UUID]/
            [BLOB metadata kind like activity_parquet, photo, ...]
              ...

    ...

    parquet/                     ... TODO possibly misplaced for 3D IR model
      [UUID]/
        metadata.json
        normalized.parquet

    photos/
      [UUID]/                    ... avatar BLOBs for user profile
        metadata.json            ... same as metadata above
        normalized.jpg
        thumbnail.jpg

"""

from mytral.blobstore.abc import BlobStoreAbc
from mytral.blobstore.avatar_service import AvatarBlobService
from mytral.blobstore.entity_photo_service import EntityPhotoService
from mytral.blobstore.exceptions import BlobConfigurationError
from mytral.blobstore.exceptions import BlobConflictError
from mytral.blobstore.exceptions import BlobNotFoundError
from mytral.blobstore.exceptions import BlobStoreError
from mytral.blobstore.exceptions import BlobValidationError
from mytral.blobstore.models import BLOB_VARIANT_NORMALIZED
from mytral.blobstore.models import BLOB_VARIANT_ORIGINAL
from mytral.blobstore.models import BLOB_VARIANT_THUMBNAIL
from mytral.blobstore.models import BlobKind
from mytral.blobstore.models import BlobMetadata
from mytral.blobstore.models import BlobOwnerKind
from mytral.blobstore.models import BlobRecord
from mytral.config import BlobStoreType


def create_blobstore(config) -> BlobStoreAbc:
    """Create and return the blob store backend configured in MytralConfig.

    Parameters
    ----------
    config : MytralConfig
        Application configuration instance.

    Returns
    -------
    BlobStoreAbc
        A ready-to-use blob store implementation.

    Raises
    ------
    BlobConfigurationError
        If the configured backend cannot be initialized (e.g. missing
        dependencies or connection failure).
    """

    if config.blobstore_type == BlobStoreType.FILESYSTEM:
        from mytral.blobstore.filesystem import FilesystemBlobStore

        return FilesystemBlobStore(
            base_dir=config.user_data_dir,
            blobs_subdir=config.blobstore_filesystem_subdir,
        )

    if config.blobstore_type == BlobStoreType.MINIO:
        from mytral.blobstore.minio_store import MinioBlobStore

        return MinioBlobStore(
            endpoint=config.blobstore_minio_endpoint,
            access_key=config.blobstore_minio_access_key,
            secret_key=config.blobstore_minio_secret_key,
            bucket=config.blobstore_minio_bucket,
            secure=config.blobstore_minio_secure,
        )

    if config.blobstore_type == BlobStoreType.S3:
        from mytral.blobstore.s3_store import S3BlobStore

        return S3BlobStore(
            bucket=config.blobstore_s3_bucket,
            region=config.blobstore_s3_region,
            access_key=config.blobstore_s3_access_key,
            secret_key=config.blobstore_s3_secret_key,
            session_token=config.blobstore_s3_session_token,
        )

    raise BlobConfigurationError(f"Unknown blobstore type: {config.blobstore_type!r}")


__all__ = [
    "AvatarBlobService",
    "BlobStoreAbc",
    "BlobStoreError",
    "BlobNotFoundError",
    "BlobConflictError",
    "BlobValidationError",
    "BlobConfigurationError",
    "BlobKind",
    "BlobOwnerKind",
    "BlobMetadata",
    "BlobRecord",
    "BLOB_VARIANT_ORIGINAL",
    "BLOB_VARIANT_NORMALIZED",
    "BLOB_VARIANT_THUMBNAIL",
    "EntityPhotoService",
    "create_blobstore",
]
