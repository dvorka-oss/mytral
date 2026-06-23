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

"""Async task: import activities and FIT recordings from a Garmin Connect
data export archive using bulldozer-parallelised blob processing.
"""

import dataclasses
import datetime
import hashlib
import io
import json
import os
import pathlib
import shutil
import traceback
import uuid
import zipfile

import fitparse

from mytral import commons
from mytral import config as mytral_config
from mytral import tasks
from mytral.backends import entities as be_entities
from mytral.blobstore import activity_service as blob_svc_module
from mytral.blobstore.filesystem import FilesystemBlobStore
from mytral.blobstore.models import BlobKind
from mytral.integrations import garmin_user_archive
from mytral.integrations import icommons
from mytral.recordings import parquet_converter
from mytral.tasks import bulldozer
from mytral.tasks.bulldozer._sandbox_utils import _make_blob_metadata
from mytral.tasks.bulldozer._sandbox_utils import _sandbox_blobs_dir
from mytral.tasks.bulldozer._sandbox_utils import _split_evenly

_ACTIVITY_FIELDS = {f.name for f in dataclasses.fields(be_entities.ActivityEntity)}

_UPLOADS_SUBDIR = pathlib.Path("DI_CONNECT") / "DI-Connect-Uploaded-Files"
_FIT_EXPORT_SUBDIR = "garmin_fit_export"


def _parse_fit_export_filename(name: str) -> tuple[str, str, str]:
    """Parse a Garmin FIT export filename → (date_str, activity_id, sport_str).

    Expected format: YYYY-MM-DD_ACTIVITYID_SPORT[_...].fit
    Returns ("", "", "") when the name doesn't match this pattern.
    """
    stem = pathlib.Path(name).stem
    parts = stem.split("_", 2)
    if len(parts) == 3 and parts[1].isdigit():
        return parts[0], parts[1], parts[2]
    return "", "", ""


def _fitparse_extract_when(fit_data: bytes) -> datetime.datetime | None:
    """Extract activity start time from a FIT file using fitparse.

    Uses fitparse (which handles Garmin's Latin-1 string encoding) instead
    of fit_tool, which fails on Garmin Connect archive FIT files.

    Returns UTC-aware datetime, or None when parsing fails or no session found.
    """
    try:
        ff = fitparse.FitFile(io.BytesIO(fit_data), check_crc=False)
        for session in ff.get_messages("session"):
            start = session.get_value("start_time")
            if start is None:
                continue
            if isinstance(start, datetime.datetime):
                if start.tzinfo is None:
                    return start.replace(tzinfo=datetime.timezone.utc)
                return start
    except Exception:
        pass
    return None


def _fitparse_extract_sport(fit_data: bytes) -> str:
    """Extract sport/activity type string from a FIT file using fitparse."""
    try:
        ff = fitparse.FitFile(io.BytesIO(fit_data), check_crc=False)
        for session in ff.get_messages("session"):
            sport = session.get_value("sport")
            if sport is not None:
                return str(sport).lower()
    except Exception:
        pass
    return ""


