# MyTraL: my trailing log
#
# Copyright (C) 2015-2026 Martin Dvorak <martin.dvorak@mindforger.com>
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

"""Async task: import Strava user ZIP archive data."""

import datetime
import gzip
import hashlib
import io
import json
import os
import pathlib
import traceback
import uuid

from mytral import config as mytral_config
from mytral import plugins
from mytral import tasks
from mytral.backends import entities
from mytral.blobstore import activity_service as blob_svc_module
from mytral.blobstore import image_processing
from mytral.blobstore.filesystem import FilesystemBlobStore
from mytral.blobstore.models import BLOB_VARIANT_THUMBNAIL
from mytral.blobstore.models import BlobKind
from mytral.blobstore.models import BlobMetadata
from mytral.blobstore.models import BlobOwnerKind
from mytral.integrations import strava_user_archive
from mytral.recordings import gpx_extractor
from mytral.recordings import parquet_converter
from mytral.recordings import tcx_extractor
from mytral.tasks import bulldozer
from mytral.tasks.do import strava_commons


class _PathEncoder(json.JSONEncoder):
    """JSON encoder that converts pathlib.Path objects to strings."""

    def default(self, o):
        if isinstance(o, pathlib.PurePath):
            return str(o)
        return super().default(o)


def _sandbox_blobs_dir(job_dir: pathlib.Path, user_id: str) -> pathlib.Path:
    """Return the sandbox blobstore root directory for a given job.

    Matches the internal layout of ``FilesystemBlobStore`` constructed with
    ``base_dir=MytralConfig(persistence_data_dir=job_dir/"work").user_data_dir``
    and ``blobs_subdir="blobs"``::

        job_dir / "work" / "data" / <user_id> / "blobs"
    """
    return job_dir / "work" / "data" / user_id / "blobs"


def _make_blob_metadata(
    user_id: str,
    activity_key: str,
    kind: str,
    file_name: str,
    original_file_name: str,
    extension: str,
    size_bytes: int,
    sha256: str,
    content_type: str = "application/octet-stream",
    name: str = "",
    description: str = "",
    keywords: list[str] | None = None,
    created_at: str = "",
    width: int = 0,
    height: int = 0,
    thumbnail_available: bool = False,
) -> BlobMetadata:
    """Create a ``BlobMetadata`` with consistent defaults for Strava imports."""
    return BlobMetadata(
        blob_key=str(uuid.uuid4()),
        user_id=user_id,
        owner_kind=BlobOwnerKind.ACTIVITY.value,
        owner_key=activity_key,
        kind=kind,
        file_name=file_name,
        original_file_name=original_file_name,
        extension=extension,
        content_type=content_type,
        size_bytes=size_bytes,
        sha256=sha256,
        name=name,
        description=description,
        keywords=keywords or [],
        created_at=created_at,
        updated_at=created_at,
        width=width,
        height=height,
        thumbnail_available=thumbnail_available,
    )


def _recording_summary_to_dict(summary) -> dict:
    """Convert a ``RecordingSummary`` to a plain dict for JSON serialization."""
    result: dict = {}
    for field_name in (
        "activity_type_key",
        "when",
        "hours",
        "minutes",
        "seconds",
        "distance",
        "kcal",
        "avg_hr",
        "max_hr",
        "avg_cadence",
        "max_cadence",
        "avg_speed",
        "max_speed",
        "avg_watts",
        "max_watts",
        "elevation_gain",
        "name_hint",
    ):
        value = getattr(summary, field_name, None)
        if value is not None:
            if isinstance(value, datetime.datetime):
                value = value.isoformat()
            result[field_name] = value
    return result


