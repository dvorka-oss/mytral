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
"""Filesystem-backed blob store implementation."""

import datetime
import json
import os
import pathlib
import shutil
import tempfile
import typing

from mytral.blobstore.abc import BlobStoreAbc
from mytral.blobstore.exceptions import BlobConflictError
from mytral.blobstore.exceptions import BlobNotFoundError
from mytral.blobstore.exceptions import BlobStoreError
from mytral.blobstore.models import BLOB_VARIANT_NORMALIZED
from mytral.blobstore.models import BLOB_VARIANT_ORIGINAL
from mytral.blobstore.models import BLOB_VARIANT_THUMBNAIL
from mytral.blobstore.models import BlobKind
from mytral.blobstore.models import BlobMetadata

_METADATA_FILENAME = "metadata.json"

# filenames used inside each blob directory
_DATA_NAMES = {
    BLOB_VARIANT_NORMALIZED: {
        # photos: normalized (EXIF-stripped, resized) bytes — the only stored photo file
        ".jpg": "normalized.jpg",
        ".jpeg": "normalized.jpg",
        ".png": "normalized.png",
        ".webp": "normalized.webp",
    },
    BLOB_VARIANT_THUMBNAIL: {
        # thumbnails are always stored as JPEG regardless of the source format;
        # this keeps the serving path simple and avoids special-casing per format
        ".jpg": "thumbnail.jpg",
        ".jpeg": "thumbnail.jpg",
        ".png": "thumbnail.jpg",
        ".webp": "thumbnail.jpg",
    },
}


def _photo_filename(extension: str) -> str:
    """Return the on-disk filename for a photo blob (normalized bytes stored here)."""
    return _DATA_NAMES[BLOB_VARIANT_NORMALIZED].get(extension, f"normalized{extension}")


def _gpx_filename() -> str:
    """Return the on-disk filename for a GPX blob."""
    return "data.gpx"


