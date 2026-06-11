# MyTraL: my trailing log
#
# Copyright (C) 2015-2026 Martin Dvorak <martin.dvorak@mindforger.com>
#
# This program is free software: you can redistribute it and/or modify
# it under the terms of the GNU Affero General Public License as published by
# the Free Software Foundation, either version 3 of the License, or
# (at your option) any later version.
# This program is distributed in the hope that it will be useful,
# but WITHOUT ANY WARRANTY; without even the implied warranty of
# MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the
# GNU Affero General Public License for more details.
#
# You should have received a copy of the GNU Affero General Public License
# along with this program. If not, see <http://www.gnu.org/licenses/>.
"""Async task: import multiple FIT files from a directory."""

import io
import json
import os
import pathlib
import traceback
import uuid

from mytral import app_logger
from mytral import app_user_ds as ds
from mytral import config as mytral_config
from mytral import tasks
from mytral.backends import entities as be_entities
from mytral.blobstore import activity_service as blob_svc_module
from mytral.blobstore.filesystem import FilesystemBlobStore
from mytral.recordings import fit_extractor
from mytral.recordings import parquet_converter
from mytral.tasks import bulldozer


def _split_evenly(items: list, num_chunks: int) -> list[list]:
    """Distribute items round-robin across *num_chunks* buckets."""
    if not items or num_chunks <= 1:
        return [items]
    chunks: list[list] = [[] for _ in range(num_chunks)]
    for i, item in enumerate(items):
        chunks[i % num_chunks].append(item)
    return [c for c in chunks if c]


def _sandbox_blobs_dir(job_dir: pathlib.Path, user_id: str) -> pathlib.Path:
    """Return the sandbox blobstore root directory for a given job."""
    return job_dir / "work" / "data" / user_id / "blobs"


def _fit_directory_blob_job(job_key: int, job_dir: pathlib.Path) -> None:
    """Bulldozer job: process FIT files in a sandbox.

    Reads ``job_dir/input/payload.json`` and for each activity reads the FIT
    file from its original path, uploads the recording blob to the sandbox
    blobstore, generates Parquet and map data.

    On failure writes ``job_dir/output/error.json``.
    """
    try:
        _fit_directory_blob_job_impl(job_key, job_dir)
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


def _fit_directory_blob_job_impl(job_key: int, job_dir: pathlib.Path) -> None:
    """Implementation of :func:`_fit_directory_blob_job`."""
    input_file = job_dir / "input" / "payload.json"
    if not input_file.exists():
        return

    with open(input_file) as fh:
        payload = json.load(fh)

    activities_data = payload.get("activities", [])
    if not activities_data:
        return

    user_id = payload.get("user_id", "")
    max_file_size = payload.get("max_file_size", 0)

    # create isolated blobstore inside the sandbox
    sandbox_config = mytral_config.MytralConfig(persistence_data_dir=job_dir / "work")
    sandbox_store = FilesystemBlobStore(
        base_dir=sandbox_config.user_data_dir,
        blobs_subdir="blobs",
    )
    blob_svc = blob_svc_module.ActivityBlobService(
        store=sandbox_store,
        dataset=None,  # not needed — we use skip_persist with activity param
        config=sandbox_config,
    )

    for d in activities_data:
        # pop transient keys before reconstructing ActivityEntity
        fit_path_str = d.pop("_fit_path", "")
        if not fit_path_str:
            continue

        fit_path = pathlib.Path(fit_path_str)
        if not fit_path.is_file():
            continue

        # validate file size
        file_size = fit_path.stat().st_size
        if max_file_size and file_size > max_file_size:
            continue

        # reconstruct activity entity for the upload methods
        activity = be_entities.ActivityEntity(**d)

        # read FIT file bytes
        try:
            fit_data = fit_path.read_bytes()
        except OSError:
            continue

        # upload recording blob to sandbox (activity is mutated in-memory)
        try:
            meta = blob_svc.upload_recording(
                user_id=user_id,
                activity_key=activity.key,
                uploaded_file=io.BytesIO(fit_data),
                original_filename=fit_path.name,
                content_type="application/octet-stream",
                activity=activity,
                skip_persist=True,
            )
        except Exception:
            continue

        # convert to parquet
        try:
            parquet_bytes = parquet_converter.fit_to_parquet(fit_data)
            blob_svc.save_parquet(
                user_id=user_id,
                activity_key=activity.key,
                source_blob_key=meta.blob_key,
                parquet_data=parquet_bytes,
                activity=activity,
                skip_persist=True,
            )
        except Exception:
            pass

        # serialize updated activity back to dict (with blob keys now filled in)
        d.update(activity.to_dict())

    # write processed activities to output
    output_file = job_dir / "output" / "payload.json"
    output_file.parent.mkdir(parents=True, exist_ok=True)
    with open(output_file, "w") as fh:
        json.dump({"activities": activities_data}, fh)