def _apply_summary_dict(activity: entities.ActivityEntity, summary_dict: dict) -> None:
    """Apply summary fields from a dict onto an activity (in-place).

    When the summary overwrites duration fields (hours/minutes/seconds), the
    distance, avg_speed and max_speed are also taken from the summary to keep
    motion data internally consistent.  Mixing CSV-provided distance with
    recording-derived duration would otherwise produce nonsensical speeds.
    """
    if summary_dict.get("activity_type_key") and not activity.activity_type_key:
        activity.activity_type_key = summary_dict["activity_type_key"]
    when_str = summary_dict.get("when")
    if when_str:
        try:
            when = datetime.datetime.fromisoformat(when_str)
            activity.when_year = when.year
            activity.when_month = when.month
            activity.when_day = when.day
            activity.when_hour = when.hour
            activity.when_minute = when.minute
            activity.when_second = when.second
        except (ValueError, TypeError):
            pass

    # duration overwrite from summary → also take distance and speed from summary
    duration_from_summary = False
    d_hours = summary_dict.get("hours")
    if d_hours is not None and activity.hours == 0:
        activity.hours = d_hours
        duration_from_summary = True
    d_mins = summary_dict.get("minutes")
    if d_mins is not None and activity.minutes == 0:
        activity.minutes = d_mins
        duration_from_summary = True
    d_secs = summary_dict.get("seconds")
    if d_secs is not None and activity.seconds == 0:
        activity.seconds = d_secs
        duration_from_summary = True

    if duration_from_summary:
        if summary_dict.get("distance"):
            activity.distance = summary_dict["distance"]
        if summary_dict.get("avg_speed"):
            activity.avg_speed = summary_dict["avg_speed"]
        if summary_dict.get("max_speed"):
            activity.max_speed = summary_dict["max_speed"]
    else:
        # CSV duration is valid — apply distance/speed independently (only when 0)
        if summary_dict.get("distance") and activity.distance == 0:
            activity.distance = summary_dict["distance"]
        if summary_dict.get("avg_speed") and activity.avg_speed == 0.0:
            activity.avg_speed = summary_dict["avg_speed"]
        if summary_dict.get("max_speed") and activity.max_speed == 0.0:
            activity.max_speed = summary_dict["max_speed"]

    if summary_dict.get("kcal") and activity.kcal == 0:
        activity.kcal = summary_dict["kcal"]
    if summary_dict.get("avg_hr") and activity.avg_hr == 0:
        activity.avg_hr = summary_dict["avg_hr"]
    if summary_dict.get("max_hr") and activity.max_hr == 0:
        activity.max_hr = summary_dict["max_hr"]
    if summary_dict.get("avg_cadence") and activity.avg_cadence == 0:
        activity.avg_cadence = summary_dict["avg_cadence"]
    if summary_dict.get("max_cadence") and activity.max_cadence == 0:
        activity.max_cadence = summary_dict["max_cadence"]
    if summary_dict.get("elevation_gain") and activity.elevation_gain == 0:
        activity.elevation_gain = summary_dict["elevation_gain"]
    if summary_dict.get("name_hint") and not activity.name:
        activity.name = summary_dict["name_hint"]


def _split_evenly(items: list, num_chunks: int) -> list[list]:
    """Split *items* into *num_chunks* chunks using round-robin distribution."""
    if not items or num_chunks <= 1:
        return [items]
    chunks: list[list] = [[] for _ in range(num_chunks)]
    for i, item in enumerate(items):
        chunks[i % num_chunks].append(item)
    return [c for c in chunks if c]


def _strava_blob_job(job_key: int, job_dir: pathlib.Path) -> None:
    """Bulldozer job: process Strava archive photos and recordings in a sandbox.

    Reads ``job_dir/input/payload.json`` and processes each activity:
    uploads photos and/or recordings to the sandbox blobstore, generates
    Parquet, and extracts recording summaries.

    On failure writes ``job_dir/output/error.json``.
    """
    try:
        _strava_blob_job_impl(job_key, job_dir)
    except Exception:
        error_file = job_dir / "output" / "error.json"
        error_file.parent.mkdir(parents=True, exist_ok=True)
        with open(error_file, "w") as fh:
            json.dump(
                {
                    "job_key": job_key,
                    "job_dir": str(job_dir),
                    "traceback": traceback.format_exc(),
                },
                fh,
            )