def _fitparse_extract_summary(fit_data: bytes) -> dict:
    """Extract full activity summary from a FIT file using fitparse.

    fitparse handles Garmin archive FIT files with Latin-1 encoded strings,
    unlike fit_tool which fails with a UTF-8 decode error on such files.

    Speed values from fitparse are in m/s; converted to km/h here.
    Returns a dict whose keys mirror RecordingSummary field names so callers
    can stay readable when switching from fit_extractor.
    """
    result: dict = {
        "when": None,
        "activity_type_key": None,
        "name_hint": None,
        "hours": None,
        "minutes": None,
        "seconds": None,
        "distance": None,
        "kcal": None,
        "avg_hr": None,
        "max_hr": None,
        "avg_cadence": None,
        "max_cadence": None,
        "avg_speed": None,
        "max_speed": None,
        "avg_watts": None,
        "max_watts": None,
        "elevation_gain": None,
    }
    try:
        ff = fitparse.FitFile(io.BytesIO(fit_data), check_crc=False)
        for session in ff.get_messages("session"):
            start = session.get_value("start_time")
            if isinstance(start, datetime.datetime):
                result["when"] = (
                    start.replace(tzinfo=datetime.timezone.utc)
                    if start.tzinfo is None
                    else start
                )

            sport = session.get_value("sport")
            if sport is not None:
                sport_str = str(sport).lower()
                result["activity_type_key"] = icommons.FIT_INT_SPORT_TO_MYTRAL_AT.get(
                    sport_str, commons.AT_WORKOUT
                )

            elapsed = session.get_value("total_elapsed_time")
            if elapsed is not None:
                total_s = int(elapsed)
                result["hours"] = total_s // 3600
                result["minutes"] = (total_s % 3600) // 60
                result["seconds"] = total_s % 60

            dist = session.get_value("total_distance")
            if dist is not None:
                result["distance"] = int(dist)

            kcal = session.get_value("total_calories")
            if kcal is not None:
                result["kcal"] = int(kcal)

            result["avg_hr"] = session.get_value("avg_heart_rate")
            result["max_hr"] = session.get_value("max_heart_rate")
            result["avg_cadence"] = session.get_value("avg_cadence")
            result["max_cadence"] = session.get_value("max_cadence")

            avg_speed = session.get_value("avg_speed")
            if avg_speed is not None:
                result["avg_speed"] = round(float(avg_speed) * 3.6, 2)

            max_speed = session.get_value("max_speed")
            if max_speed is not None:
                result["max_speed"] = round(float(max_speed) * 3.6, 2)

            avg_power = session.get_value("avg_power")
            if avg_power is not None:
                result["avg_watts"] = int(avg_power)

            max_power = session.get_value("max_power")
            if max_power is not None:
                result["max_watts"] = int(max_power)

            ascent = session.get_value("total_ascent")
            if ascent is not None:
                result["elevation_gain"] = int(ascent)

            break  # only first session
    except Exception:
        pass
    return result


# ---------------------------------------------------------------------------
# Bulldozer worker
# ---------------------------------------------------------------------------


def _garmin_blob_job(job_key: int, job_dir: pathlib.Path) -> None:
    """Bulldozer job: upload FIT blobs and convert to Parquet.

    Reads ``job_dir/input/payload.json``.  On failure writes
    ``job_dir/output/error.json``.
    """
    try:
        _garmin_blob_job_impl(job_key, job_dir)
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


