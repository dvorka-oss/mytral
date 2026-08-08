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

"""Entity document service: upload and serve documents for gear, exercises, goals."""

import datetime
import hashlib
import io
import typing
import uuid

import structlog

from mytral.blobstore.abc import BlobStoreAbc
from mytral.blobstore.exceptions import BlobNotFoundError
from mytral.blobstore.exceptions import BlobStoreError
from mytral.blobstore.exceptions import BlobValidationError
from mytral.blobstore.models import BlobKind
from mytral.blobstore.models import BlobMetadata
from mytral.blobstore.models import BlobOwnerKind
from mytral.blobstore.validation import DOCUMENT_EXTENSION_TO_CONTENT_TYPE
from mytral.blobstore.validation import DOCUMENT_MAX_BYTES
from mytral.blobstore.validation import validate_blob_metadata
from mytral.blobstore.validation import validate_document

_logger = structlog.get_logger()

_MAX_ATTACHMENTS_PER_ENTITY = 20


class EntityDocumentService:
    """Blob operations for entity documents/attachments (gear, exercise, goal).

    Documents are arbitrary non-image files (PDF, Office documents, plain
    text, ...) such as manuals, invoices, or warranty cards. Unlike photos,
    no normalization or thumbnail generation is performed.

    This service handles only blob storage operations. Routes are responsible
    for loading and persisting the entity's attachment_blob_keys list.

    Parameters
    ----------
    store : BlobStoreAbc
        Underlying blob store backend.
    """

    def __init__(self, store: BlobStoreAbc) -> None:
        self._store = store

    def upload_document(
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
        max_bytes: int = DOCUMENT_MAX_BYTES,
        max_count: int = _MAX_ATTACHMENTS_PER_ENTITY,
        current_count: int = 0,
    ) -> BlobMetadata:
        """Upload a single document for an entity.

        IMPORTANT: Caller must persist the returned blob_key in the entity
        and call delete_document on failure to maintain consistency.

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
        max_bytes : int
            Maximum allowed document size in bytes.
        max_count : int
            Maximum allowed documents per entity.
        current_count : int
            Current number of documents already attached.

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
                f"Cannot upload document: entity already has {current_count} "
                f"document(s), limit is {max_count}."
            )

        data = file_stream.read(max_bytes + 1)
        ext = validate_document(
            filename=original_filename,
            data=data,
            max_bytes=max_bytes,
        )

        name_v, desc_v, kw_v = validate_blob_metadata(name, description, keywords)

        blob_key = str(uuid.uuid4()).replace("-", "")
        now = datetime.datetime.now(datetime.timezone.utc).isoformat()
        sha = hashlib.sha256(data).hexdigest()

        metadata = BlobMetadata(
            blob_key=blob_key,
            user_id=user_id,
            owner_kind=owner_kind.value,
            owner_key=owner_key,
            kind=kind.value,
            file_name=f"data{ext}",
            original_file_name=original_filename,
            extension=ext,
            content_type=DOCUMENT_EXTENSION_TO_CONTENT_TYPE.get(
                ext, "application/octet-stream"
            ),
            size_bytes=len(data),
            sha256=sha,
            name=name_v,
            description=desc_v,
            keywords=kw_v,
            created_at=now,
            updated_at=now,
        )

        self._store.create_blob(metadata, io.BytesIO(data))

        return metadata

    def delete_document(self, user_id: str, blob_key: str) -> None:
        """Delete a document blob. Best-effort, ignores BlobNotFoundError.

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

    def open_document(
        self, user_id: str, blob_key: str
    ) -> tuple[typing.BinaryIO, BlobMetadata]:
        """Open a document for streaming/download.

        Parameters
        ----------
        user_id : str
            Owning user identifier.
        blob_key : str
            Blob key.

        Returns
        -------
        tuple[BinaryIO, BlobMetadata]
            Stream and metadata.
        """
        meta = self._store.get_blob_metadata(user_id, blob_key)
        stream = self._store.open_blob(user_id, blob_key)
        return stream, meta

    def list_documents(self, user_id: str, blob_keys: list[str]) -> list[BlobMetadata]:
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
                    "entity_document.list_missing_blob", blob_key=bk, user_id=user_id
                )
        return results