def _strava_blob_job_impl(job_key: int, job_dir: pathlib.Path) -> None:
    """Implementation of :func:`_strava_blob_job`."""
    input_file = job_dir / "input" / "payload.json"
    if not input_file.exists():
        return

    with open(input_file) as fh:
        payload = json.load(fh)

    activities_data = payload.get("activities", [])
    if not activities_data:
        return

    user_id = payload.get("user_id", "")
    data_dir = pathlib.Path(payload.get("data_dir", ""))
    import_photos = payload.get("import_photos", True)
    import_recordings = payload.get("import_recordings", True)

    # create isolated blobstore inside the sandbox
    sandbox_config = mytral_config.MytralConfig(persistence_data_dir=job_dir / "work")
    sandbox_store = FilesystemBlobStore(
        base_dir=sandbox_config.user_data_dir,
        blobs_subdir="blobs",
    )

    now = datetime.datetime.now(datetime.timezone.utc).isoformat()
    summaries: dict[str, dict] = {}

    for d in activities_data:
        activity_key = d["key"]

        # upload photos
        photo_paths = d.get("_photo_paths") or []
        if import_photos and photo_paths:
            new_photo_keys = d.get("photo_blob_keys") or []
            for rel_path in photo_paths:
                photo_path = data_dir / rel_path
                if not photo_path.is_file():
                    continue
                try:
                    raw_bytes = photo_path.read_bytes()
                except OSError:
                    continue

                ext = photo_path.suffix.lower()
                # normalize: strip EXIF, auto-rotate, resize
                try:
                    norm_bytes, _fmt, norm_w, norm_h = image_processing.normalize_photo(
                        data=raw_bytes,
                        extension=ext,
                        max_dimension_px=4096,
                    )
                except Exception:
                    norm_bytes, norm_w, norm_h = raw_bytes, 0, 0

                sha = hashlib.sha256(norm_bytes).hexdigest()
                ext_to_mime = {
                    ".jpg": "image/jpeg",
                    ".jpeg": "image/jpeg",
                    ".png": "image/png",
                    ".webp": "image/webp",
                }
                photo_meta = _make_blob_metadata(
                    user_id=user_id,
                    activity_key=activity_key,
                    kind=BlobKind.ACTIVITY_PHOTO.value,
                    file_name=f"normalized{ext}",
                    original_file_name=photo_path.name,
                    extension=ext,
                    size_bytes=len(norm_bytes),
                    sha256=sha,
                    content_type=ext_to_mime.get(ext, "application/octet-stream"),
                    created_at=now,
                    width=norm_w,
                    height=norm_h,
                )
                sandbox_store.create_blob(photo_meta, io.BytesIO(norm_bytes))
                new_photo_keys.append(photo_meta.blob_key)

                # generate thumbnail
                try:
                    thumb_bytes = image_processing.generate_thumbnail(
                        data=norm_bytes,
                        max_dimension_px=1440,
                    )
                    sandbox_store.write_blob_variant(
                        user_id,
                        photo_meta.blob_key,
                        BLOB_VARIANT_THUMBNAIL,
                        thumb_bytes,
                    )
                    photo_meta.thumbnail_available = True
                    # update metadata on disk with thumbnail flag + dimensions
                    sandbox_store.update_blob_metadata(
                        user_id=user_id,
                        blob_key=photo_meta.blob_key,
                        name=photo_meta.name,
                        description=photo_meta.description,
                        keywords=photo_meta.keywords,
                        thumbnail_available=True,
                        width=photo_meta.width,
                        height=photo_meta.height,
                    )
                except Exception:
                    pass

            d["photo_blob_keys"] = new_photo_keys
            if new_photo_keys and not d.get("highlight_photo_blob_key"):
                d["highlight_photo_blob_key"] = new_photo_keys[0]

        # import recording
        recording_path = d.get("_recording_path") or ""
        if not (import_recordings and recording_path):
            continue

        full_path = data_dir / recording_path
        if not full_path.is_file():
            continue

        suffixes = [s.lower() for s in full_path.suffixes]
        is_gz = len(suffixes) >= 2 and suffixes[-2:] in (
            [".gpx", ".gz"],
            [".tcx", ".gz"],
        )
        is_plain = suffixes[-1:] in ([".gpx"], [".tcx"])
        if not (is_plain or is_gz):
            continue

        try:
            raw_bytes = full_path.read_bytes()
            if is_gz:
                raw_bytes = gzip.decompress(raw_bytes)
        except (OSError, gzip.BadGzipFile):
            continue

        # determine normalized extension
        if suffixes[-1] == ".gz":
            norm_ext = suffixes[-2]  # .gpx or .tcx
        else:
            norm_ext = suffixes[-1]
        norm_name = full_path.with_suffix("").name if is_gz else full_path.name

        sha = hashlib.sha256(raw_bytes).hexdigest()

        rec_meta = _make_blob_metadata(
            user_id=user_id,
            activity_key=activity_key,
            kind=BlobKind.ACTIVITY_RECORDING.value,
            file_name=f"data{norm_ext}",
            original_file_name=norm_name,
            extension=norm_ext,
            size_bytes=len(raw_bytes),
            sha256=sha,
            name="Strava recording",
            description="Imported from Strava archive",
            keywords=["strava", "archive"],
            created_at=now,
        )
        sandbox_store.create_blob(rec_meta, io.BytesIO(raw_bytes))

        # update activity recording reference
        recorded_keys = d.get("recorded_blob_keys") or []
        recorded_keys.append(f"{rec_meta.blob_key}{norm_ext}")
        d["recorded_blob_keys"] = recorded_keys

        # generate parquet
        try:
            if norm_ext == ".tcx":
                pq_bytes = parquet_converter.tcx_to_parquet(raw_bytes)
            else:
                pq_bytes = parquet_converter.gpx_to_parquet(raw_bytes)
        except Exception:
            continue

        pq_sha = hashlib.sha256(pq_bytes).hexdigest()
        pq_meta = _make_blob_metadata(
            user_id=user_id,
            activity_key=activity_key,
            kind=BlobKind.ACTIVITY_PARQUET.value,
            file_name="data.parquet",
            original_file_name="data.parquet",
            extension=".parquet",
            size_bytes=len(pq_bytes),
            sha256=pq_sha,
            created_at=now,
        )
        sandbox_store.create_blob(pq_meta, io.BytesIO(pq_bytes))

        # update activity parquet reference
        recorded_pq = d.get("recorded_parquet_keys") or {}
        recorded_pq[rec_meta.blob_key] = pq_meta.blob_key
        d["recorded_parquet_keys"] = recorded_pq

        # extract summary
        try:
            if norm_ext == ".tcx":
                summary = tcx_extractor.extract_tcx_summary(raw_bytes)
            else:
                summary = gpx_extractor.extract_gpx_summary(raw_bytes)
            if summary is not None:
                summaries[activity_key] = _recording_summary_to_dict(summary)
        except Exception:
            pass

    # write processed activities + summaries to output
    output_file = job_dir / "output" / "payload.json"
    output_file.parent.mkdir(parents=True, exist_ok=True)
    with open(output_file, "w") as fh:
        json.dump(
            {"activities": activities_data, "summaries": summaries},
            fh,
            cls=_PathEncoder,
        )


