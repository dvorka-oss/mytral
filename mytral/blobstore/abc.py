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
import abc
import typing

from mytral.blobstore.models import BlobMetadata


class BlobStoreAbc(abc.ABC):
    """Backend-neutral contract for blob CRUD operations.

    All do must raise explicit domain exceptions (see
    ``mytral.blobstore.exceptions``) rather than returning ``None`` on error.

    .. warning::
        This layer does **not** enforce authorization.  Every method accepts a
        ``user_id`` parameter that scopes the lookup, but it trusts the caller
        to supply the correct value.  Authorization — verifying that the
        requesting user owns the resource — is the responsibility of the
        **service layer** (``ActivityBlobService``).  Any mistake at that
        boundary is a potential confidentiality breach.
    """

    @abc.abstractmethod
    def create_blob(
        self,
        metadata: BlobMetadata,
        data_stream: typing.BinaryIO,
    ) -> BlobMetadata:
        """Write a new blob and its metadata to the store.

        Parameters
        ----------
        metadata : BlobMetadata
            Fully-populated metadata. ``blob_key`` must be unique within the user.
        data_stream : typing.BinaryIO
            Readable binary stream of the blob content.

        Returns
        -------
        BlobMetadata
            The stored metadata (may have fields updated by the backend, e.g.
            sha256 or size_bytes if computed during write).

        Raises
        ------
        BlobConflictError
            If a blob with the same key already exists.
        BlobStoreError
            On any unrecoverable backend failure.
        """

    @abc.abstractmethod
    def get_blob_metadata(
        self,
        user_id: str,
        blob_key: str,
    ) -> BlobMetadata:
        """Return metadata for a specific blob.

        Parameters
        ----------
        user_id : str
            Owning user identifier.
        blob_key : str
            Unique blob key.

        Raises
        ------
        BlobNotFoundError
            If the blob does not exist.
        """

    @abc.abstractmethod
    def list_blobs(
        self,
        user_id: str,
        owner_kind: str,
        owner_key: str,
        kind: str | None = None,
    ) -> list[BlobMetadata]:
        """List blobs belonging to a specific owner entity.

        Parameters
        ----------
        user_id : str
            Owning user identifier.
        owner_kind : str
            Owner entity type (see BlobOwnerKind).
        owner_key : str
            Owner entity primary key.
        kind : str | None
            When set, filter results to this blob kind (see BlobKind).

        Returns
        -------
        list[BlobMetadata]
            Ordered by creation time, ascending.
        """

    @abc.abstractmethod
    def open_blob(
        self,
        user_id: str,
        blob_key: str,
        variant: str = "original",
    ) -> typing.BinaryIO:
        """Open a readable stream for a blob variant.

        Parameters
        ----------
        user_id : str
            Owning user identifier.
        blob_key : str
            Unique blob key.
        variant : str
            One of ``original``, ``normalized``, ``thumbnail``.
            ``thumbnail`` is only available for photo blobs.

        Returns
        -------
        typing.BinaryIO
            A readable binary stream. The caller is responsible for closing it.

        Raises
        ------
        BlobNotFoundError
            If the blob or the requested variant does not exist.
        """

    @abc.abstractmethod
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
        """Update user-editable metadata fields.

        Only ``name``, ``description``, ``keywords``, and the optional image
        geometry fields may be updated.  The binary payload and system metadata
        are never modified.

        Parameters
        ----------
        user_id : str
            Owning user identifier.
        blob_key : str
            Unique blob key.
        name : str
            New name value.
        description : str
            New description value.
        keywords : list[str]
            New keyword list (already normalized).
        thumbnail_available : bool | None
            When provided, overwrite the thumbnail-available flag.
        width : int | None
            When provided, overwrite the stored image width in pixels.
        height : int | None
            When provided, overwrite the stored image height in pixels.
        track_count : int | None
            When provided, overwrite the GPX track count.
        track_point_count : int | None
            When provided, overwrite the GPX trackpoint count.
        summary_polyline : str | None
            When provided, overwrite the encoded summary polyline.
        summary_bbox : tuple[float, float, float, float] | None
            When provided, overwrite the summary bounding box.
        full_polyline : str | None
            When provided, overwrite the encoded full polyline.
        elevation_profile : list[tuple[float, float]] | None
            When provided, overwrite the simplified elevation profile.

        Raises
        ------
        BlobNotFoundError
            If the blob does not exist.
        """

    @abc.abstractmethod
    def delete_blob(
        self,
        user_id: str,
        blob_key: str,
    ) -> None:
        """Hard-delete a blob and all of its variants.

        The implementation must guarantee the no-relic invariant: after a
        successful return, no binary payload, thumbnail, normalized variant,
        or metadata object must remain.

        Parameters
        ----------
        user_id : str
            Owning user identifier.
        blob_key : str
            Unique blob key.

        Raises
        ------
        BlobNotFoundError
            If the blob does not exist.
        BlobStoreError
            If deletion could not be fully verified as complete.
        """

    @abc.abstractmethod
    def blob_exists(
        self,
        user_id: str,
        blob_key: str,
    ) -> bool:
        """Return True if the blob exists in the store.

        Parameters
        ----------
        user_id : str
            Owning user identifier.
        blob_key : str
            Unique blob key.
        """
