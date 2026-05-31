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

"""Activity-level blob service: business rules for recordings and photo attachments."""

import datetime
import hashlib
import io
import shutil
import time
import traceback
import typing
import uuid

from mytral import app_logger
from mytral.backends import entities
from mytral.backends.datasets.dataset_json import JsonUsersDataset
from mytral.blobstore import image_processing
from mytral.blobstore.abc import BlobStoreAbc
from mytral.blobstore.exceptions import BlobNotFoundError
from mytral.blobstore.exceptions import BlobStoreError
from mytral.blobstore.exceptions import BlobValidationError
from mytral.blobstore.models import BLOB_VARIANT_THUMBNAIL
from mytral.blobstore.models import BlobKind
from mytral.blobstore.models import BlobMetadata
from mytral.blobstore.models import BlobOwnerKind
from mytral.blobstore.validation import parse_gpx
from mytral.blobstore.validation import validate_blob_metadata
from mytral.blobstore.validation import validate_photo
from mytral.blobstore.validation import validate_recording
from mytral.config import MytralConfig
from mytral.recordings import gpx_extractor


def _now_iso() -> str:
    return datetime.datetime.now(datetime.timezone.utc).isoformat()


def _sha256_hex(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def _new_blob_key() -> str:
    return str(uuid.uuid4()).replace("-", "")


class ActivityBlobService:
    """Business rules for attaching GPX files and photos to activities.

    Parameters
    ----------
    store : BlobStoreAbc
        Underlying blob store backend.
    dataset : JsonUsersDataset
        MyTraL user dataset used to load and persist activity entities.
    config : MytralConfig
        Application configuration instance for limit configuration.
    """

    def __init__(
        self, store: BlobStoreAbc, dataset: JsonUsersDataset, config: MytralConfig
    ) -> None:
        self._store = store
        self._ds = dataset
        self._config = config
        self._logger = app_logger

    #
    # Internal helpers
    #

    def _get_activity(self, user_id: str, activity_key: str) -> entities.ActivityEntity:
        dataset_name = self._ds.profile(user_id).dataset_name
        try:
            return self._ds.get_activity(
                user_id=user_id,
                dataset_name=dataset_name,
                key=activity_key,
            )
        except (ValueError, KeyError) as exc:
            raise BlobValidationError(
                f"Activity '{activity_key}' not found for user '{user_id}'."
            ) from exc

    def _save_activity(self, user_id: str, activity: entities.ActivityEntity) -> None:
        dataset_name = self._ds.profile(user_id).dataset_name
        self._ds.update_activity(
            user_id=user_id,
            dataset_name=dataset_name,
            entity=activity,
        )

    def _try_normalize_photo(
        self,
        data: bytes,
        extension: str,
    ) -> tuple[bytes, int, int]:
        """Normalize a photo upfront: strip EXIF, auto-rotate, resize.

        Returns (normalized_bytes, width, height).
        Falls back to the raw bytes when Pillow is unavailable.
        """
        try:
            norm_bytes, _fmt, w, h = image_processing.normalize_photo(
                data=data,
                extension=extension,
                max_dimension_px=self._config.blobstore_photo_max_dimension_px,
            )
            return norm_bytes, w, h
        except (BlobValidationError, ImportError) as exc:
            app_logger.warning("Photo normalization skipped for upload: %s", exc)
            return data, 0, 0

    def _try_generate_thumbnail(
        self,
        user_id: str,
        blob_key: str,
        norm_bytes: bytes,
    ) -> bool:
        """Generate and write the thumbnail variant.

        Returns True when the thumbnail was successfully stored.
        Falls back gracefully when Pillow is unavailable.
        """
        try:
            thumb_bytes = image_processing.generate_thumbnail(
                data=norm_bytes,
                max_dimension_px=self._config.blobstore_thumbnail_max_dimension_px,
            )
            if hasattr(self._store, "write_blob_variant"):
                self._store.write_blob_variant(
                    user_id, blob_key, BLOB_VARIANT_THUMBNAIL, thumb_bytes
                )
            return True
        except (BlobValidationError, BlobStoreError, ImportError) as exc:
            app_logger.warning(
                f"Thumbnail generation failed for blob '{blob_key}' "
                f"(user '%{user_id}'): {exc}",
                traceback=traceback.format_exc(),
            )
            return False

    #
    # Photo operations
    #

    def upload_photos(
        self,
        user_id: str,
        activity_key: str,
        uploaded_files: list[tuple[typing.BinaryIO, str]],
        *,
        name: str = "",
        description: str = "",
        keywords: str | list[str] = "",
    ) -> list[BlobMetadata]:
        """Upload one or more photos to an activity.

        Parameters
        ----------
        user_id : str
            Owning user identifier.
        activity_key : str
            Target activity key.
        uploaded_files : list[tuple[typing.BinaryIO, str]]
            List of ``(stream, original_filename)`` pairs.
        name : str
            Name applied to all uploaded photos.
        description : str
            Description applied to all uploaded photos.
        keywords : str | list[str]
            Keywords applied to all uploaded photos.

        Returns
        -------
        list[BlobMetadata]
            Metadata for each successfully stored photo.

        Raises
        ------
        BlobValidationError
            On validation failure, if the photo count limit would be exceeded,
            if any individual photo exceeds the per-photo size limit, or if the
            total upload size exceeds the per-request size limit.
        BlobStoreError
            On backend failure.
        """
        activity = self._get_activity(user_id, activity_key)
        max_count = self._config.blobstore_max_photo_count_per_activity
        current_count = len(activity.photo_blob_keys)
        if current_count + len(uploaded_files) > max_count:
            raise BlobValidationError(
                f"Cannot upload {len(uploaded_files)} photo(s): activity already has "
                f"{current_count} photo(s), limit is {max_count}."
            )

        name_v, desc_v, kw_v = validate_blob_metadata(name, description, keywords)

        stored: list[BlobMetadata] = []
        new_keys: list[str] = []
        total_bytes = 0

        for file_stream, original_filename in uploaded_files:
            data = file_stream.read(self._config.blobstore_max_photo_size_bytes + 1)
            if len(data) > self._config.blobstore_max_photo_size_bytes:
                max_mib = self._config.blobstore_max_photo_size_bytes // (1024 * 1024)
                raise BlobValidationError(
                    f"Photo '{original_filename}' exceeds the maximum allowed size of "
                    f"{max_mib} MiB."
                )
            total_bytes += len(data)
            if total_bytes > self._config.blobstore_max_photo_request_bytes:
                req_mib = self._config.blobstore_max_photo_request_bytes // (
                    1024 * 1024
                )
                raise BlobValidationError(
                    "Total size of uploaded photos exceeds the maximum allowed "
                    f"per-request size of {req_mib} MiB."
                )

            ext, width, height = validate_photo(
                filename=original_filename,
                data=data,
                max_bytes=self._config.blobstore_max_photo_size_bytes,
            )

            # normalize upfront: strip EXIF, auto-rotate, resize — the stored bytes
            # ARE the normalized version; no separate "original" is kept
            norm_bytes, norm_w, norm_h = self._try_normalize_photo(data, ext)
            stored_w = norm_w or width
            stored_h = norm_h or height

            blob_key = _new_blob_key()
            now = _now_iso()
            ext_to_mime = {
                ".jpg": "image/jpeg",
                ".jpeg": "image/jpeg",
                ".png": "image/png",
                ".webp": "image/webp",
            }

            metadata = BlobMetadata(
                blob_key=blob_key,
                user_id=user_id,
                owner_kind=BlobOwnerKind.ACTIVITY.value,
                owner_key=activity_key,
                kind=BlobKind.ACTIVITY_PHOTO.value,
                file_name=f"normalized{ext}",
                original_file_name=original_filename,
                extension=ext,
                content_type=ext_to_mime.get(ext, "image/jpeg"),
                size_bytes=len(norm_bytes),
                sha256=_sha256_hex(norm_bytes),
                name=name_v,
                description=desc_v,
                keywords=kw_v,
                created_at=now,
                updated_at=now,
                width=stored_w,
                height=stored_h,
            )

            self._store.create_blob(metadata, io.BytesIO(norm_bytes))
            new_keys.append(blob_key)

            # generate thumbnail; update metadata with thumbnail flag
            thumb_ok = self._try_generate_thumbnail(user_id, blob_key, norm_bytes)
            if thumb_ok:
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

            stored.append(metadata)

        # update activity with new blob keys; compensate on failure
        activity.photo_blob_keys = list(activity.photo_blob_keys) + new_keys
        if not activity.highlight_photo_blob_key and activity.photo_blob_keys:
            activity.highlight_photo_blob_key = activity.photo_blob_keys[0]

        try:
            self._save_activity(user_id, activity)
        except Exception as exc:
            # compensate: delete all newly stored blobs
            for key in new_keys:
                try:
                    self._store.delete_blob(user_id, key)
                except BlobStoreError:
                    pass
            raise BlobStoreError(
                f"Failed to persist activity blob references: {exc}"
            ) from exc

        return stored

    def list_photos(self, user_id: str, activity_key: str) -> list[BlobMetadata]:
        """Return metadata for all photos attached to an activity."""
        activity = self._get_activity(user_id, activity_key)
        if not activity.photo_blob_keys:
            return []
        photos: list[BlobMetadata] = []
        for key in activity.photo_blob_keys:
            try:
                photos.append(self._store.get_blob_metadata(user_id, key))
            except BlobNotFoundError:
                continue
        return photos

    def open_photo(
        self,
        user_id: str,
        activity_key: str,
        blob_key: str,
        variant: str = "original",
    ) -> tuple[typing.BinaryIO, BlobMetadata]:
        """Open a photo stream for a given variant.

        Returns
        -------
        tuple[typing.BinaryIO, BlobMetadata]
            ``(stream, metadata)``

        Raises
        ------
        BlobValidationError
            If the blob_key is not attached to the activity.
        BlobNotFoundError
            If the blob or variant does not exist.
        """
        activity = self._get_activity(user_id, activity_key)
        if blob_key not in activity.photo_blob_keys:
            raise BlobValidationError(
                f"Photo '{blob_key}' is not attached to activity '{activity_key}'."
            )
        meta = self._store.get_blob_metadata(user_id, blob_key)
        if meta.user_id != user_id:
            raise BlobValidationError(
                f"Blob '{blob_key}' does not belong to user '{user_id}'."
            )
        stream = self._store.open_blob(user_id, blob_key, variant=variant)
        return stream, meta

    def update_photo_metadata(
        self,
        user_id: str,
        activity_key: str,
        blob_key: str,
        *,
        name: str,
        description: str,
        keywords: str | list[str],
    ) -> BlobMetadata:
        """Update user-editable metadata for a photo.

        Raises
        ------
        BlobValidationError
            If the photo is not attached to the activity or validation fails.
        """
        activity = self._get_activity(user_id, activity_key)
        if blob_key not in activity.photo_blob_keys:
            raise BlobValidationError(
                f"Photo '{blob_key}' is not attached to activity '{activity_key}'."
            )
        name_v, desc_v, kw_v = validate_blob_metadata(name, description, keywords)
        return self._store.update_blob_metadata(
            user_id, blob_key, name=name_v, description=desc_v, keywords=kw_v
        )

    def set_highlight_photo(
        self, user_id: str, activity_key: str, blob_key: str
    ) -> None:
        """Set a photo as the activity highlight.

        Raises
        ------
        BlobValidationError
            If the blob_key is not attached to the activity.
        """
        activity = self._get_activity(user_id, activity_key)
        if blob_key not in activity.photo_blob_keys:
            raise BlobValidationError(
                f"Photo '{blob_key}' is not attached to activity '{activity_key}'."
            )
        activity.highlight_photo_blob_key = blob_key
        self._save_activity(user_id, activity)

    def delete_photo(self, user_id: str, activity_key: str, blob_key: str) -> None:
        """Delete a photo from an activity with no-relic guarantee.

        If the deleted photo was the highlight, the first remaining photo
        becomes the new highlight; the highlight is cleared if no photos remain.

        Raises
        ------
        BlobValidationError
            If the photo is not attached to the activity.
        BlobStoreError
            On backend failure or if the JSON update fails after blob deletion.
        """
        activity = self._get_activity(user_id, activity_key)
        if blob_key not in activity.photo_blob_keys:
            raise BlobValidationError(
                f"Photo '{blob_key}' is not attached to activity '{activity_key}'."
            )

        self._store.delete_blob(user_id, blob_key)

        remaining = [k for k in activity.photo_blob_keys if k != blob_key]
        activity.photo_blob_keys = remaining

        if activity.highlight_photo_blob_key == blob_key:
            activity.highlight_photo_blob_key = remaining[0] if remaining else ""

        try:
            self._save_activity(user_id, activity)
        except Exception as exc:
            raise BlobStoreError(
                f"Photo blob deleted but activity reference update failed: {exc}. "
                "The activity JSON has a stale reference that must be cleared."
            ) from exc

    def delete_all_activity_blobs(self, user_id: str, activity_key: str) -> None:
        """Delete all blobs belonging to an activity (GPX + all photos).

        Intended to be called just before the activity itself is deleted so
        that no orphaned blob data is left on the storage backend.  Errors per
        individual blob are silently ignored — the caller should proceed with
        activity deletion regardless.

        Parameters
        ----------
        user_id : str
            Owning user identifier.
        activity_key : str
            Activity primary key.
        """
        blobs = self._store.list_blobs(
            user_id=user_id,
            owner_kind=BlobOwnerKind.ACTIVITY.value,
            owner_key=activity_key,
        )
        for meta in blobs:
            try:
                self._store.delete_blob(user_id, meta.blob_key)
            except Exception:
                pass

    def cleanup_orphan_recordings(self, user_id: str) -> int:
        """Delete recording and parquet blobs whose activity no longer exists.

        Walks the filesystem blob store under the activities directory,
        checks each ``activity_key`` against the dataset, and removes
        orphaned blob directories.  Returns the count of cleaned activity
        directories.

        Parameters
        ----------
        user_id : str
            Owning user identifier.

        Returns
        -------
        int
            Number of orphan activity directories removed.
        """
        persistence_dir = self._config.persistence_data_dir
        if persistence_dir is None:
            return 0
        activities_dir = persistence_dir / user_id / "blobs" / "activities"
        if not activities_dir.is_dir():
            return 0

        cleaned = 0
        for child in activities_dir.iterdir():
            if not child.is_dir():
                continue
            activity_key = child.name
            try:
                self._get_activity(user_id, activity_key)
            except BlobValidationError:
                # activity no longer exists — delete orphan blobs
                try:
                    shutil.rmtree(child, ignore_errors=True)
                    cleaned += 1
                    app_logger.info(
                        f"Cleaned orphan blobs for activity {activity_key} "
                        f"(user {user_id})"
                    )
                except OSError as exc:
                    app_logger.warning(
                        f"Failed to clean orphan blobs for activity "
                        f"{activity_key} (user {user_id}): {exc}"
                    )
        return cleaned

    #
    # Recording operations
    #

    def upload_recording(
        self,
        user_id: str,
        activity_key: str,
        uploaded_file: typing.BinaryIO,
        original_filename: str,
        content_type: str = "",
        *,
        name: str = "",
        description: str = "",
        keywords: str | list[str] = "",
        activity: entities.ActivityEntity | None = None,
        skip_persist: bool = False,
    ) -> BlobMetadata:
        """Upload a recording file (FIT / GPX / HRM) for an activity.

        Parameters
        ----------
        user_id : str
            Owning user identifier.
        activity_key : str
            Target activity key.
        uploaded_file : typing.BinaryIO
            Binary stream of the recording upload.
        original_filename : str
            Original filename as provided by the browser.
        content_type : str
            MIME type from the browser (optional).
        name : str
            Human-readable name for the blob.
        description : str
            Description text.
        keywords : str | list[str]
            Comma-separated string or list of keyword tags.
        activity : ActivityEntity or None
            Pre-loaded activity entity.  When provided, the activity is
            mutated in memory and ``_get_activity`` is skipped.  Useful
            with ``skip_persist`` for batched writes.
        skip_persist : bool
            When True, the activity JSON is not saved to disk.  The
            in-memory ``activity`` object is still updated so the caller
            can persist it later in a single write.

        Returns
        -------
        BlobMetadata
            Metadata of the newly stored blob.

        Raises
        ------
        BlobValidationError
            On validation failure or if activity does not exist (when
            ``activity`` is not provided).
        BlobStoreError
            On backend failure.
        """
        self._logger.info(
            f"BEGIN Uploading recording '{original_filename}' as '{user_id}'",
            filename=original_filename,
            content_type=content_type,
            user_id=user_id,
            name=name,
            description=description,
        )
        start_time = time.perf_counter()

        if activity is None:
            activity = self._get_activity(user_id, activity_key)
        # Ensure recorded_blob_keys is a list to avoid None errors
        if activity.recorded_blob_keys is None:
            activity.recorded_blob_keys = []
        name_v, desc_v, kw_v = validate_blob_metadata(name, description, keywords)

        data = uploaded_file.read(self._config.blobstore_max_recording_size_bytes + 1)
        ext = validate_recording(
            filename=original_filename,
            data=data,
            max_bytes=self._config.blobstore_max_recording_size_bytes,
        )

        blob_key = _new_blob_key()
        now = _now_iso()
        sha = _sha256_hex(data)

        metadata = BlobMetadata(
            blob_key=blob_key,
            user_id=user_id,
            owner_kind=BlobOwnerKind.ACTIVITY.value,
            owner_key=activity_key,
            kind=BlobKind.ACTIVITY_RECORDING.value,
            file_name=f"data{ext}",
            original_file_name=original_filename,
            extension=ext,
            content_type=content_type or "application/octet-stream",
            size_bytes=len(data),
            sha256=sha,
            name=name_v,
            description=desc_v,
            keywords=kw_v,
            created_at=now,
            updated_at=now,
        )

        self._store.create_blob(metadata, io.BytesIO(data))

        # update activity JSON reference; compensate on failure
        entry = f"{blob_key}{ext}"
        activity.recorded_blob_keys.append(entry)
        if skip_persist:
            app_logger.info(
                f"Recording upload: activity {activity_key} recording blob appended "
                f"(deferred persist)"
            )
        else:
            try:
                self._save_activity(user_id, activity)
                app_logger.info(
                    f"Recording upload: activity {activity_key} cache refreshed after "
                    f"recording add"
                )
            except Exception as exc:
                # attempt cleanup of the uploaded blob
                try:
                    self._store.delete_blob(user_id, blob_key)
                except BlobStoreError:
                    app_logger.error(
                        f"Failed to delete recording blob {blob_key} after activity "
                        f"reference update failure: {exc}",
                        traceback=traceback.format_exc(),
                    )
                    pass
                app_logger.error(
                    f"Recording upload failed to persist recording reference for "
                    f"activity {activity_key}: {exc}",
                    traceback=traceback.format_exc(),
                )
                raise BlobStoreError(
                    f"Failed to persist activity recording reference: {exc}"
                ) from exc

        duration = time.perf_counter() - start_time
        self._logger.info(
            f"DONE upload recording '{original_filename}' in {duration}s",
            filename=original_filename,
            content_type=content_type,
            user_id=user_id,
            name=name,
            description=description,
        )

        return metadata

    def ensure_gpx_map_data(
        self,
        user_id: str,
        activity_key: str,
        blob_key: str,
        *,
        refresh_legacy: bool = False,
    ) -> BlobMetadata:
        """Ensure GPX map metadata exists for the selected recording blob.

        Parameters
        ----------
        user_id : str
            Owning user identifier.
        activity_key : str
            Target activity key.
        blob_key : str
            Recording blob key.
        refresh_legacy : bool
            Whether legacy summary/profile payload should be recomputed when
            metadata exists but predates current GPX map storage format.

        Returns
        -------
        BlobMetadata
            Up-to-date blob metadata with summary map payload when available.
        """
        activity = self._get_activity(user_id=user_id, activity_key=activity_key)
        if blob_key not in [
            entities.recording_blob_uuid(e) for e in activity.recorded_blob_keys
        ]:
            raise BlobValidationError(
                f"Recording '{blob_key}' is not attached to activity '{activity_key}'."
            )

        meta = self._store.get_blob_metadata(user_id=user_id, blob_key=blob_key)
        if meta.extension != ".gpx":
            return meta

        if meta.summary_polyline and meta.summary_bbox:
            if not refresh_legacy:
                return meta
            should_refresh_summary = False
            if meta.updated_at == meta.created_at and (
                not meta.full_polyline or meta.elevation_profile is None
            ):
                try:
                    summary_points = gpx_extractor.decode_polyline(
                        meta.summary_polyline
                    )
                    should_refresh_summary = len(summary_points) >= 150
                except Exception:
                    should_refresh_summary = True
            if not should_refresh_summary:
                return meta

        stream, _ = self.open_recording(
            user_id=user_id,
            activity_key=activity_key,
            blob_key=blob_key,
        )
        try:
            gpx_data = stream.read()
        finally:
            stream.close()
        track_count = meta.track_count
        track_point_count = meta.track_point_count
        try:
            track_count, track_point_count = parse_gpx(data=gpx_data)
            gps_points = gpx_extractor.extract_gps_points(gpx_data=gpx_data)
            summary_polyline, summary_bbox, full_polyline = (
                gpx_extractor.encode_gps_polylines(points=gps_points)
            )
            elevation_profile = gpx_extractor.simplify_elevation_profile(
                gpx_extractor.extract_elevation_profile(gpx_data=gpx_data)
            )
        except Exception as exc:
            raise BlobValidationError(
                f"Failed to generate GPX map data for recording '{blob_key}': {exc}"
            ) from exc

        return self._store.update_blob_metadata(
            user_id=user_id,
            blob_key=blob_key,
            name=meta.name,
            description=meta.description,
            keywords=meta.keywords,
            track_count=track_count,
            track_point_count=track_point_count,
            summary_polyline=summary_polyline,
            summary_bbox=summary_bbox,
            full_polyline=full_polyline,
            elevation_profile=elevation_profile,
        )

    def upload_recording_with_parquet(
        self,
        user_id: str,
        activity_key: str,
        uploaded_file: typing.BinaryIO,
        original_filename: str,
        content_type: str = "",
        *,
        name: str = "",
        description: str = "",
        keywords: str | list[str] = "",
        parquet_bytes: bytes | None = None,
    ) -> BlobMetadata:
        """Upload a recording file and immediately generate parquet (synchronous).

        This is a convenience method that combines upload_recording() with
        immediate parquet conversion. Useful for tests and sync operations.

        Parameters
        ----------
        user_id : str
            Owning user identifier.
        activity_key : str
            Target activity key.
        uploaded_file : typing.BinaryIO
            Binary stream of the recording upload.
        original_filename : str
            Original filename as provided by the browser.
        content_type : str
            MIME type from the browser (optional).
        name : str
            Human-readable name for the blob.
        description : str
            Description text.
        keywords : str | list[str]
            Comma-separated string or list of keyword tags.
        parquet_bytes : bytes | None
            Pre-generated Parquet bytes to store. If not provided, it will
            be generated from the recording file.

        Returns
        -------
        BlobMetadata
            Metadata of the newly stored recording blob.

        Raises
        ------
        BlobValidationError
            On validation failure or if activity does not exist.
        BlobStoreError
            On backend failure.
        """
        from mytral.recordings import parquet_converter

        # upload the recording first
        metadata = self.upload_recording(
            user_id=user_id,
            activity_key=activity_key,
            uploaded_file=uploaded_file,
            original_filename=original_filename,
            content_type=content_type,
            name=name,
            description=description,
            keywords=keywords,
        )

        # now convert to parquet and save
        try:
            is_generated = False
            if parquet_bytes is None:
                is_generated = True
                # read the blob we just uploaded
                result = self.open_recording(user_id, activity_key, metadata.blob_key)
                stream, _meta = result
                data = stream.read()

                # convert based on extension
                ext = metadata.extension.lower()
                if ext == ".fit":
                    parquet_bytes = parquet_converter.fit_to_parquet(data)
                elif ext == ".gpx":
                    parquet_bytes = parquet_converter.gpx_to_parquet(data)
                elif ext == ".hrm":
                    # polar_hrm must be imported here as it is used for parsing
                    # but parquet_converter already does its own thing
                    # actually hrm_to_parquet in parquet_converter expects a dict
                    # let's re-verify parquet_converter.hrm_to_parquet
                    from mytral.integrations import polar_hrm

                    hrm_dict = polar_hrm.parse_hrm(data.decode("utf-8", "ignore"))
                    parquet_bytes = parquet_converter.hrm_to_parquet(hrm_dict)
                else:
                    # unknown format, skip parquet generation
                    app_logger.warning(
                        f"Unknown extension '{ext}' for blob {metadata.blob_key}, "
                        f"skipping parquet generation"
                    )
                    return metadata

            # save the parquet
            self.save_parquet(
                user_id=user_id,
                activity_key=activity_key,
                source_blob_key=metadata.blob_key,
                parquet_data=parquet_bytes,
            )
            app_logger.info(
                f"Parquet {'generated' if is_generated else 'provided'} "
                f"for recording {metadata.blob_key}"
            )
        except Exception as exc:
            # log the error but don't fail the upload
            app_logger.error(
                f"Failed to generate parquet for recording {metadata.blob_key}: {exc}",
                traceback=traceback.format_exc(),
            )

        return metadata

    def get_recording(
        self, user_id: str, activity_key: str, blob_key: str
    ) -> BlobMetadata | None:
        """Return recording blob metadata, or None if the blob is not found.

        Parameters
        ----------
        user_id : str
            Owning user identifier.
        activity_key : str
            Activity primary key.
        blob_key : str
            Blob UUID of the recording.

        Returns
        -------
        BlobMetadata | None
        """
        try:
            return self._store.get_blob_metadata(user_id, blob_key)
        except BlobNotFoundError:
            return None

    def list_recordings(self, user_id: str, activity_key: str) -> list[BlobMetadata]:
        """List all recording blobs attached to an activity.

        Parameters
        ----------
        user_id : str
            Owning user identifier.
        activity_key : str
            Activity primary key.

        Returns
        -------
        list[BlobMetadata]
        """
        activity = self._get_activity(user_id, activity_key)
        result: list[BlobMetadata] = []
        for entry in activity.recorded_blob_keys:
            uuid_ = entities.recording_blob_uuid(entry)
            try:
                result.append(self._store.get_blob_metadata(user_id, uuid_))
            except BlobNotFoundError:
                pass
        return result

    def delete_recording(self, user_id: str, activity_key: str, blob_key: str) -> None:
        """Delete a single recording blob from an activity.

        Parameters
        ----------
        user_id : str
            Owning user identifier.
        activity_key : str
            Activity primary key.
        blob_key : str
            Blob UUID of the recording to delete.

        Raises
        ------
        BlobValidationError
            If the recording is not found in the activity.
        BlobStoreError
            On backend failure.
        """
        from mytral.backends import entities as _entities

        activity = self._get_activity(user_id, activity_key)
        entry_to_remove: str | None = None
        for entry in activity.recorded_blob_keys:
            if _entities.recording_blob_uuid(entry) == blob_key:
                entry_to_remove = entry
                break
        if entry_to_remove is None:
            raise BlobValidationError(
                f"Recording '{blob_key}' is not attached to activity '{activity_key}'."
            )

        self._store.delete_blob(user_id, blob_key)

        # remove parquet if present
        parquet_key = activity.recorded_parquet_keys.pop(blob_key, None)
        if parquet_key:
            try:
                self._store.delete_blob(user_id, parquet_key)
            except BlobNotFoundError:
                pass

        activity.recorded_blob_keys.remove(entry_to_remove)
        try:
            self._save_activity(user_id, activity)
        except Exception as exc:
            raise BlobStoreError(
                f"Recording deleted but activity reference update failed: {exc}."
            ) from exc

    def open_recording(
        self, user_id: str, activity_key: str, blob_key: str
    ) -> tuple[typing.BinaryIO, BlobMetadata]:
        """Open a recording data stream for download.

        Parameters
        ----------
        user_id : str
            Owning user identifier.
        activity_key : str
            Activity primary key.
        blob_key : str
            Blob UUID of the recording.

        Returns
        -------
        tuple[typing.BinaryIO, BlobMetadata]
            ``(stream, metadata)``

        Raises
        ------
        BlobValidationError
            If the recording is not attached to the activity.
        BlobNotFoundError
            If the blob no longer exists in the store.
        """
        from mytral.backends import entities as _entities

        activity = self._get_activity(user_id, activity_key)
        found = any(
            _entities.recording_blob_uuid(e) == blob_key
            for e in activity.recorded_blob_keys
        )
        if not found:
            raise BlobValidationError(
                f"Recording '{blob_key}' is not attached to activity '{activity_key}'."
            )
        meta = self._store.get_blob_metadata(user_id, blob_key)
        if meta.user_id != user_id:
            raise BlobValidationError(
                f"Blob '{blob_key}' does not belong to user '{user_id}'."
            )
        stream = self._store.open_blob(user_id, blob_key)
        return stream, meta

    def save_parquet(
        self,
        user_id: str,
        activity_key: str,
        source_blob_key: str,
        parquet_data: bytes,
        *,
        activity: entities.ActivityEntity | None = None,
        skip_persist: bool = False,
    ) -> str:
        """Store a Parquet blob and register it against the source recording.

        Parameters
        ----------
        user_id : str
            Owning user identifier.
        activity_key : str
            Activity primary key.
        source_blob_key : str
            Blob UUID of the source recording (FIT/GPX/HRM).
        parquet_data : bytes
            Parquet-encoded bytes to store.
        activity : ActivityEntity or None
            Pre-loaded activity entity.  When provided, the activity is
            mutated in memory and ``_get_activity`` is skipped.  Useful
            with ``skip_persist`` for batched writes.
        skip_persist : bool
            When True, the activity JSON is not saved to disk.  The
            in-memory ``activity`` object is still updated so the caller
            can persist it later in a single write.

        Returns
        -------
        str
            Blob UUID of the newly created Parquet blob.

        Raises
        ------
        BlobStoreError
            On backend failure.
        """
        if activity is None:
            activity = self._get_activity(user_id, activity_key)
        parquet_key = _new_blob_key()
        now = _now_iso()
        sha = _sha256_hex(parquet_data)

        metadata = BlobMetadata(
            blob_key=parquet_key,
            user_id=user_id,
            owner_kind=BlobOwnerKind.ACTIVITY.value,
            owner_key=activity_key,
            kind=BlobKind.ACTIVITY_PARQUET.value,
            file_name="data.parquet",
            original_file_name="data.parquet",
            extension=".parquet",
            content_type="application/octet-stream",
            size_bytes=len(parquet_data),
            sha256=sha,
            name="",
            description="",
            keywords=[],
            created_at=now,
            updated_at=now,
        )
        self._store.create_blob(metadata, io.BytesIO(parquet_data))

        # delete old parquet if it exists
        old_parquet_key = activity.recorded_parquet_keys.get(source_blob_key)
        if old_parquet_key:
            try:
                self._store.delete_blob(user_id, old_parquet_key)
            except BlobNotFoundError:
                pass

        activity.recorded_parquet_keys[source_blob_key] = parquet_key
        if skip_persist:
            app_logger.info(
                f"Parquet blob {parquet_key} linked to activity {activity_key} "
                f"(deferred persist)"
            )
        else:
            try:
                self._save_activity(user_id, activity)
                app_logger.info(
                    f"Parquet saved: activity {activity_key} cache refreshed after "
                    f"parquet add"
                )
            except Exception as exc:
                try:
                    self._store.delete_blob(user_id, parquet_key)
                except BlobStoreError:
                    pass
                raise BlobStoreError(
                    f"Failed to persist Parquet reference: {exc}"
                ) from exc

        return parquet_key

    def open_parquet(
        self,
        user_id: str,
        activity_key: str,
        source_blob_key: str,
    ) -> tuple[typing.BinaryIO, BlobMetadata] | None:
        """Open the Parquet data stream for a given source recording.

        Parameters
        ----------
        user_id : str
            Owning user identifier.
        activity_key : str
            Activity primary key.
        source_blob_key : str
            Blob UUID of the source recording.

        Returns
        -------
        tuple[typing.BinaryIO, BlobMetadata] | None
            ``(stream, metadata)`` or None when no Parquet exists yet.
        """
        activity = self._get_activity(user_id, activity_key)
        parquet_key = activity.recorded_parquet_keys.get(source_blob_key)
        if not parquet_key:
            return None
        try:
            meta = self._store.get_blob_metadata(user_id, parquet_key)
            stream = self._store.open_blob(user_id, parquet_key)
            return stream, meta
        except BlobNotFoundError:
            return None