def _strava_gpx_map_job(job_key: int, job_dir: pathlib.Path) -> None:
    """Bulldozer job: precompute GPX map data for recording blobs.

    Reads ``job_dir/input/payload.json``.  For each recording blob that does not
    yet have ``summary_polyline`` / ``summary_bbox``, reads the raw GPX/TCX data
    from the main blobstore, parses GPS points, encodes polylines and extracts
    the elevation profile.

    Results are written to ``job_dir/output/payload.json``.
    On failure writes ``job_dir/output/error.json``.
    """
    try:
        _strava_gpx_map_job_impl(job_key, job_dir)
    except Exception:
        error_file = job_dir / "output" / "error.json"
        error_file.parent.mkdir(parents=True, exist_ok=True)
        with open(error_file, "w") as fh:
            json.dump(
                {
                    "job_key": job_key,
                    "job_dir": str(job_dir),
                    "traceback": traceback.format_exc(),
                },
                fh,
            )


def _strava_gpx_map_job_impl(job_key: int, job_dir: pathlib.Path) -> None:
    """Implementation of :func:`_strava_gpx_map_job`."""
    input_file = job_dir / "input" / "payload.json"
    if not input_file.exists():
        return

    with open(input_file) as fh:
        payload = json.load(fh)

    entries = payload.get("entries", [])
    if not entries:
        return

    user_id = payload.get("user_id", "")
    user_data_dir = pathlib.Path(payload.get("user_data_dir", ""))

    # open the *main* blobstore in read-only fashion
    main_store = FilesystemBlobStore(
        base_dir=user_data_dir,
        blobs_subdir="blobs",
    )

    results: dict[str, dict] = {}
    for entry in entries:
        blob_uuid = entry["blob_uuid"]
        extension = entry.get("extension", ".gpx")

        try:
            meta = main_store.get_blob_metadata(user_id, blob_uuid)
        except Exception:
            results[blob_uuid] = {"skipped": True, "error": "metadata not found"}
            continue

        if meta.summary_polyline and meta.summary_bbox:
            results[blob_uuid] = {"skipped": True, "reason": "already computed"}
            continue

        try:
            stream = main_store.open_blob(user_id, blob_uuid)
            try:
                gpx_data = stream.read()
            finally:
                stream.close()
        except Exception:
            results[blob_uuid] = {"skipped": True, "error": "cannot read recording"}
            continue

        try:
            if extension == ".tcx":
                track_count, track_point_count, gps_points, raw_profile = (
                    tcx_extractor.extract_all_from_tcx(gpx_data)
                )
            else:
                track_count, track_point_count, gps_points, raw_profile = (
                    gpx_extractor.extract_all_from_gpx(gpx_data)
                )
            elevation_profile = gpx_extractor.simplify_elevation_profile(raw_profile)
        except Exception:
            results[blob_uuid] = {"skipped": True, "error": "parse/extract failed"}
            continue

        if gps_points:
            summary_polyline, summary_bbox, full_polyline = (
                gpx_extractor.encode_gps_polylines(points=gps_points)
            )
        else:
            summary_polyline, summary_bbox, full_polyline = "", None, ""

        results[blob_uuid] = {
            "skipped": False,
            "summary_polyline": summary_polyline,
            "summary_bbox": list(summary_bbox) if summary_bbox else None,
            "full_polyline": full_polyline,
            "elevation_profile": elevation_profile,
            "track_count": track_count,
            "track_point_count": track_point_count,
        }

    output_file = job_dir / "output" / "payload.json"
    output_file.parent.mkdir(parents=True, exist_ok=True)
    with open(output_file, "w") as fh:
        json.dump({"results": results}, fh)