def _garmin_blob_job_impl(job_key: int, job_dir: pathlib.Path) -> None:
    """Implementation of :func:`_garmin_blob_job`."""
    input_file = job_dir / "input" / "payload.json"
    if not input_file.exists():
        return

    with open(input_file) as fh:
        payload = json.load(fh)

    items: list[dict] = payload.get("items", [])
    if not items:
        return

    user_id: str = payload.get("user_id", "")
    correlation_id: str = payload.get("correlation_id", "")
    import_recordings: bool = bool(payload.get("import_recordings", True))

    sandbox_config = mytral_config.MytralConfig(persistence_data_dir=job_dir / "work")
    sandbox_store = FilesystemBlobStore(
        base_dir=sandbox_config.user_data_dir,
        blobs_subdir="blobs",
    )

    now = datetime.datetime.now(datetime.timezone.utc).isoformat()
    activities: list[dict] = []

    for idx, item in enumerate(items):
        fit_path_str: str = item.get("fit_path", "")
        fit_path = pathlib.Path(fit_path_str)
        has_json_match: bool = bool(item.get("has_json_match", False))

        try:
            fit_data = fit_path.read_bytes()
        except OSError:
            continue

        summary = _fitparse_extract_summary(fit_data)

        temp_key = f"temp-{job_key}-{idx}"
        d: dict = {"key": temp_key}

        # name: prefer JSON metadata over FIT hint
        if has_json_match and item.get("name"):
            d["name"] = item["name"]
        elif summary["name_hint"]:
            d["name"] = summary["name_hint"]
        else:
            d["name"] = fit_path.stem

        # activity type: FIT summary is authoritative; JSON provides fallback
        at_key = summary["activity_type_key"]
        if at_key and at_key != commons.AT_WORKOUT:
            d["activity_type_key"] = at_key
        else:
            raw_type = (item.get("activity_type") or "").lower()
            d["activity_type_key"] = icommons.FIT_INT_SPORT_TO_MYTRAL_AT.get(
                raw_type, commons.AT_WORKOUT
            )

        # location from JSON metadata
        location = item.get("location", "")
        if location:
            d["where"] = location

        # source tracking
        d["src"] = garmin_user_archive.SRC_GARMIN_CONNECT
        if item.get("activity_id") is not None:
            # activity_id available from JSON match or parsed filename
            d["src_key"] = str(item["activity_id"])
        else:
            d["src_key"] = fit_path.name
        d["src_descriptor"] = f"garmin-archive-{correlation_id}"

        # datetime from FIT session
        fit_when = summary["when"]
        if fit_when:
            d["when"] = fit_when.strftime("%Y-%m-%d %H:%M")
            d["when_year"] = fit_when.year
            d["when_month"] = fit_when.month
            d["when_day"] = fit_when.day
            d["when_hour"] = fit_when.hour
            d["when_minute"] = fit_when.minute
            d["when_second"] = fit_when.second

        # duration
        if summary["hours"] is not None:
            d["hours"] = summary["hours"]
        if summary["minutes"] is not None:
            d["minutes"] = summary["minutes"]
        if summary["seconds"] is not None:
            d["seconds"] = summary["seconds"]

        # metrics
        if summary["distance"]:
            d["distance"] = summary["distance"]
        if summary["kcal"]:
            d["kcal"] = summary["kcal"]
        if summary["avg_hr"]:
            d["avg_hr"] = summary["avg_hr"]
        if summary["max_hr"]:
            d["max_hr"] = summary["max_hr"]
        if summary["avg_cadence"]:
            d["avg_cadence"] = summary["avg_cadence"]
        if summary["max_cadence"]:
            d["max_cadence"] = summary["max_cadence"]
        if summary["avg_speed"]:
            d["avg_speed"] = summary["avg_speed"]
        if summary["max_speed"]:
            d["max_speed"] = summary["max_speed"]
        if summary["avg_watts"]:
            d["avg_watts"] = summary["avg_watts"]
        if summary["max_watts"]:
            d["max_watts"] = summary["max_watts"]
        if summary["elevation_gain"]:
            d["elevation_gain"] = summary["elevation_gain"]

        if import_recordings:
            sha = hashlib.sha256(fit_data).hexdigest()
            rec_meta = _make_blob_metadata(
                user_id=user_id,
                activity_key=temp_key,
                kind=BlobKind.ACTIVITY_RECORDING.value,
                file_name="data.fit",
                original_file_name=fit_path.name,
                extension=".fit",
                size_bytes=len(fit_data),
                sha256=sha,
                name="FIT recording",
                description="Imported from Garmin Connect archive",
                keywords=["fit", "garmin-archive"],
                created_at=now,
            )
            sandbox_store.create_blob(rec_meta, io.BytesIO(fit_data))
            d["recorded_blob_keys"] = [f"{rec_meta.blob_key}.fit"]

            try:
                parquet_bytes = parquet_converter.fit_to_parquet(fit_data)
            except Exception:
                d["_fit_path"] = fit_path_str
                activities.append(d)
                continue

            pq_sha = hashlib.sha256(parquet_bytes).hexdigest()
            pq_meta = _make_blob_metadata(
                user_id=user_id,
                activity_key=temp_key,
                kind=BlobKind.ACTIVITY_PARQUET.value,
                file_name="data.parquet",
                original_file_name="data.parquet",
                extension=".parquet",
                size_bytes=len(parquet_bytes),
                sha256=pq_sha,
                created_at=now,
            )
            sandbox_store.create_blob(pq_meta, io.BytesIO(parquet_bytes))
            d["recorded_parquet_keys"] = {rec_meta.blob_key: pq_meta.blob_key}

        d["_fit_path"] = fit_path_str
        activities.append(d)

    output_file = job_dir / "output" / "payload.json"
    output_file.parent.mkdir(parents=True, exist_ok=True)
    with open(output_file, "w") as fh:
        json.dump({"activities": activities}, fh)