class FitDirectoryImportTask(tasks.TaskBase):
    """Import all FIT files from a directory, creating activities for each.

    Parameters are provided via ``task_entity.parameters``:

    - ``user_id`` (str): owning user identifier
    - ``dataset_name`` (str): target dataset name
    - ``data_dir`` (str): absolute path to directory containing .fit files
    - ``sport_type`` (str, optional): default sport type for imported activities
    - ``on_conflict`` (str): conflict resolution strategy (skip, override, new_key)
    - ``correlation_id`` (str): import run identifier
    """

    TASK_TYPE = "fit_directory_import"
    TASK_DISPLAY_NAME = "FIT Directory Import"

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
        """Execute FIT directory import task.

        Raises
        ------
        RuntimeError
            On unrecoverable failures.
        """
        params = self.task_entity.parameters
        user_id: str = params["user_id"]
        dataset_name: str = params["dataset_name"]
        data_dir: str = params["data_dir"]
        sport_type: str = params.get("sport_type", "")
        on_conflict: str = params.get("on_conflict", "skip")
        correlation_id: str = params.get("correlation_id", str(uuid.uuid4()))

        self.log(f"FIT directory import: user={user_id}, dir={data_dir}")
        self.update_progress(5)
        self.check_cancellation()

        # validate directory
        dir_path = pathlib.Path(data_dir)
        if not dir_path.is_dir():
            raise RuntimeError(f"Directory does not exist: {data_dir}")

        # find all .fit files (case-insensitive extension match)
        fit_files = sorted(
            path
            for path in dir_path.iterdir()
            if path.is_file() and path.suffix.lower() == ".fit"
        )
        self.log(f"Found {len(fit_files)} FIT files")
        for f in fit_files:
            self.log(f"  - {f.name}")

        if not fit_files:
            self.log("No FIT files found in directory")
            self.update_progress(100)
            return

        self.update_progress(10)
        self.check_cancellation()

        blob_svc = blob_svc_module.ActivityBlobService(
            store=self._blobstore,
            dataset=self._dataset,
            config=self._config,
        )

        # use bulldozer for large imports (> 10 files)
        if len(fit_files) > 10:
            self._execute_bulldozer(
                user_id=user_id,
                dataset_name=dataset_name,
                fit_files=fit_files,
                sport_type=sport_type,
                on_conflict=on_conflict,
                correlation_id=correlation_id,
                blob_svc=blob_svc,
            )
            return

        imported_count = 0
        skipped_count = 0
        failed_count = 0

        # process each FIT file sequentially
        for idx, fit_path in enumerate(fit_files):
            progress = 10 + int((idx / len(fit_files)) * 85)
            self.update_progress(progress)
            self.check_cancellation()

            try:
                result = self._process_single_fit(
                    user_id=user_id,
                    dataset_name=dataset_name,
                    fit_path=fit_path,
                    sport_type=sport_type,
                    on_conflict=on_conflict,
                    correlation_id=correlation_id,
                    blob_svc=blob_svc,
                )
                if result == "imported":
                    imported_count += 1
                elif result == "skipped":
                    skipped_count += 1
            except Exception as exc:
                failed_count += 1
                self.log(f"Failed to import {fit_path.name}: {exc}")
                app_logger.error(
                    "FIT directory import failed for file",
                    file=str(fit_path),
                    error=str(exc),
                )

        self.update_progress(100)
        self.log(
            f"FIT directory import complete: {imported_count} imported, "
            f"{skipped_count} skipped, {failed_count} failed"
        )

    def _execute_bulldozer(
        self,
        user_id: str,
        dataset_name: str,
        fit_files: list[pathlib.Path],
        sport_type: str,
        on_conflict: str,
        correlation_id: str,
        blob_svc: blob_svc_module.ActivityBlobService,
    ) -> None:
        """Execute FIT directory import using Bulldozer for parallel processing.

        Parameters
        ----------
        user_id : str
            Owning user identifier.
        dataset_name : str
            Target dataset name.
        fit_files : list[pathlib.Path]
            Sorted list of FIT file paths to import.
        sport_type : str
            Optional sport type override.
        on_conflict : str
            Conflict resolution strategy.
        correlation_id : str
            Import run identifier.
        blob_svc : ActivityBlobService
            Blob service instance for the main blobstore.
        """
        # phase 1: extract activities from all FIT files (sequential, fast)
        self.log("Phase 1: Extracting activities from FIT files...")
        activities: list[be_entities.ActivityEntity] = []
        max_size = self._config.blobstore_max_recording_size_bytes
        for fit_path in fit_files:
            try:
                file_size = fit_path.stat().st_size
                if file_size > max_size:
                    self.log(
                        f"Skipping {fit_path.name}: exceeds max size "
                        f"({max_size // (1024 * 1024)} MiB)"
                    )
                    continue
                fit_data = fit_path.read_bytes()
                summary = fit_extractor.extract_fit_summary(fit_data)
                activity = self._build_activity_from_fit(
                    fit_path=fit_path,
                    sport_type=sport_type,
                    correlation_id=correlation_id,
                    summary=summary,
                )
                activities.append(activity)
            except Exception as exc:
                self.log(f"Failed to extract {fit_path.name}: {exc}")
        self.log(f"Extracted {len(activities)} activities")
        self.update_progress(15)
        self.check_cancellation()

        if not activities:
            self.log("No valid activities extracted")
            self.update_progress(100)
            return

        # phase 2: conflict resolution (sequential)
        self.log("Phase 2: Resolving conflicts...")
        skipped = 0
        overridden_keys: set[str] = set()
        resolved: list[be_entities.ActivityEntity] = []
        for activity in activities:
            # find conflict using year from summary (embedded in activity date)
            existing_key = self._find_activity_conflict_bulldozer(
                user_id=user_id,
                dataset_name=dataset_name,
                activity=activity,
            )
            if existing_key:
                if on_conflict == "skip":
                    skipped += 1
                    self.log(f"Skipping {activity.src_key} (conflict)")
                    continue
                if on_conflict == "override":
                    activity.key = existing_key
                    overridden_keys.add(existing_key)
                # new_key: keep the generated key, create as new
            resolved.append(activity)

        self.log(
            f"Conflict resolution: {len(resolved)} to import, "
            f"{skipped} skipped, {len(overridden_keys)} overridden"
        )
        self.update_progress(20)
        self.check_cancellation()

        if not resolved:
            self.log("All activities skipped — import complete")
            self.update_progress(100)
            return

        # phase 3: create activities in dataset + clear overridden blobs
        self.log("Phase 3: Creating activities in dataset...")
        for overridden_key in sorted(overridden_keys):
            try:
                blob_svc.delete_all_activity_blobs(
                    user_id=user_id,
                    activity_key=overridden_key,
                )
            except Exception as exc:
                self.log(
                    f"WARNING: failed to clear blobs for overridden "
                    f"activity {overridden_key}: {exc}"
                )

        for activity in resolved:
            if activity.key in overridden_keys:
                ds.update_activity(
                    user_id=user_id,
                    dataset_name=dataset_name,
                    entity=activity,
                )
            else:
                ds.create_activity(
                    user_id=user_id,
                    dataset_name=dataset_name,
                    entity=activity,
                )
        self.log(f"Created/updated {len(resolved)} activities")
        self.update_progress(25)
        self.check_cancellation()

        # phase 4: bulldozer-parallelized blob processing
        self.log("Phase 4: Uploading recordings & generating parquet (parallel)...")

        workers = max(1, (os.cpu_count() or 1) // 2)
        chunks = _split_evenly(resolved, min(workers, len(resolved)))

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

        for i, chunk in enumerate(chunks):
            input_file = job_dirs[i] / "input" / "payload.json"
            activities_payload = []
            for a in chunk:
                d = a.to_dict()
                # find original FIT path from fit_files
                fit_path = None
                for fp in fit_files:
                    if fp.name == a.src_key:
                        fit_path = fp
                        break
                if fit_path:
                    d["_fit_path"] = str(fit_path)
                activities_payload.append(d)
            with open(input_file, "w") as fh:
                json.dump(
                    {
                        "user_id": user_id,
                        "activities": activities_payload,
                        "max_file_size": max_size,
                    },
                    fh,
                )

        self.log(
            f"Split {len(resolved)} activities into {len(chunks)} chunks "
            f"({len(chunks)} workers)"
        )

        bzz.run(job_dirs=job_dirs, job_function=_fit_directory_blob_job)

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
                f"Bulldozer jobs {failed_jobs} failed — see log for details"
            )

        self.log("All Bulldozer jobs DONE — merging blobstores...")
        self.update_progress(70)

        # phase 5: merge sandbox blobstores into main blobstore
        main_blobs_dir = persistence_root / "data" / user_id / "blobs"
        sandbox_blobs_dirs = [_sandbox_blobs_dir(d, user_id) for d in job_dirs]
        merged = blob_svc_module.ActivityBlobService.merge_sandbox_blobstores(
            sandbox_blobs_dirs=sandbox_blobs_dirs,
            main_blobs_dir=main_blobs_dir,
        )
        self.log(f"Merged {merged} blob directories from sandboxes into main store")
        self.update_progress(80)

        # phase 6: collect results and update activities with blob keys
        self.log("Phase 6: Collecting results and updating activities...")
        updated_count = 0
        failed_count = 0
        for job_dir in job_dirs:
            output_file = job_dir / "output" / "payload.json"
            if not output_file.exists():
                continue
            with open(output_file) as fh:
                chunk_data = json.load(fh)
            for d in chunk_data.get("activities", []):
                d.pop("_fit_path", None)
                try:
                    activity = be_entities.ActivityEntity(**d)
                    ds.update_activity(
                        user_id=user_id,
                        dataset_name=dataset_name,
                        entity=activity,
                    )
                    updated_count += 1
                except Exception as exc:
                    failed_count += 1
                    self.log(f"Failed to update activity {d.get('key', '?')}: {exc}")

        self.update_progress(100)
        self.log(
            f"FIT directory import complete: {updated_count} imported, "
            f"{skipped} skipped, {failed_count} failed"
        )

    def _build_activity_from_fit(
        self,
        fit_path: pathlib.Path,
        sport_type: str,
        correlation_id: str,
        summary: fit_extractor.RecordingSummary,
    ) -> be_entities.ActivityEntity:
        """Build an ActivityEntity from a FIT file summary.

        Parameters
        ----------
        fit_path : pathlib.Path
            Path to the FIT file.
        sport_type : str
            Optional sport type override.
        correlation_id : str
            Import run identifier.
        summary : RecordingSummary
            Summary extracted from the FIT file.

        Returns
        -------
        ActivityEntity
            New activity entity with key assigned.
        """
        # determine activity name: use name_hint from FIT or filename stem
        if summary.name_hint:
            activity_name = summary.name_hint
        else:
            activity_name = fit_path.stem

        activity = be_entities.ActivityEntity()
        activity.key = ds.create_key()
        activity.name = activity_name

        # set sport type from parameter or summary
        if sport_type:
            activity.activity_type_key = sport_type
        elif summary.activity_type_key:
            activity.activity_type_key = summary.activity_type_key

        # set datetime from summary if available
        if summary.when:
            activity.when = summary.when.strftime("%Y-%m-%d %H:%M")
            activity.when_year = summary.when.year
            activity.when_month = summary.when.month
            activity.when_day = summary.when.day
            activity.when_hour = summary.when.hour
            activity.when_minute = summary.when.minute
            activity.when_second = summary.when.second

        # set duration from summary
        if summary.hours is not None:
            activity.hours = summary.hours
        if summary.minutes is not None:
            activity.minutes = summary.minutes
        if summary.seconds is not None:
            activity.seconds = summary.seconds

        # set distance from summary
        if summary.distance:
            activity.distance = summary.distance

        # set kcal from summary
        if summary.kcal:
            activity.kcal = summary.kcal

        # set HR data from summary
        if summary.avg_hr:
            activity.avg_hr = summary.avg_hr
        if summary.max_hr:
            activity.max_hr = summary.max_hr

        # set cadence from summary
        if summary.avg_cadence:
            activity.avg_cadence = summary.avg_cadence
        if summary.max_cadence:
            activity.max_cadence = summary.max_cadence

        # set speed from summary
        if summary.avg_speed:
            activity.avg_speed = summary.avg_speed
        if summary.max_speed:
            activity.max_speed = summary.max_speed

        # set power from summary
        if summary.avg_watts:
            activity.avg_watts = summary.avg_watts
        if summary.max_watts:
            activity.max_watts = summary.max_watts

        # set elevation from summary
        if summary.elevation_gain:
            activity.elevation_gain = summary.elevation_gain

        activity.src = "fit-import"
        activity.src_key = fit_path.name
        activity.src_descriptor = f"directory-import-{correlation_id}"

        return activity

    def _find_activity_conflict_bulldozer(
        self,
        user_id: str,
        dataset_name: str,
        activity: be_entities.ActivityEntity,
    ) -> str | None:
        """Return existing activity's key if conflict, else None.

        Searches all years for conflicts since the activity's ``when_year``
        may default to the current year when the recording has no timestamp.
        """
        if not activity.src_key:
            return None
        year_activities = ds.list_activities(
            user_id=user_id,
            dataset_name=dataset_name,
            filter_year=0,
        )
        for existing in year_activities:
            if existing.src == activity.src and existing.src_key == activity.src_key:
                return existing.key
        return None

    def _process_single_fit(
        self,
        user_id: str,
        dataset_name: str,
        fit_path: pathlib.Path,
        sport_type: str,
        on_conflict: str,
        correlation_id: str,
        blob_svc: blob_svc_module.ActivityBlobService,
    ) -> str:
        """Process a single FIT file.

        Parameters
        ----------
        user_id : str
            Owning user identifier.
        dataset_name : str
            Target dataset name.
        fit_path : pathlib.Path
            Path to the FIT file.
        sport_type : str
            Optional sport type override.
        on_conflict : str
            Conflict resolution strategy.
        correlation_id : str
            Import run identifier.
        blob_svc : ActivityBlobService
            Blob service instance.

        Returns
        -------
        str
            "imported", "skipped", or raises exception on failure.
        """
        # validate file size before reading
        max_size = self._config.blobstore_max_recording_size_bytes
        file_size = fit_path.stat().st_size
        if file_size > max_size:
            raise RuntimeError(
                f"FIT file {fit_path.name} exceeds maximum allowed size "
                f"({max_size // (1024 * 1024)} MiB)"
            )

        # read FIT file once and reuse for summary extraction
        fit_data = fit_path.read_bytes()

        # extract summary and build activity entity
        summary = fit_extractor.extract_fit_summary(fit_data)
        activity = self._build_activity_from_fit(
            fit_path=fit_path,
            sport_type=sport_type,
            correlation_id=correlation_id,
            summary=summary,
        )

        # check for conflicts
        existing_key = self._find_activity_conflict(
            user_id=user_id,
            dataset_name=dataset_name,
            activity=activity,
            summary=summary,
        )

        if existing_key:
            self.log(
                f"Conflict detected for {fit_path.name}: "
                f"existing_key={existing_key}, strategy={on_conflict}"
            )
            if on_conflict == "skip":
                self.log(f"Skipping {fit_path.name} (conflict)")
                return "skipped"
            elif on_conflict == "override":
                # delete existing blobs to avoid storage leak
                blob_svc.delete_all_activity_blobs(
                    user_id=user_id,
                    activity_key=existing_key,
                )
                activity.key = existing_key
                ds.update_activity(
                    user_id=user_id,
                    dataset_name=dataset_name,
                    entity=activity,
                )
                self.log(f"Updated activity from {fit_path.name}")
            # else: on_conflict == "new_key" — fall through to create with new key

        # create activity if not overriding an existing one
        if not existing_key or on_conflict != "override":
            ds.create_activity(
                user_id=user_id,
                dataset_name=dataset_name,
                entity=activity,
            )
            self.log(f"Created activity {activity.key} from {fit_path.name}")

        self.log(
            f"Processing {fit_path.name}: key={activity.key}, "
            f"when_year={activity.when_year}, src_key={activity.src_key}"
        )

        # upload FIT blob (reuse already-read data via BytesIO)
        meta = blob_svc.upload_recording(
            user_id=user_id,
            activity_key=activity.key,
            uploaded_file=io.BytesIO(fit_data),
            original_filename=fit_path.name,
            content_type="application/octet-stream",
        )

        # convert to parquet directly
        try:
            parquet_bytes = parquet_converter.fit_to_parquet(fit_data)
            blob_svc.save_parquet(
                user_id=user_id,
                activity_key=activity.key,
                source_blob_key=meta.blob_key,
                parquet_data=parquet_bytes,
            )
            self.log(f"Parquet saved for {fit_path.name}")
        except Exception as exc:
            self.log(f"WARNING: Parquet conversion failed for {fit_path.name}: {exc}")

        # pre-generate map data (polylines, elevation profile) so that the
        # first page view of the activity is fast instead of blocking the UI
        # for tens of seconds while the FIT is re-parsed on the request thread
        try:
            self.log("Generating map data...")
            blob_svc.ensure_gpx_map_data(
                user_id=user_id,
                activity_key=activity.key,
                blob_key=meta.blob_key,
            )
            self.log("Map data generated")
        except Exception as exc:
            self.log(f"WARNING: Map data generation failed for {fit_path.name}: {exc}")

        return "imported"

    def _find_activity_conflict(
        self,
        user_id: str,
        dataset_name: str,
        activity: be_entities.ActivityEntity,
        summary: fit_extractor.RecordingSummary,
    ) -> str | None:
        """Return existing activity's key if conflict, else None.

        Conflict is determined by src_key (FIT filename).
        Uses summary.when.year when available, otherwise searches all years.
        """
        if activity.src_key:
            # use summary year when available; otherwise search all years
            # (activity.when_year defaults to current year, which would miss
            # conflicts from the same file imported in a prior year)
            filter_year = summary.when.year if summary.when else 0
            year_activities = ds.list_activities(
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


tasks.tasks_registry.register_task(FitDirectoryImportTask)