class StravaArchiveImportTask(tasks.TaskBase):
    """Import activities from a Strava user ZIP archive."""

    TASK_TYPE = "strava_archive_import"
    TASK_DISPLAY_NAME = "Strava Archive Import"

    DATA_DIR_KEY = strava_user_archive.STRAVA_ARCHIVE_DATA_DIR_KEY
    IMPORT_PHOTOS_KEY = "import_photos"
    IMPORT_RECORDINGS_KEY = "import_recordings"
    IMPORT_FROM_DATE_KEY = "import_from_date"
    IMPORT_TO_DATE_KEY = "import_to_date"

    def __init__(
        self,
        task_entity: tasks.TaskEntity,
        logger,
        log_callback,
        config=None,
        dataset=None,
        blobstore=None,
        enc_key="",
    ):
        super().__init__(
            task_entity=task_entity,
            logger=logger,
            log_callback=log_callback,
            config=config,
            dataset=dataset,
            blobstore=blobstore,
            enc_key=enc_key,
        )

    def execute(self) -> None:
        """Execute Strava archive import.

         Raises
        --
         RuntimeError
             On unrecoverable failures.
        """

        params = self.task_entity.parameters
        user_id: str = params["user_id"]
        dataset_name: str = params["dataset_name"]
        data_dir_str: str = params[StravaArchiveImportTask.DATA_DIR_KEY]
        on_conflict: str = str(params.get("on_conflict", "skip") or "skip")
        import_photos = strava_commons._to_bool(
            params.get(StravaArchiveImportTask.IMPORT_PHOTOS_KEY, True)
        )
        import_recordings = strava_commons._to_bool(
            params.get(StravaArchiveImportTask.IMPORT_RECORDINGS_KEY, True)
        )
        import_from_date = _parse_iso_date_param(
            params.get(StravaArchiveImportTask.IMPORT_FROM_DATE_KEY, ""),
            StravaArchiveImportTask.IMPORT_FROM_DATE_KEY,
        )
        import_to_date = _parse_iso_date_param(
            params.get(StravaArchiveImportTask.IMPORT_TO_DATE_KEY, ""),
            StravaArchiveImportTask.IMPORT_TO_DATE_KEY,
        )
        if import_from_date and import_to_date and import_from_date > import_to_date:
            raise RuntimeError(
                f"Invalid date range: {import_from_date.isoformat()} > "
                f"{import_to_date.isoformat()}"
            )

        self.log(f"Strava archive import started (dir={data_dir_str})")
        self.update_progress(2)

        data_dir = pathlib.Path(data_dir_str)
        if not data_dir.is_dir():
            raise RuntimeError(f"Data directory not found: {data_dir}")

        plugin: strava_user_archive.StravaUserArchiveActivitiesImportPlugin = (
            plugins.registry.get_plugin(
                strava_user_archive.StravaUserArchiveActivitiesImportPlugin.NAME
            )
        )
        plugin.logger = self.logger

        user_profile = self._dataset.profile(user_id)
        correlation_id: str = params.get("correlation_id", "")

        self.log("Parsing activities.csv from Strava archive...")
        self.update_progress(5)

        try:
            activities = plugin.import_activities(
                datasets={StravaArchiveImportTask.DATA_DIR_KEY: data_dir},
                user_profile=user_profile,
                correlation_id=correlation_id,
            )
        except Exception as exc:
            raise RuntimeError(f"Failed to parse Strava archive data: {exc}") from exc

        parsed_total = len(activities)
        self.log(f"Parsed {parsed_total} activities from {data_dir_str}")
        activities = _filter_activities_by_date_range(
            activities=activities,
            import_from_date=import_from_date,
            import_to_date=import_to_date,
        )
        activities, conflict_stats = self._apply_on_conflict(
            activities=activities,
            user_id=user_id,
            dataset_name=dataset_name,
            on_conflict=on_conflict,
        )
        overridden_keys = conflict_stats["overridden_keys"]
        total = len(activities)
        if parsed_total != total:
            self.log(
                f"Date range filter kept {total} of {parsed_total} activities "
                f"(from={import_from_date}, to={import_to_date})"
            )
        if conflict_stats["skipped"] > 0:
            self.log(
                f"Conflict resolution skipped {conflict_stats['skipped']} "
                f"activities (on_conflict={on_conflict})"
            )
        if conflict_stats["overridden"] > 0:
            self.log(
                f"Conflict resolution overriding {conflict_stats['overridden']} "
                f"activities (on_conflict={on_conflict})"
            )
        self.update_progress(10)

        if total == 0:
            self.log("No activities found — import complete")
            self.update_progress(100)
            return

        # PHASE 1: create activities in dataset
        self.update_progress(12)
        self._dataset.create_activities(
            user_id=user_id,
            dataset_name=dataset_name,
            entity_list=activities,
        )
        self.log(f"Created {total} activities in dataset '{dataset_name}'")
        self.update_progress(18)
        self.check_cancellation()

        # PHASE 2: clear blobs for overridden activities
        blob_svc = blob_svc_module.ActivityBlobService(
            store=self._blobstore,
            dataset=self._dataset,
            config=self._config,
        )
        for overridden_key in sorted(overridden_keys):
            try:
                blob_svc.delete_all_activity_blobs(
                    user_id=user_id,
                    activity_key=overridden_key,
                )
            except Exception as exc:
                self.log(
                    "  WARNING: failed to clear existing blobs for overridden "
                    f"activity {overridden_key}: {exc}"
                )
        self.update_progress(20)

        # PHASE 3: Bulldozer-parallelized photo + recording import
        self.log("Uploading photos & recordings...")

        # split activities evenly across workers
        workers = max(1, (os.cpu_count() or 1) // 2)
        chunks = _split_evenly(activities, min(workers, total))

        # create Bulldozer sandbox
        persistence_root = self._config.persistence_data_dir
        usr_task_dir = (
            persistence_root
            / mytral_config.MytralPersistenceFsConfig.DIR_DATA
            / user_id
            / mytral_config.MytralPersistenceFsConfig.DIR_TASKS
            / f"task-{self.task_entity.key}"
        )
        bzz = bulldozer.SubtaskBulldozer(
            usr_task_dir=usr_task_dir,
            logger=self.logger,
        )
        job_dirs = bzz.make_sandbox()
        job_dirs = job_dirs[: len(chunks)]

        # write each chunk to its job input directory
        for i, chunk in enumerate(chunks):
            input_file = job_dirs[i] / "input" / "payload.json"
            activities_payload = []
            for a in chunk:
                d = a.to_dict()
                d["_recording_path"] = getattr(a, "_recording_path", "")
                d["_photo_paths"] = getattr(a, "_photo_paths", []) or []
                activities_payload.append(d)
            with open(input_file, "w") as fh:
                json.dump(
                    {
                        "user_id": user_id,
                        "data_dir": str(data_dir),
                        "import_photos": import_photos,
                        "import_recordings": import_recordings,
                        "activities": activities_payload,
                    },
                    fh,
                    cls=_PathEncoder,
                )

        self.log(
            f"Split {total} activities into {len(chunks)} chunks "
            f"({len(chunks)} workers)"
        )
        self.update_progress(22)

        # run Bulldozer
        bzz.run(job_dirs=job_dirs, job_function=_strava_blob_job)

        # detect and report failed jobs
        failed_jobs = []
        for job_dir in job_dirs:
            error_file = job_dir / "output" / "error.json"
            if error_file.exists():
                with open(error_file) as fh:
                    err = json.load(fh)
                failed_jobs.append(err["job_key"])
                self.log(
                    f"ERROR: Bulldozer job {err['job_key']} failed:\n{err['traceback']}"
                )
        if failed_jobs:
            raise RuntimeError(
                f"Bulldozer jobs {failed_jobs} failed - see log for details"
            )

        self.log("All photo and recordings Bulldozer jobs DONE - merging blobstores...")
        self.update_progress(50)

        # PHASE 4: merge sandbox blobstores into main blobstore
        main_blobs_dir = persistence_root / "data" / user_id / "blobs"
        sandbox_blobs_dirs = [_sandbox_blobs_dir(d, user_id) for d in job_dirs]
        merged = blob_svc_module.ActivityBlobService.merge_sandbox_blobstores(
            sandbox_blobs_dirs=sandbox_blobs_dirs,
            main_blobs_dir=main_blobs_dir,
        )
        self.log(f"Merged {merged} blob directories from sandboxes into main store")
        self.update_progress(55)
        self.check_cancellation()

        # PHASE 5: collect activities + summaries, apply, batch update
        self.log("Collecting activities from sandbox outputs...")

        all_activities: list[entities.ActivityEntity] = []
        all_summaries: dict[str, dict] = {}
        photos_uploaded = 0
        photos_failed = 0
        recordings_imported = 0
        recordings_skipped = 0
        recordings_failed = 0

        for job_dir in job_dirs:
            output_file = job_dir / "output" / "payload.json"
            if not output_file.exists():
                continue
            with open(output_file) as fh:
                chunk_data = json.load(fh)
            for d in chunk_data.get("activities", []):
                # strip transient attrs before reconstructing entity
                d.pop("_photo_paths", None)
                d.pop("_recording_path", None)
                d.pop("transient_fields", None)
                all_activities.append(entities.ActivityEntity(**d))
            for key, summary in chunk_data.get("summaries", {}).items():
                all_summaries[key] = summary

        if len(all_activities) != total:
            self.log(
                f"WARNING: collected {len(all_activities)} activities, expected {total}"
            )

        self.update_progress(60)

        # apply summaries and count statistics
        photos_before = 0
        recordings_before = 0
        for activity in activities:
            orig_photos = getattr(activity, "_photo_paths", []) or []
            photos_before += len(orig_photos)
            if getattr(activity, "_recording_path", ""):
                recordings_before += 1

        for activity in all_activities:
            summary_dict = all_summaries.get(activity.key)
            if summary_dict:
                _apply_summary_dict(activity, summary_dict)

        photos_after = sum(len(a.photo_blob_keys or []) for a in all_activities)
        recordings_after = sum(1 for a in all_activities if a.recorded_blob_keys)
        photos_uploaded = photos_after
        photos_failed = max(0, photos_before - photos_after)
        recordings_imported = recordings_after
        recordings_failed = max(0, recordings_before - recordings_after)

        self.update_progress(70)

        # batch-update all activities with new blob keys + summaries
        self.log(f"Applying updates to {len(all_activities)} activities in dataset...")
        self._dataset.update_activities(
            user_id=user_id,
            dataset_name=dataset_name,
            activities=all_activities,
        )
        self.update_progress(80)
        self.check_cancellation()

        # PHASE 6: Bulldozer-parallelized GPX map data precomputation
        self.log("Precomputing GPX map data for recordings...")

        # collect recording blob references
        gpx_entries: list[dict] = []
        for activity in all_activities:
            if not activity.recorded_blob_keys:
                continue
            for entry in activity.recorded_blob_keys:
                blob_uuid = entities.recording_blob_uuid(entry)
                ext = entry.rsplit(".", 1)[-1] if "." in entry else ".gpx"
                gpx_entries.append(
                    {
                        "activity_key": activity.key,
                        "blob_uuid": blob_uuid,
                        "extension": f".{ext}",
                    }
                )

        if gpx_entries:
            gpx_workers = max(1, (os.cpu_count() or 1) // 2)
            gpx_chunks = _split_evenly(gpx_entries, min(gpx_workers, len(gpx_entries)))

            gpx_bzz = bulldozer.SubtaskBulldozer(
                usr_task_dir=usr_task_dir,
                subtask_key="gpx-map",
                logger=self.logger,
            )
            gpx_job_dirs = gpx_bzz.make_sandbox()
            gpx_job_dirs = gpx_job_dirs[: len(gpx_chunks)]

            user_data_dir = str(self._config.user_data_dir)
            for i, chunk in enumerate(gpx_chunks):
                input_file = gpx_job_dirs[i] / "input" / "payload.json"
                with open(input_file, "w") as fh:
                    json.dump(
                        {
                            "user_id": user_id,
                            "user_data_dir": user_data_dir,
                            "entries": chunk,
                        },
                        fh,
                    )

            self.log(
                f"Split {len(gpx_entries)} recording blobs into "
                f"{len(gpx_chunks)} GPX-map chunks ({len(gpx_chunks)} workers)"
            )
            self.update_progress(85)

            gpx_bzz.run(job_dirs=gpx_job_dirs, job_function=_strava_gpx_map_job)
            self.update_progress(86)

            # detect failed GPX jobs
            gpx_failed = []
            for job_dir in gpx_job_dirs:
                error_file = job_dir / "output" / "error.json"
                if error_file.exists():
                    with open(error_file) as fh:
                        err = json.load(fh)
                    gpx_failed.append(err["job_key"])
                    self.log(
                        f"ERROR: GPX-map job {err['job_key']} failed:\n"
                        f"{err['traceback']}"
                    )
            if gpx_failed:
                self.log(
                    f"WARNING: {len(gpx_failed)} GPX-map jobs failed — "
                    f"some map data may be missing"
                )

            # collect results and update blob metadata
            self.update_progress(90)
            self.log(
                f"Collecting GPX map data from {len(gpx_job_dirs)} job outputs and "
                f"updating blob metadata..."
            )
            gpx_map_count = 0
            gpx_skip_count = 0
            for job_dir in gpx_job_dirs:
                output_file = job_dir / "output" / "payload.json"
                if not output_file.exists():
                    continue
                with open(output_file) as fh:
                    chunk_result = json.load(fh)
                for blob_uuid, result in chunk_result.get("results", {}).items():
                    if result.get("skipped"):
                        gpx_skip_count += 1
                        continue
                    try:
                        cur_meta = blob_svc._store.get_blob_metadata(user_id, blob_uuid)
                        bbox = result.get("summary_bbox")
                        if bbox and len(bbox) == 4:
                            bbox = tuple(bbox)
                        else:
                            bbox = None
                        blob_svc._store.update_blob_metadata(
                            user_id=user_id,
                            blob_key=blob_uuid,
                            name=cur_meta.name,
                            description=cur_meta.description,
                            keywords=cur_meta.keywords,
                            track_count=result.get("track_count"),
                            track_point_count=result.get("track_point_count"),
                            summary_polyline=result.get("summary_polyline"),
                            summary_bbox=bbox,
                            full_polyline=result.get("full_polyline"),
                            elevation_profile=result.get("elevation_profile"),
                        )
                        gpx_map_count += 1
                    except Exception as exc:
                        self.log(
                            f"  WARNING: GPX metadata update failed for "
                            f"{blob_uuid}: {exc}"
                        )
            self.log(
                f"Precomputed GPX map data for {gpx_map_count} recordings "
                f"({gpx_skip_count} already had it)"
            )
        else:
            self.log("No recording blobs to precompute GPX map data for")

        self.update_progress(95)

        self.update_progress(100)

        self.log(
            f"Strava archive import complete: {total} activities imported, "
            f"{photos_uploaded} photos uploaded, {photos_failed} photos failed, "
            f"{recordings_imported} recordings imported, "
            f"{recordings_skipped} recordings skipped, "
            f"{recordings_failed} recordings failed"
        )

    def _apply_on_conflict(
        self,
        activities: list,
        user_id: str,
        dataset_name: str,
        on_conflict: str,
    ) -> tuple[list, dict]:
        """Apply import on_conflict strategy by (src, src_key)."""
        mode = on_conflict.lower().strip()
        if mode not in ("skip", "override", "new_key"):
            mode = "new_key"
        if mode == "new_key":
            return activities, {"skipped": 0, "overridden": 0, "overridden_keys": set()}

        existing = {}
        for current in self._dataset.list_activities(
            user_id=user_id,
            dataset_name=dataset_name,
        ):
            src = str(getattr(current, "src", "") or "")
            src_key = str(getattr(current, "src_key", "") or "")
            if src and src_key:
                existing[(src, src_key)] = current.key

        skipped = 0
        overridden = 0
        overridden_keys: set[str] = set()
        resolved = []
        for activity in activities:
            src = str(getattr(activity, "src", "") or "")
            src_key = str(getattr(activity, "src_key", "") or "")
            current_key = existing.get((src, src_key))
            if current_key is None:
                resolved.append(activity)
                continue
            if mode == "skip":
                skipped += 1
                continue
            activity.key = current_key
            overridden += 1
            overridden_keys.add(current_key)
            resolved.append(activity)

        return resolved, {
            "skipped": skipped,
            "overridden": overridden,
            "overridden_keys": overridden_keys,
        }


def _parse_iso_date_param(value, param_name: str) -> datetime.date | None:
    """Parse optional YYYY-MM-DD date task parameter."""
    text = str(value or "").strip()
    if not text:
        return None
    try:
        return datetime.datetime.strptime(text, "%Y-%m-%d").date()
    except ValueError as exc:
        raise RuntimeError(
            f"Invalid {param_name} value '{text}'. Expected YYYY-MM-DD."
        ) from exc


def _activity_date(activity) -> datetime.date | None:
    """Extract activity date for range filtering."""
    year = int(getattr(activity, "when_year", 0) or 0)
    month = int(getattr(activity, "when_month", 0) or 0)
    day = int(getattr(activity, "when_day", 0) or 0)
    if year <= 0 or month <= 0 or day <= 0:
        return None
    try:
        return datetime.date(year=year, month=month, day=day)
    except ValueError:
        return None


def _filter_activities_by_date_range(
    activities: list,
    import_from_date: datetime.date | None,
    import_to_date: datetime.date | None,
) -> list:
    """Return activities filtered by optional inclusive date bounds."""
    if import_from_date is None and import_to_date is None:
        return activities
    filtered: list = []
    for activity in activities:
        activity_date = _activity_date(activity)
        if activity_date is None:
            filtered.append(activity)
            continue
        if import_from_date and activity_date < import_from_date:
            continue
        if import_to_date and activity_date > import_to_date:
            continue
        filtered.append(activity)
    return filtered


tasks.tasks_registry.register_task(StravaArchiveImportTask)