# ---------------------------------------------------------------------------
# Date filter helpers (same logic as in strava_archive_import)
# ---------------------------------------------------------------------------


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


# ---------------------------------------------------------------------------
# Main task
# ---------------------------------------------------------------------------


class GarminArchiveImportTask(tasks.TaskBase):
    """Import activities and FIT recordings from a Garmin Connect archive.

    Parameters are provided via ``task_entity.parameters``:

    - ``user_id`` (str): owning user identifier
    - ``dataset_name`` (str): target dataset name
    - ``DATA_DIR_KEY`` (str): absolute path to extracted Garmin archive directory
    - ``on_conflict`` (str): conflict resolution strategy (skip, override, new_key)
    - ``IMPORT_RECORDINGS_KEY`` (bool): whether to import FIT recordings
    - ``IMPORT_FROM_DATE_KEY`` (str, optional): YYYY-MM-DD lower bound
    - ``IMPORT_TO_DATE_KEY`` (str, optional): YYYY-MM-DD upper bound
    - ``correlation_id`` (str): import run identifier
    """

    TASK_TYPE = "garmin_archive_import"
    TASK_DISPLAY_NAME = "Garmin Connect Archive Import"

    DATA_DIR_KEY = garmin_user_archive.USE_TYPE_GARMIN_ARCHIVE_DIR
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
        """Execute Garmin archive import task.

        Raises
        ------
        RuntimeError
            On unrecoverable failures.
        """
        params = self.task_entity.parameters
        user_id: str = params["user_id"]
        dataset_name: str = params["dataset_name"]
        data_dir: str = params[self.DATA_DIR_KEY]
        on_conflict: str = params.get("on_conflict", "skip")
        import_recordings: bool = bool(params.get(self.IMPORT_RECORDINGS_KEY, True))
        correlation_id: str = params.get("correlation_id", str(uuid.uuid4()))

        import_from_date = _parse_iso_date_param(
            params.get(self.IMPORT_FROM_DATE_KEY, ""), "import_from_date"
        )
        import_to_date = _parse_iso_date_param(
            params.get(self.IMPORT_TO_DATE_KEY, ""), "import_to_date"
        )

        self.log(f"Garmin archive import: user={user_id}, path={data_dir}")
        self.update_progress(2)
        self.check_cancellation()

        data_path = pathlib.Path(data_dir)
        if not data_path.exists():
            raise RuntimeError(f"Path does not exist: {data_dir}")

        persistence_root = self._config.persistence_data_dir
        usr_task_dir = (
            persistence_root
            / mytral_config.MytralPersistenceFsConfig.DIR_DATA
            / user_id
            / mytral_config.MytralPersistenceFsConfig.DIR_TASKS
            / f"task-{self.task_entity.key}"
        )

        # ------------------------------------------------------------------
        # Phase 1: resolve input, detect format, collect FIT paths + metadata
        # ------------------------------------------------------------------

        # Step 1a: if a ZIP file was given, extract it to a temp directory
        if data_path.is_file() and data_path.suffix.lower() == ".zip":
            self.log(f"Extracting ZIP: {data_path.name} ...")
            extracted_dir = usr_task_dir / "extracted"
            extracted_dir.mkdir(parents=True, exist_ok=True)
            with zipfile.ZipFile(data_path, "r") as zf:
                zf.extractall(extracted_dir)
            archive_dir = extracted_dir
            self.log("Extracted to temporary directory")
        else:
            archive_dir = data_path

        self.update_progress(5)
        self.check_cancellation()

        # Step 1b: detect archive format
        fit_export_dir = archive_dir / _FIT_EXPORT_SUBDIR
        uploads_dir = archive_dir / _UPLOADS_SUBDIR

        items: list[dict] = []
        matched_count = 0
        unmatched_count = 0
        filtered_count = 0

        if fit_export_dir.is_dir():
            # ----------------------------------------------------------
            # Format A: Garmin FIT export ZIP
            #   garmin_fit_export/YYYY-MM-DD_ACTIVITYID_SPORT.fit
            # No JSON metadata; activity ID and sport come from filename.
            # ----------------------------------------------------------
            self.log("Detected Garmin FIT export format (garmin_fit_export/)")
            fit_paths = sorted(fit_export_dir.glob("*.fit"))
            self.log(
                f"Found {len(fit_paths)} FIT files"
                " — building import list from filenames ..."
            )
            self.update_progress(8)
            self.check_cancellation()

            # No FIT file I/O here: date, activity ID, and sport are encoded in
            # the filename as YYYY-MM-DD_ACTIVITYID_SPORT.fit.  All FIT parsing
            # (timestamps, metrics, blob upload) is done in parallel by Phase 2.
            for fit_path in fit_paths:
                date_str, activity_id, sport_str = _parse_fit_export_filename(
                    fit_path.name
                )
                if not date_str:
                    unmatched_count += 1
                    continue

                if import_from_date or import_to_date:
                    try:
                        activity_date = datetime.date.fromisoformat(date_str)
                    except ValueError:
                        unmatched_count += 1
                        continue
                    if import_from_date and activity_date < import_from_date:
                        filtered_count += 1
                        continue
                    if import_to_date and activity_date > import_to_date:
                        filtered_count += 1
                        continue

                has_id = bool(activity_id)
                if has_id:
                    matched_count += 1
                else:
                    unmatched_count += 1

                items.append(
                    {
                        "fit_path": str(fit_path),
                        "activity_id": activity_id if has_id else None,
                        "name": "",
                        "location": "",
                        "activity_type": sport_str,
                        "has_json_match": False,
                    }
                )

            self.log(
                f"Import list ready: {len(items)} activities "
                f"({matched_count} with activity ID, {unmatched_count} without, "
                f"{filtered_count} filtered by date range)"
            )

        elif uploads_dir.is_dir() or (archive_dir / "DI_CONNECT").is_dir():
            # ----------------------------------------------------------
            # Format B: Garmin Connect full data archive (extracted)
            #   DI_CONNECT/DI-Connect-Uploaded-Files/UploadedFiles_*_Part*.zip
            #   DI_CONNECT/DI-Connect-Fitness/*_summarizedActivities.json
            # ----------------------------------------------------------
            self.log("Detected Garmin Connect full archive format (DI_CONNECT/)")
            self.log("Extracting FIT files from nested ZIPs ...")

            zip_files = (
                sorted(uploads_dir.glob("UploadedFiles_*_Part*.zip"))
                if uploads_dir.is_dir()
                else []
            )
            if not zip_files:
                zip_files = (
                    sorted(uploads_dir.glob("*.zip")) if uploads_dir.is_dir() else []
                )

            temp_fits_dir = usr_task_dir / "temp_fits"
            temp_fits_dir.mkdir(parents=True, exist_ok=True)

            total_extracted = 0
            for zip_idx, zip_path in enumerate(zip_files):
                try:
                    with zipfile.ZipFile(zip_path, "r") as zf:
                        for member in zf.infolist():
                            if not member.filename.lower().endswith(".fit"):
                                continue
                            basename = pathlib.Path(member.filename).name
                            dest_name = f"{zip_idx:04d}_{basename}"
                            dest_path = temp_fits_dir / dest_name
                            dest_path.write_bytes(zf.read(member))
                            total_extracted += 1
                except Exception as exc:
                    self.log(f"WARNING: failed to extract {zip_path.name}: {exc}")

            self.log(
                f"Extracted {total_extracted} FIT files from {len(zip_files)} ZIP(s)"
            )
            self.update_progress(8)
            self.check_cancellation()

            fit_paths = sorted(temp_fits_dir.glob("*.fit"))
            if not fit_paths:
                self.log("No FIT files found in archive — nothing to import")
                self.update_progress(100)
                return

            self.log("Parsing Garmin Connect activity metadata from JSON ...")
            json_index = garmin_user_archive.parse_activities_index(archive_dir)
            self.log(f"JSON index: {len(json_index)} activities loaded")
            self.update_progress(12)
            self.check_cancellation()

            self.log(
                f"Scanning {len(fit_paths)} FIT files and matching to metadata ..."
            )
            for fit_path in fit_paths:
                try:
                    fit_data = fit_path.read_bytes()
                except OSError as exc:
                    self.log(f"WARNING: cannot read {fit_path.name}: {exc}")
                    continue

                fit_when = _fitparse_extract_when(fit_data)
                if fit_when is None:
                    filtered_count += 1
                    continue

                if import_from_date or import_to_date:
                    activity_date = fit_when.date()
                    if import_from_date and activity_date < import_from_date:
                        filtered_count += 1
                        continue
                    if import_to_date and activity_date > import_to_date:
                        filtered_count += 1
                        continue

                metadata = garmin_user_archive.find_fit_json_match(fit_when, json_index)
                has_match = metadata is not None
                if has_match:
                    matched_count += 1
                else:
                    unmatched_count += 1

                items.append(
                    {
                        "fit_path": str(fit_path),
                        "activity_id": metadata["activityId"] if has_match else None,
                        "name": metadata["name"] if has_match else "",
                        "location": metadata["locationName"] if has_match else "",
                        "activity_type": metadata["activityType"] if has_match else "",
                        "has_json_match": has_match,
                    }
                )

            self.log(
                f"FIT scan complete: {len(items)} to import "
                f"({matched_count} matched to JSON, {unmatched_count} unmatched, "
                f"{filtered_count} filtered)"
            )

        else:
            raise RuntimeError(
                f"Unrecognised Garmin archive format at {archive_dir}. "
                f"Expected '{_FIT_EXPORT_SUBDIR}/' (FIT export ZIP) or "
                f"'DI_CONNECT/' (full data archive)."
            )

        self.update_progress(18)
        self.check_cancellation()

        if not items:
            self.log("No activities to import after filtering")
            self.update_progress(100)
            return

        # validate file sizes
        max_size = self._config.blobstore_max_recording_size_bytes
        for item in items:
            p = pathlib.Path(item["fit_path"])
            if p.stat().st_size > max_size:
                raise RuntimeError(
                    f"FIT file {p.name} exceeds maximum allowed "
                    f"size ({max_size // (1024 * 1024)} MiB)"
                )

        # ------------------------------------------------------------------
        # Phase 2: bulldozer-parallel FIT → blob + parquet
        # ------------------------------------------------------------------

        workers = max(1, (os.cpu_count() or 1) // 2)
        total = len(items)
        actual_workers = min(workers, total)
        chunks = _split_evenly(items, actual_workers)
        per_worker = (total + actual_workers - 1) // actual_workers

        self.log(
            f"Phase 2: launching {actual_workers} parallel worker(s) "
            f"to process {total} FIT files (~{per_worker} files/worker) ..."
        )

        bzz = bulldozer.SubtaskBulldozer(
            usr_task_dir=usr_task_dir,
            logger=self.logger,
        )
        job_dirs = bzz.make_sandbox()
        job_dirs = job_dirs[: len(chunks)]

        for i, chunk in enumerate(chunks):
            input_file = job_dirs[i] / "input" / "payload.json"
            with open(input_file, "w") as fh:
                json.dump(
                    {
                        "user_id": user_id,
                        "correlation_id": correlation_id,
                        "import_recordings": import_recordings,
                        "items": chunk,
                    },
                    fh,
                )

        self.update_progress(22)
        self.check_cancellation()

        bzz.run(job_dirs=job_dirs, job_function=_garmin_blob_job)
        self.check_cancellation()

        failed_jobs = []
        for job_dir in job_dirs:
            error_file = job_dir / "output" / "error.json"
            if error_file.exists():
                with open(error_file) as fh:
                    err = json.load(fh)
                failed_jobs.append(err["job_key"])
                self.log(f"ERROR: job {err['job_key']} failed:\n{err['traceback']}")
        if failed_jobs:
            raise RuntimeError(
                f"Bulldozer jobs {failed_jobs} failed — see log for details"
            )

        self.log(f"Phase 2 complete — all {actual_workers} worker(s) done")
        self.update_progress(50)
        self.check_cancellation()

        # ------------------------------------------------------------------
        # Phase 3: conflict resolution, blob merge, persist activities
        # ------------------------------------------------------------------

        all_dicts: list[dict] = []
        for job_dir in job_dirs:
            output_file = job_dir / "output" / "payload.json"
            if not output_file.exists():
                continue
            with open(output_file) as fh:
                chunk_data = json.load(fh)
            all_dicts.extend(chunk_data.get("activities", []))

        if not all_dicts:
            self.log("No activities produced by bulldozer jobs")
            self.update_progress(100)
            return

        self.log(
            f"Collected {len(all_dicts)} activity dicts from {len(job_dirs)} job(s)"
        )
        self.update_progress(55)
        self.check_cancellation()

        blob_svc = blob_svc_module.ActivityBlobService(
            store=self._blobstore,
            dataset=self._dataset,
            config=self._config,
        )

        temp_to_final: dict[str, str] = {}
        skipped_temp_keys: list[str] = []
        new_entries: list[dict] = []
        override_entries: list[dict] = []
        skipped_count = 0
        failed_count = 0

        for d in all_dicts:
            temp_key = d["key"]
            src_key_label = d.get("src_key", "")

            try:
                entity_fields = {k: v for k, v in d.items() if k in _ACTIVITY_FIELDS}
                activity = be_entities.ActivityEntity(**entity_fields)

                filter_year = activity.when_year if activity.when_year else 0
                existing_key = self._find_activity_conflict(
                    user_id=user_id,
                    dataset_name=dataset_name,
                    activity=activity,
                    filter_year=filter_year,
                )

                if existing_key:
                    self.log(
                        f"Conflict for {src_key_label}: existing={existing_key}, "
                        f"strategy={on_conflict}"
                    )
                    if on_conflict == "skip":
                        skipped_temp_keys.append(temp_key)
                        skipped_count += 1
                        continue
                    elif on_conflict == "override":
                        temp_to_final[temp_key] = existing_key
                        override_entries.append(d)
                    else:
                        final_key = self._dataset.create_key()
                        temp_to_final[temp_key] = final_key
                        new_entries.append(d)
                else:
                    final_key = self._dataset.create_key()
                    temp_to_final[temp_key] = final_key
                    new_entries.append(d)

            except Exception as exc:
                failed_count += 1
                self.log(f"Failed to resolve conflict for {src_key_label}: {exc}")
                skipped_temp_keys.append(temp_key)

        self.update_progress(65)
        self.check_cancellation()

        processed_count = len(new_entries) + len(override_entries)
        if processed_count == 0:
            self.update_progress(100)
            self.log(
                f"Garmin archive import complete: 0 imported, "
                f"{skipped_count} skipped, {failed_count} failed"
            )
            return

        self.log(
            f"Conflict resolution: {len(new_entries)} new, "
            f"{len(override_entries)} overridden, "
            f"{skipped_count} skipped, {failed_count} failed"
        )

        # clear existing blobs for overridden activities
        for d in override_entries:
            final_key = temp_to_final[d["key"]]
            try:
                blob_svc.delete_all_activity_blobs(
                    user_id=user_id,
                    activity_key=final_key,
                )
            except Exception as exc:
                self.log(
                    f"WARNING: failed to clear blobs for overridden "
                    f"activity {final_key}: {exc}"
                )

        self.update_progress(70)
        self.check_cancellation()

        # rename sandbox dirs temp_key → final_key
        for job_dir in job_dirs:
            sandbox_activities = _sandbox_blobs_dir(job_dir, user_id) / "activities"
            if not sandbox_activities.is_dir():
                continue
            for temp_key, final_key in temp_to_final.items():
                temp_dir = sandbox_activities / temp_key
                final_dir = sandbox_activities / final_key
                if temp_dir.is_dir() and not final_dir.exists():
                    temp_dir.rename(final_dir)

        # delete sandbox dirs for skipped activities
        for job_dir in job_dirs:
            sandbox_activities = _sandbox_blobs_dir(job_dir, user_id) / "activities"
            if not sandbox_activities.is_dir():
                continue
            for temp_key in skipped_temp_keys:
                temp_dir = sandbox_activities / temp_key
                if temp_dir.is_dir():
                    shutil.rmtree(str(temp_dir))

        self.update_progress(75)
        self.check_cancellation()

        # merge sandbox blobstores into main blobstore
        main_blobs_dir = persistence_root / "data" / user_id / "blobs"
        sandbox_blobs_dirs = [_sandbox_blobs_dir(d, user_id) for d in job_dirs]
        merged = blob_svc_module.ActivityBlobService.merge_sandbox_blobstores(
            sandbox_blobs_dirs=sandbox_blobs_dirs,
            main_blobs_dir=main_blobs_dir,
        )
        self.log(f"Merged {merged} blob directories from sandboxes into main store")
        self.update_progress(80)
        self.check_cancellation()

        # build final ActivityEntity lists
        new_entity_list: list[be_entities.ActivityEntity] = []
        override_entity_list: list[be_entities.ActivityEntity] = []

        for d in new_entries:
            final_key = temp_to_final[d["key"]]
            d["key"] = final_key
            d.pop("_fit_path", None)
            entity_fields = {k: v for k, v in d.items() if k in _ACTIVITY_FIELDS}
            new_entity_list.append(be_entities.ActivityEntity(**entity_fields))

        for d in override_entries:
            final_key = temp_to_final[d["key"]]
            d["key"] = final_key
            d.pop("_fit_path", None)
            entity_fields = {k: v for k, v in d.items() if k in _ACTIVITY_FIELDS}
            override_entity_list.append(be_entities.ActivityEntity(**entity_fields))

        if new_entity_list:
            self._dataset.create_activities(
                user_id=user_id,
                dataset_name=dataset_name,
                entity_list=new_entity_list,
            )
            self.log(f"Created {len(new_entity_list)} new activities")

        if override_entity_list:
            self._dataset.update_activities(
                user_id=user_id,
                dataset_name=dataset_name,
                activities=override_entity_list,
            )
            self.log(f"Updated {len(override_entity_list)} overridden activities")

        self.update_progress(95)
        self.check_cancellation()

        self.update_progress(100)
        self.log(
            f"Garmin archive import complete: {processed_count} imported, "
            f"{skipped_count} skipped, {failed_count} failed"
        )

    def _find_activity_conflict(
        self,
        user_id: str,
        dataset_name: str,
        activity: be_entities.ActivityEntity,
        filter_year: int = 0,
    ) -> str | None:
        """Return existing activity key when ``(src, src_key)`` matches, else None."""
        if activity.src_key:
            year_activities = self._dataset.list_activities(
                user_id=user_id,
                dataset_name=dataset_name,
                filter_year=filter_year,
            )
            for existing in year_activities:
                if (
                    existing.src == activity.src
                    and existing.src_key == activity.src_key
                ):
                    return existing.key
        return None


tasks.tasks_registry.register_task(GarminArchiveImportTask)
