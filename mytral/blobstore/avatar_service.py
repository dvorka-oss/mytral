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
"""Avatar blob service: upload and serve square JPEG avatars for users and coaches."""

import datetime
import hashlib
import io
import typing
import uuid

import structlog

from mytral.blobstore import image_processing
from mytral.blobstore.abc import BlobStoreAbc
from mytral.blobstore.exceptions import BlobValidationError
from mytral.blobstore.models import BLOB_VARIANT_NORMALIZED
from mytral.blobstore.models import BLOB_VARIANT_THUMBNAIL
from mytral.blobstore.models import BlobKind
from mytral.blobstore.models import BlobMetadata
from mytral.blobstore.models import BlobOwnerKind

_logger = structlog.get_logger()

# avatar upload size limit: 10 MB
_MAX_AVATAR_BYTES = 10 * 1024 * 1024

# normalized avatar dimension
_AVATAR_PX = 200

# thumbnail avatar dimension
_THUMB_PX = 40

_ALLOWED_EXTENSIONS = {".jpg", ".jpeg", ".png", ".gif", ".webp"}


def _now_iso() -> str:
    return datetime.datetime.now(datetime.timezone.utc).isoformat()


def _sha256_hex(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def _new_blob_key() -> str:
    return str(uuid.uuid4()).replace("-", "")


def _validate_extension(extension: str) -> str:
    """Normalize and validate the file extension.

    Parameters
    ----------
    extension : str
        File extension, optionally including leading dot.

    Returns
    -------
    str
        Lowercase extension with leading dot.

    Raises
    ------
    BlobValidationError
        If the extension is not an allowed image type.
    """
    if not extension.startswith("."):
        extension = f".{extension}"
    extension = extension.lower()
    if extension not in _ALLOWED_EXTENSIONS:
        raise BlobValidationError(
            f"Unsupported avatar format '{extension}'. "
            f"Allowed: {sorted(_ALLOWED_EXTENSIONS)}"
        )
    return extension


class AvatarBlobService:
    """Business rules for uploading and serving user and coach avatar photos.

    Parameters
    ----------
    store : BlobStoreAbc
        Underlying blob store backend.
    """

    def __init__(self, store: BlobStoreAbc) -> None:
        self._store = store

    #
    # Upload helpers
    #

    def _upload_avatar(
        self,
        user_id: str,
        owner_kind: str,
        owner_key: str,
        kind: str,
        data: bytes,
        extension: str,
    ) -> BlobMetadata:
        """Normalize, store, and return metadata for an avatar blob.

        Parameters
        ----------
        user_id : str
            ID of the owning user.
        owner_kind : str
            ``BlobOwnerKind`` value string.
        owner_key : str
            Key of the entity that owns this avatar (user_id for user, coach key
            for coach).
        kind : str
            ``BlobKind`` value string.
        data : bytes
            Raw uploaded image bytes.
        extension : str
            File extension of the uploaded file.

        Returns
        -------
        BlobMetadata
            Metadata for the newly created blob.

        Raises
        ------
        BlobValidationError
            If the image is invalid or too large.
        BlobStoreError
            On storage failure.
        """
        if len(data) > _MAX_AVATAR_BYTES:
            raise BlobValidationError(
                f"Avatar file is too large ({len(data)} bytes, "
                f"max {_MAX_AVATAR_BYTES})."
            )

        ext = _validate_extension(extension)
        normalized_data, _fmt, width, height = image_processing.normalize_avatar(
            data, ext
        )

        blob_key = _new_blob_key()
        now = _now_iso()
        metadata = BlobMetadata(
            user_id=user_id,
            blob_key=blob_key,
            owner_kind=owner_kind,
            owner_key=owner_key,
            kind=kind,
            file_name="normalized.jpg",
            original_file_name=f"avatar{ext}",
            extension=".jpg",
            content_type="image/jpeg",
            size_bytes=len(normalized_data),
            sha256=_sha256_hex(normalized_data),
            name="",
            description="",
            keywords=[],
            created_at=now,
            updated_at=now,
            width=width,
            height=height,
            normalized_format="jpeg",
        )

        self._store.create_blob(
            metadata=metadata,
            data_stream=io.BytesIO(normalized_data),
        )

        try:
            thumb_data = image_processing.generate_thumbnail(normalized_data, _THUMB_PX)
            self._store.write_blob_variant(
                user_id, blob_key, BLOB_VARIANT_THUMBNAIL, thumb_data
            )
            self._store.update_blob_metadata(
                user_id,
                blob_key,
                name="",
                description="",
                keywords=[],
                thumbnail_available=True,
                width=width,
                height=height,
            )
            metadata.thumbnail_available = True
        except Exception as exc:
            _logger.warning(
                "avatar.thumbnail_failed",
                user_id=user_id,
                blob_key=blob_key,
                exc=str(exc),
            )

        _logger.info(
            "avatar_uploaded",
            user_id=user_id,
            owner_kind=owner_kind,
            owner_key=owner_key,
            blob_key=blob_key,
            size=len(normalized_data),
        )
        return metadata

    #
    # User avatar
    #

    def upload_user_avatar(
        self,
        user_id: str,
        data: bytes,
        extension: str,
    ) -> BlobMetadata:
        """Upload (or replace) the avatar for a user profile.

        Parameters
        ----------
        user_id : str
            ID of the user.
        data : bytes
            Raw image bytes.
        extension : str
            File extension of the uploaded image.

        Returns
        -------
        BlobMetadata
            Metadata for the newly stored blob.
        """
        return self._upload_avatar(
            user_id=user_id,
            owner_kind=BlobOwnerKind.USER.value,
            owner_key=user_id,
            kind=BlobKind.USER_AVATAR.value,
            data=data,
            extension=extension,
        )

    def open_user_avatar(
        self,
        user_id: str,
        blob_key: str,
        thumbnail: bool = False,
    ) -> typing.BinaryIO:
        """Open the avatar (or thumbnail) stream for a user.

        Parameters
        ----------
        user_id : str
            ID of the user.
        blob_key : str
            Blob key returned from a previous upload.
        thumbnail : bool
            When ``True``, returns the 40×40 thumbnail variant.

        Returns
        -------
        typing.BinaryIO
            Readable binary stream of JPEG bytes.

        Raises
        ------
        BlobNotFoundError
            If the blob or variant does not exist.
        """
        variant = BLOB_VARIANT_THUMBNAIL if thumbnail else BLOB_VARIANT_NORMALIZED
        return self._store.open_blob(user_id, blob_key, variant)

    #
    # Coach avatar
    #

    def upload_coach_avatar(
        self,
        user_id: str,
        coach_key: str,
        data: bytes,
        extension: str,
    ) -> BlobMetadata:
        """Upload (or replace) the avatar for an AI coach.

        Parameters
        ----------
        user_id : str
            ID of the owning user.
        coach_key : str
            Key of the coach within the user's coach list.
        data : bytes
            Raw image bytes.
        extension : str
            File extension of the uploaded image.

        Returns
        -------
        BlobMetadata
            Metadata for the newly stored blob.
        """
        return self._upload_avatar(
            user_id=user_id,
            owner_kind=BlobOwnerKind.ACOACH.value,
            owner_key=coach_key,
            kind=BlobKind.ACOACH_AVATAR.value,
            data=data,
            extension=extension,
        )

    def open_coach_avatar(
        self,
        user_id: str,
        blob_key: str,
        thumbnail: bool = False,
    ) -> typing.BinaryIO:
        """Open the avatar (or thumbnail) stream for a coach.

        Parameters
        ----------
        user_id : str
            ID of the owning user.
        blob_key : str
            Blob key returned from a previous upload.
        thumbnail : bool
            When ``True``, returns the 40×40 thumbnail variant.

        Returns
        -------
        typing.BinaryIO
            Readable binary stream of JPEG bytes.

        Raises
        ------
        BlobNotFoundError
            If the blob or variant does not exist.
        """
        variant = BLOB_VARIANT_THUMBNAIL if thumbnail else BLOB_VARIANT_NORMALIZED
        return self._store.open_blob(user_id, blob_key, variant)

    #
    # Deletion
    #

    def delete_avatar(self, user_id: str, blob_key: str) -> None:
        """Delete an avatar blob (user or coach).

        Parameters
        ----------
        user_id : str
            ID of the owning user.
        blob_key : str
            Key of the blob to delete.

        Raises
        ------
        BlobNotFoundError
            If the blob does not exist.
        BlobStoreError
            On storage failure.
        """
        self._store.delete_blob(user_id=user_id, blob_key=blob_key)
        _logger.info(
            "avatar_deleted",
            user_id=user_id,
            blob_key=blob_key,
        )