class FilesystemBlobStore(BlobStoreAbc):
    """Blob store that persists blobs on the local filesystem.

    Parameters
    ----------
    base_dir : pathlib.Path
        Root data directory that contains per-user subdirectories (the ``data/``
        directory of the MyTraL instance).
    blobs_subdir : str
        Name of the blobs subdirectory within each user directory. Defaults to
        ``"blobs"``.
    """

    def __init__(
        self,
        base_dir: pathlib.Path,
        blobs_subdir: str = "blobs",
    ) -> None:
        self._base_dir = base_dir
        self._blobs_subdir = blobs_subdir

    #
    # Internal helpers
    #

    @staticmethod
    def _validate_path_component(value: str, name: str) -> None:
        """Reject values that contain filesystem path separators.

        Parameters
        ----------
        value : str
            The string to validate.
        name : str
            Human-readable parameter name for error messages.

        Raises
        ------
        ValueError
            If the value contains ``/`` or ``\\``.
        """
        if "/" in value or "\\" in value:
            raise ValueError(
                f"Invalid {name} '{value}': "
                "path component must not contain path separators."
            )

    def _user_blobs_dir(self, user_id: str) -> pathlib.Path:
        self._validate_path_component(user_id, "user_id")
        return self._base_dir / user_id / self._blobs_subdir

    def _blob_dir(
        self, user_id: str, blob_key: str, metadata: BlobMetadata
    ) -> pathlib.Path:
        self._validate_path_component(blob_key, "blob_key")
        return self._owner_dir(user_id, metadata) / blob_key

    def _owner_dir(self, user_id: str, metadata: BlobMetadata) -> pathlib.Path:
        self._validate_path_component(metadata.owner_key, "owner_key")
        blobs_dir = self._user_blobs_dir(user_id)
        if metadata.kind == BlobKind.ACTIVITY_RECORDING.value:
            return blobs_dir / "activities" / metadata.owner_key / "recordings"
        if metadata.kind == BlobKind.ACTIVITY_PARQUET.value:
            return blobs_dir / "activities" / metadata.owner_key / "parquet"
        if metadata.kind == BlobKind.ACTIVITY_PHOTO.value:
            return blobs_dir / "activities" / metadata.owner_key / "photos"
        if metadata.kind == BlobKind.USER_AVATAR.value:
            return blobs_dir / "profile"
        if metadata.kind == BlobKind.ACOACH_AVATAR.value:
            return blobs_dir / "acoaches" / metadata.owner_key
        if metadata.kind == BlobKind.GEAR_PHOTO.value:
            return blobs_dir / "gear" / metadata.owner_key / "photos"
        if metadata.kind == BlobKind.EXERCISE_PHOTO.value:
            return blobs_dir / "exercises" / metadata.owner_key / "photos"
        if metadata.kind == BlobKind.GOAL_PHOTO.value:
            return blobs_dir / "goals" / metadata.owner_key / "photos"
        return blobs_dir / "misc" / metadata.owner_key / metadata.kind

    def _locate_blob_dir(self, user_id: str, blob_key: str) -> pathlib.Path | None:
        """Search for the blob directory by scanning known owner kind prefixes."""
        self._validate_path_component(blob_key, "blob_key")
        blobs_dir = self._user_blobs_dir(user_id)

        # scan activities/<activity_key>/<kind>/<blob_key>/
        activities_dir = blobs_dir / "activities"
        if activities_dir.exists():
            for activity_dir in activities_dir.iterdir():
                if not activity_dir.is_dir():
                    continue
                for kind_dir in activity_dir.iterdir():
                    if not kind_dir.is_dir():
                        continue
                    candidate = kind_dir / blob_key
                    if candidate.is_dir() and (candidate / _METADATA_FILENAME).exists():
                        return candidate

        # scan profile/<blob_key>/  (user avatars)
        profile_dir = blobs_dir / "profile"
        if profile_dir.exists():
            candidate = profile_dir / blob_key
            if candidate.is_dir() and (candidate / _METADATA_FILENAME).exists():
                return candidate

        # scan acoaches/<coach_key>/<blob_key>/  (coach avatars)
        acoaches_dir = blobs_dir / "acoaches"
        if acoaches_dir.exists():
            for coach_dir in acoaches_dir.iterdir():
                if not coach_dir.is_dir():
                    continue
                candidate = coach_dir / blob_key
                if candidate.is_dir() and (candidate / _METADATA_FILENAME).exists():
                    return candidate

        # scan gear/<gear_key>/photos/<blob_key>/
        gear_dir = blobs_dir / "gear"
        if gear_dir.exists():
            for owner_dir in gear_dir.iterdir():
                if not owner_dir.is_dir():
                    continue
                for kind_dir in owner_dir.iterdir():
                    if not kind_dir.is_dir():
                        continue
                    candidate = kind_dir / blob_key
                    if candidate.is_dir() and (candidate / _METADATA_FILENAME).exists():
                        return candidate

        # scan exercises/<exercise_key>/photos/<blob_key>/
        exercises_dir = blobs_dir / "exercises"
        if exercises_dir.exists():
            for owner_dir in exercises_dir.iterdir():
                if not owner_dir.is_dir():
                    continue
                for kind_dir in owner_dir.iterdir():
                    if not kind_dir.is_dir():
                        continue
                    candidate = kind_dir / blob_key
                    if candidate.is_dir() and (candidate / _METADATA_FILENAME).exists():
                        return candidate

        # scan goals/<goal_key>/photos/<blob_key>/
        goals_dir = blobs_dir / "goals"
        if goals_dir.exists():
            for owner_dir in goals_dir.iterdir():
                if not owner_dir.is_dir():
                    continue
                for kind_dir in owner_dir.iterdir():
                    if not kind_dir.is_dir():
                        continue
                    candidate = kind_dir / blob_key
                    if candidate.is_dir() and (candidate / _METADATA_FILENAME).exists():
                        return candidate

        return None

    def _read_metadata(self, blob_dir: pathlib.Path) -> BlobMetadata:
        meta_path = blob_dir / _METADATA_FILENAME
        try:
            with open(meta_path, "r", encoding="utf-8") as fh:
                return BlobMetadata.from_dict(json.load(fh))
        except FileNotFoundError as exc:
            raise BlobNotFoundError(f"Metadata not found at: {meta_path}") from exc
        except (json.JSONDecodeError, TypeError) as exc:
            raise BlobStoreError(f"Metadata is corrupt at: {meta_path}: {exc}") from exc

    def _write_metadata_atomic(
        self, blob_dir: pathlib.Path, metadata: BlobMetadata
    ) -> None:
        meta_path = blob_dir / _METADATA_FILENAME
        tmp_fd, tmp_path = tempfile.mkstemp(
            dir=blob_dir, prefix=".meta_", suffix=".json"
        )
        try:
            with os.fdopen(tmp_fd, "w", encoding="utf-8") as fh:
                json.dump(metadata.to_dict(), fh, indent=2, ensure_ascii=False)
                fh.flush()
                os.fsync(fh.fileno())
            os.replace(tmp_path, meta_path)
        except Exception:
            try:
                os.unlink(tmp_path)
            except OSError:
                pass
            raise

    def _blob_dir_from_key(self, user_id: str, blob_key: str) -> pathlib.Path:
        """Return the blob directory, raising BlobNotFoundError if absent."""
        blob_dir = self._locate_blob_dir(user_id, blob_key)
        if blob_dir is None:
            raise BlobNotFoundError(
                f"Blob '{blob_key}' not found for user '{user_id}'."
            )
        return blob_dir

    #
    # BlobStoreAbc implementation
    #

    def create_blob(
        self,
        metadata: BlobMetadata,
        data_stream: typing.BinaryIO,
    ) -> BlobMetadata:
        """Write a new blob and its metadata to the filesystem."""
        if self.blob_exists(metadata.user_id, metadata.blob_key):
            raise BlobConflictError(
                f"Blob '{metadata.blob_key}' already exists for user "
                f"'{metadata.user_id}'."
            )

        owner_dir = self._owner_dir(metadata.user_id, metadata)
        blob_dir = owner_dir / metadata.blob_key
        blob_dir.mkdir(parents=True, exist_ok=False)

        try:
            # resolve the primary data filename based on blob kind
            if metadata.extension == ".gpx":
                data_filename = _gpx_filename()
            else:
                data_filename = _photo_filename(metadata.extension)
            data_path = blob_dir / data_filename

            tmp_fd, tmp_path = tempfile.mkstemp(
                dir=blob_dir, prefix=".data_", suffix=".tmp"
            )
            try:
                with os.fdopen(tmp_fd, "wb") as fh:
                    shutil.copyfileobj(data_stream, fh)
                    fh.flush()
                    os.fsync(fh.fileno())
                os.replace(tmp_path, data_path)
            except Exception:
                try:
                    os.unlink(tmp_path)
                except OSError:
                    pass
                raise

            self._write_metadata_atomic(blob_dir, metadata)
        except Exception:
            # compensate: remove the partially-written blob directory
            try:
                shutil.rmtree(blob_dir)
            except OSError:
                pass
            raise

        return metadata

    def get_blob_metadata(
        self,
        user_id: str,
        blob_key: str,
    ) -> BlobMetadata:
        """Return metadata for the given blob key."""
        blob_dir = self._blob_dir_from_key(user_id, blob_key)
        return self._read_metadata(blob_dir)

    def list_blobs(
        self,
        user_id: str,
        owner_kind: str,
        owner_key: str,
        kind: str | None = None,
    ) -> list[BlobMetadata]:
        """List blobs belonging to an owner entity, sorted by creation time."""
        blobs_dir = self._user_blobs_dir(user_id)
        results: list[BlobMetadata] = []

        if owner_kind == "activity":
            activity_dir = blobs_dir / "activities" / owner_key
            if not activity_dir.exists():
                return []
            for kind_dir in activity_dir.iterdir():
                if not kind_dir.is_dir():
                    continue
                for blob_dir in kind_dir.iterdir():
                    if not blob_dir.is_dir():
                        continue
                    meta_path = blob_dir / _METADATA_FILENAME
                    if not meta_path.exists():
                        continue
                    try:
                        meta = self._read_metadata(blob_dir)
                    except BlobStoreError:
                        continue
                    if kind is not None and meta.kind != kind:
                        continue
                    results.append(meta)

        elif owner_kind == "gear":
            owner_dir = blobs_dir / "gear" / owner_key
            if not owner_dir.exists():
                return []
            for kind_dir in owner_dir.iterdir():
                if not kind_dir.is_dir():
                    continue
                for blob_dir in kind_dir.iterdir():
                    if not blob_dir.is_dir():
                        continue
                    meta_path = blob_dir / _METADATA_FILENAME
                    if not meta_path.exists():
                        continue
                    try:
                        meta = self._read_metadata(blob_dir)
                    except BlobStoreError:
                        continue
                    if kind is not None and meta.kind != kind:
                        continue
                    results.append(meta)

        elif owner_kind == "exercise":
            owner_dir = blobs_dir / "exercises" / owner_key
            if not owner_dir.exists():
                return []
            for kind_dir in owner_dir.iterdir():
                if not kind_dir.is_dir():
                    continue
                for blob_dir in kind_dir.iterdir():
                    if not blob_dir.is_dir():
                        continue
                    meta_path = blob_dir / _METADATA_FILENAME
                    if not meta_path.exists():
                        continue
                    try:
                        meta = self._read_metadata(blob_dir)
                    except BlobStoreError:
                        continue
                    if kind is not None and meta.kind != kind:
                        continue
                    results.append(meta)

        elif owner_kind == "goal":
            owner_dir = blobs_dir / "goals" / owner_key
            if not owner_dir.exists():
                return []
            for kind_dir in owner_dir.iterdir():
                if not kind_dir.is_dir():
                    continue
                for blob_dir in kind_dir.iterdir():
                    if not blob_dir.is_dir():
                        continue
                    meta_path = blob_dir / _METADATA_FILENAME
                    if not meta_path.exists():
                        continue
                    try:
                        meta = self._read_metadata(blob_dir)
                    except BlobStoreError:
                        continue
                    if kind is not None and meta.kind != kind:
                        continue
                    results.append(meta)

        results.sort(key=lambda m: m.created_at)
        return results

    def open_blob(
        self,
        user_id: str,
        blob_key: str,
        variant: str = BLOB_VARIANT_ORIGINAL,
    ) -> typing.BinaryIO:
        """Open a readable binary stream for a blob variant."""
        blob_dir = self._blob_dir_from_key(user_id, blob_key)
        meta = self._read_metadata(blob_dir)

        is_gpx = meta.extension == ".gpx"
        if variant in (BLOB_VARIANT_ORIGINAL, BLOB_VARIANT_NORMALIZED):
            # GPX: single data file; photos: normalized bytes are the only stored file
            path = blob_dir / (
                _gpx_filename() if is_gpx else _photo_filename(meta.extension)
            )
        elif variant == BLOB_VARIANT_THUMBNAIL:
            path = blob_dir / "thumbnail.jpg"
        else:
            raise BlobNotFoundError(f"Unknown blob variant: '{variant}'.")

        if not path.exists():
            raise BlobNotFoundError(
                f"Blob variant '{variant}' not found for key '{blob_key}'."
            )
        return open(path, "rb")  # noqa: SIM115 - caller closes stream

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
        """Update user-editable metadata fields atomically."""
        blob_dir = self._blob_dir_from_key(user_id, blob_key)
        meta = self._read_metadata(blob_dir)
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
        self._write_metadata_atomic(blob_dir, meta)
        return meta

    def delete_blob(
        self,
        user_id: str,
        blob_key: str,
    ) -> None:
        """Hard-delete a blob directory and all variants with no-relic guarantee."""
        blob_dir = self._blob_dir_from_key(user_id, blob_key)

        # delete the entire blob directory tree (data + metadata)
        try:
            shutil.rmtree(blob_dir)
        except OSError as exc:
            raise BlobStoreError(
                f"Failed to delete blob directory '{blob_dir}': {exc}"
            ) from exc

        # verify no relic remains — this check races in theory (another process could
        # recreate the directory between rmtree and exists()), but on PythonAnywhere's
        # single-process deployment this is a reliable post-condition assertion; accept
        # the theoretical race rather than removing the safety guard
        if blob_dir.exists():
            raise BlobStoreError(
                f"Blob directory still exists after deletion: '{blob_dir}'. "
                "Manual cleanup required."
            )

        # clean up empty parent directories (photos/ or gpx/ and then activity dir)
        _remove_empty_parents(blob_dir.parent, stop_at=self._user_blobs_dir(user_id))

    def blob_exists(
        self,
        user_id: str,
        blob_key: str,
    ) -> bool:
        """Return True if the blob exists on the filesystem."""
        return self._locate_blob_dir(user_id, blob_key) is not None

    #
    # Extended helpers for image variants
    #

    def write_blob_variant(
        self,
        user_id: str,
        blob_key: str,
        variant: str,
        data: bytes,
    ) -> None:
        """Write a derived image variant (thumbnail) for an existing blob.

        Parameters
        ----------
        user_id : str
            Owning user identifier.
        blob_key : str
            Unique blob key (must already exist).
        variant : str
            ``thumbnail`` (the only supported derived variant).
        data : bytes
            Encoded image bytes.

        Raises
        ------
        BlobNotFoundError
            If the blob does not exist.
        BlobStoreError
            On write failure.
        """
        blob_dir = self._blob_dir_from_key(user_id, blob_key)

        if variant == BLOB_VARIANT_THUMBNAIL:
            filename = "thumbnail.jpg"
        else:
            raise BlobStoreError(f"Cannot write unknown variant: '{variant}'.")

        dest = blob_dir / filename
        tmp_fd, tmp_path = tempfile.mkstemp(
            dir=blob_dir, prefix=".variant_", suffix=".tmp"
        )
        try:
            with os.fdopen(tmp_fd, "wb") as fh:
                fh.write(data)
                fh.flush()
                os.fsync(fh.fileno())
            os.replace(tmp_path, dest)
        except Exception:
            try:
                os.unlink(tmp_path)
            except OSError:
                pass
            raise


def _remove_empty_parents(directory: pathlib.Path, stop_at: pathlib.Path) -> None:
    """Remove empty parent directories up to (but not including) stop_at."""
    current = directory
    while current != stop_at and current.is_dir():
        try:
            if not any(current.iterdir()):
                current.rmdir()
            else:
                break
        except OSError:
            break
        current = current.parent
