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

"""Entity photo service: upload and serve photos for exercises, gear, and goals."""

import datetime
import hashlib
import io
import typing
import uuid

import structlog

from mytral.blobstore import image_processing
from mytral.blobstore.abc import BlobStoreAbc
from mytral.blobstore.exceptions import BlobNotFoundError
from mytral.blobstore.exceptions import BlobStoreError
from mytral.blobstore.exceptions import BlobValidationError
from mytral.blobstore.models import BLOB_VARIANT_NORMALIZED
from mytral.blobstore.models import BLOB_VARIANT_THUMBNAIL
from mytral.blobstore.models import BlobKind
from mytral.blobstore.models import BlobMetadata
from mytral.blobstore.models import BlobOwnerKind
from mytral.blobstore.validation import validate_blob_metadata
from mytral.blobstore.validation import validate_photo

_logger = structlog.get_logger()

_MAX_PHOTO_BYTES = 25 * 1024 * 1024  # 25 MiB
_MAX_PHOTOS_PER_ENTITY = 20
_THUMBNAIL_PX = 400
_MAX_DIMENSION_PX = 1920


class EntityPhotoService:
    """Blob operations for entity photos (gear, exercise, goal).

    This service handles only blob storage operations. Routes are responsible
    for loading and persisting the entity's photo_blob_keys list.

    Parameters
    ----------
    store : BlobStoreAbc
        Underlying blob store backend.
    """

    def __init__(self, store: BlobStoreAbc) -> None:
        self._store = store

    def upload_photo(
        self,
        user_id: str,
        owner_key: str,
        owner_kind: BlobOwnerKind,
        kind: BlobKind,
        file_stream: typing.BinaryIO,
        original_filename: str,
        *,
        name: str = "",
        description: str = "",
        keywords: str | list[str] = "",
        max_count: int = _MAX_PHOTOS_PER_ENTITY,
        current_count: int = 0,
    ) -> BlobMetadata:
        """Upload and normalize a single photo for an entity.

        IMPORTANT: Caller must persist the returned blob_key in the entity
        and call delete_photo on failure to maintain consistency.

        Parameters
        ----------
        user_id : str
            Owning user identifier.
        owner_key : str
            Entity key (gear/exercise/goal UUID).
        owner_kind : BlobOwnerKind
            Owner kind enum value.
        kind : BlobKind
            Blob kind enum value.
        file_stream : typing.BinaryIO
            Uploaded file stream.
        original_filename : str
            Original filename from browser.
        name : str
            Human-readable name.
        description : str
            Description text.
        keywords : str | list[str]
            Comma-separated or list of keyword tags.
        max_count : int
            Maximum allowed photos per entity.
        current_count : int
            Current number of photos already attached.

        Returns
        -------
        BlobMetadata
            Metadata of the stored blob.

        Raises
        ------
        BlobValidationError
            On validation failure.
        BlobStoreError
            On backend failure.
        """
        if current_count >= max_count:
            raise BlobValidationError(
                f"Cannot upload photo: entity already has {current_count} photo(s), "
                f"limit is {max_count}."
            )

        data = file_stream.read(_MAX_PHOTO_BYTES + 1)
        if len(data) > _MAX_PHOTO_BYTES:
            raise BlobValidationError(
                f"Photo exceeds the maximum allowed size of "
                f"{_MAX_PHOTO_BYTES // (1024 * 1024)} MiB."
            )

        _ext, width, height = validate_photo(
            filename=original_filename,
            data=data,
            max_bytes=_MAX_PHOTO_BYTES,
        )

        name_v, desc_v, kw_v = validate_blob_metadata(name, description, keywords)

        # normalize: strip EXIF, auto-rotate, resize
        try:
            norm_bytes, norm_fmt, norm_w, norm_h = image_processing.normalize_photo(
                data=data,
                extension=_ext,
                max_dimension_px=_MAX_DIMENSION_PX,
            )
            stored_w = norm_w or width
            stored_h = norm_h or height
            stored_ext = f".{norm_fmt}" if norm_fmt != "jpeg" else ".jpg"
        except (BlobValidationError, ImportError) as exc:
            _logger.warning("entity_photo.normalize_skipped", exc=str(exc))
            norm_bytes = data
            norm_fmt = _ext.lstrip(".") if _ext else "jpeg"
            stored_w, stored_h = width, height
            stored_ext = _ext or ".jpg"

        _ext_to_mime = {
            ".jpg": "image/jpeg",
            ".jpeg": "image/jpeg",
            ".png": "image/png",
            ".webp": "image/webp",
        }

        blob_key = str(uuid.uuid4()).replace("-", "")
        now = datetime.datetime.now(datetime.timezone.utc).isoformat()
        sha = hashlib.sha256(norm_bytes).hexdigest()

        metadata = BlobMetadata(
            blob_key=blob_key,
            user_id=user_id,
            owner_kind=owner_kind.value,
            owner_key=owner_key,
            kind=kind.value,
            file_name=f"normalized{stored_ext}",
            original_file_name=original_filename,
            extension=stored_ext,
            content_type=_ext_to_mime.get(stored_ext, "image/jpeg"),
            size_bytes=len(norm_bytes),
            sha256=sha,
            name=name_v,
            description=desc_v,
            keywords=kw_v,
            created_at=now,
            updated_at=now,
            width=stored_w,
            height=stored_h,
            normalized_format=norm_fmt,
        )

        self._store.create_blob(metadata, io.BytesIO(norm_bytes))

        # generate thumbnail; best-effort update metadata with thumbnail flag
        try:
            thumb_bytes = image_processing.generate_thumbnail(
                data=norm_bytes,
                max_dimension_px=_THUMBNAIL_PX,
            )
            if hasattr(self._store, "write_blob_variant"):
                self._store.write_blob_variant(
                    user_id, blob_key, BLOB_VARIANT_THUMBNAIL, thumb_bytes
                )
                metadata.thumbnail_available = True
                self._store.update_blob_metadata(
                    user_id,
                    blob_key,
                    name=metadata.name,
                    description=metadata.description,
                    keywords=metadata.keywords,
                    thumbnail_available=True,
                    width=metadata.width,
                    height=metadata.height,
                )
        except (BlobValidationError, BlobStoreError, ImportError) as exc:
            _logger.warning(
                "entity_photo.thumbnail_failed", blob_key=blob_key, exc=str(exc)
            )

        return metadata

    def delete_photo(self, user_id: str, blob_key: str) -> None:
        """Delete a photo blob. Best-effort, ignores BlobNotFoundError.

        Parameters
        ----------
        user_id : str
            Owning user identifier.
        blob_key : str
            Blob key to delete.
        """
        try:
            self._store.delete_blob(user_id, blob_key)
        except BlobNotFoundError:
            pass

    def open_photo(
        self, user_id: str, blob_key: str, thumbnail: bool = False
    ) -> tuple[typing.BinaryIO, BlobMetadata]:
        """Open a photo for streaming.

        Parameters
        ----------
        user_id : str
            Owning user identifier.
        blob_key : str
            Blob key.
        thumbnail : bool
            If True, return thumbnail variant; else normalized.

        Returns
        -------
        tuple[BinaryIO, BlobMetadata]
            Stream and metadata.
        """
        meta = self._store.get_blob_metadata(user_id, blob_key)
        variant = BLOB_VARIANT_THUMBNAIL if thumbnail else BLOB_VARIANT_NORMALIZED

        if thumbnail and not meta.thumbnail_available:
            variant = BLOB_VARIANT_NORMALIZED

        stream = self._store.open_blob(user_id, blob_key, variant)
        return stream, meta

    def list_photos(self, user_id: str, blob_keys: list[str]) -> list[BlobMetadata]:
        """Return metadata for listed blob keys, skipping missing/corrupt entries.

        Parameters
        ----------
        user_id : str
            Owning user identifier.
        blob_keys : list[str]
            Blob keys to resolve.

        Returns
        -------
        list[BlobMetadata]
            Metadata for each found blob.
        """
        results = []
        for bk in blob_keys:
            try:
                results.append(self._store.get_blob_metadata(user_id, bk))
            except (BlobNotFoundError, BlobStoreError):
                _logger.warning(
                    "entity_photo.list_missing_blob", blob_key=bk, user_id=user_id
                )
        return results
