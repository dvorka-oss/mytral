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

"""Async task: import multiple FIT files from a directory using bulldozer."""

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

from mytral import config as mytral_config
from mytral import tasks
from mytral.backends import entities as be_entities
from mytral.blobstore import activity_service as blob_svc_module
from mytral.blobstore.filesystem import FilesystemBlobStore
from mytral.blobstore.models import BlobKind
from mytral.recordings import fit_extractor
from mytral.recordings import parquet_converter
from mytral.tasks import bulldozer
from mytral.tasks.bulldozer._sandbox_utils import _make_blob_metadata
from mytral.tasks.bulldozer._sandbox_utils import _sandbox_blobs_dir
from mytral.tasks.bulldozer._sandbox_utils import _split_evenly

# valid ActivityEntity dataclass field names for dict reconstruction
_ACTIVITY_FIELDS = {f.name for f in dataclasses.fields(be_entities.ActivityEntity)}


def _fit_directory_blob_job(job_key: int, job_dir: pathlib.Path) -> None:
    """Bulldozer job: extract summaries, upload recordings and convert to Parquet.

    Reads ``job_dir/input/payload.json`` which provides a list of FIT file
    paths.  For each file the worker extracts the activity summary, builds an
    activity dict, uploads the recording and converts to Parquet — all inside
    an isolated sandbox blobstore.

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

    fit_paths: list[str] = payload.get("fit_paths", [])
    if not fit_paths:
        return

    user_id = payload.get("user_id", "")
    sport_type = payload.get("sport_type", "")
    correlation_id = payload.get("correlation_id", "")

    # create isolated blobstore inside the sandbox
    sandbox_config = mytral_config.MytralConfig(persistence_data_dir=job_dir / "work")
    sandbox_store = FilesystemBlobStore(
        base_dir=sandbox_config.user_data_dir,
        blobs_subdir="blobs",
    )

    now = datetime.datetime.now(datetime.timezone.utc).isoformat()
    activities: list[dict] = []

    for idx, fit_path_str in enumerate(fit_paths):
        fit_path = pathlib.Path(fit_path_str)

        try:
            fit_data = fit_path.read_bytes()
        except OSError:
            continue

        # extract summary from FIT session message
        summary = fit_extractor.extract_fit_summary(fit_data)

        # build activity dict with a temporary key
        temp_key = f"temp-{job_key}-{idx}"
        d: dict[str, object] = {"key": temp_key}

        # name
        if summary.name_hint:
            d["name"] = summary.name_hint
        else:
            d["name"] = fit_path.stem

        # sport type: parameter overrides summary
        if sport_type:
            d["activity_type_key"] = sport_type
        elif summary.activity_type_key:
            d["activity_type_key"] = summary.activity_type_key

        # datetime
        if summary.when:
            d["when"] = summary.when.strftime("%Y-%m-%d %H:%M")
            d["when_year"] = summary.when.year
            d["when_month"] = summary.when.month
            d["when_day"] = summary.when.day
            d["when_hour"] = summary.when.hour
            d["when_minute"] = summary.when.minute
            d["when_second"] = summary.when.second

        # duration
        if summary.hours is not None:
            d["hours"] = summary.hours
        if summary.minutes is not None:
            d["minutes"] = summary.minutes
        if summary.seconds is not None:
            d["seconds"] = summary.seconds

        # metrics
        if summary.distance:
            d["distance"] = summary.distance
        if summary.kcal:
            d["kcal"] = summary.kcal
        if summary.avg_hr:
            d["avg_hr"] = summary.avg_hr
        if summary.max_hr:
            d["max_hr"] = summary.max_hr
        if summary.avg_cadence:
            d["avg_cadence"] = summary.avg_cadence
        if summary.max_cadence:
            d["max_cadence"] = summary.max_cadence
        if summary.avg_speed:
            d["avg_speed"] = summary.avg_speed
        if summary.max_speed:
            d["max_speed"] = summary.max_speed
        if summary.avg_watts:
            d["avg_watts"] = summary.avg_watts
        if summary.max_watts:
            d["max_watts"] = summary.max_watts
        if summary.elevation_gain:
            d["elevation_gain"] = summary.elevation_gain

        # source tracking
        d["src"] = "fit-import"
        d["src_key"] = fit_path.name
        d["src_descriptor"] = f"directory-import-{correlation_id}"

        # upload recording blob to sandbox
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
            description="Imported from FIT directory",
            keywords=["fit", "directory-import"],
            created_at=now,
        )
        sandbox_store.create_blob(rec_meta, io.BytesIO(fit_data))
        d["recorded_blob_keys"] = [f"{rec_meta.blob_key}.fit"]

        # convert to parquet
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

        # store fit path for post-processing conflict detection
        d["_fit_path"] = fit_path_str
        activities.append(d)

    # write processed activities to output
    output_file = job_dir / "output" / "payload.json"
    output_file.parent.mkdir(parents=True, exist_ok=True)
    with open(output_file, "w") as fh:
        json.dump({"activities": activities}, fh)


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
        """Execute FIT directory import task using bulldozer multiprocessing.

         Raises
        ---
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
        self.update_progress(2)
        self.check_cancellation()

        # validate directory
        dir_path = pathlib.Path(data_dir)
        if not dir_path.is_dir():
            raise RuntimeError(f"Directory does not exist: {data_dir}")

        # find all .fit files
        fit_files = sorted(
            path
            for path in dir_path.iterdir()
            if path.is_file() and path.suffix.lower() == ".fit"
        )
        if not fit_files:
            self.log("No FIT files found in directory")
            self.update_progress(100)
            return

        total = len(fit_files)
        self.log(f"Found {total} FIT files")
        for e, f in enumerate(fit_files):
            self.log(f"  #{e + 1}/{total} {f.name}")
        self.update_progress(5)
        self.check_cancellation()

        # validate file sizes before dispatching
        max_size = self._config.blobstore_max_recording_size_bytes
        for fit_path in fit_files:
            file_size = fit_path.stat().st_size
            if file_size > max_size:
                raise RuntimeError(
                    f"FIT file {fit_path.name} exceeds maximum allowed "
                    f"size ({max_size // (1024 * 1024)} MiB)"
                )

        # # PHASE 1: bulldozer-parallelized summary extraction + blob upload
        workers = max(1, (os.cpu_count() or 1) // 2)
        chunks = _split_evenly([str(p) for p in fit_files], min(workers, total))

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
            with open(input_file, "w") as fh:
                json.dump(
                    {
                        "user_id": user_id,
                        "fit_paths": chunk,
                        "sport_type": sport_type,
                        "correlation_id": correlation_id,
                    },
                    fh,
                )

        self.log(
            f"Dispatching {total} FIT files across {len(chunks)} "
            f"workers ({len(chunks)} chunks)"
        )
        self.update_progress(10)
        self.check_cancellation()

        # run bulldozer — all heavy work happens here in parallel
        bzz.run(job_dirs=job_dirs, job_function=_fit_directory_blob_job)
        self.check_cancellation()

        # detect and report failed jobs
        failed_jobs = []
        for job_dir in job_dirs:
            error_file = job_dir / "output" / "error.json"
            if error_file.exists():
                with open(error_file) as fh:
                    err = json.load(fh)
                failed_jobs.append(err["job_key"])
                self.log(
                    f"ERROR: multiprocessing job {err['job_key']} failed:\n"
                    f"{err['traceback']}"
                )
        if failed_jobs:
            raise RuntimeError(
                f"Multiprocessing jobs {failed_jobs} failed - see log for details"
            )

        self.log("All multiprocessing jobs DONE - post-processing results...")
        self.update_progress(50)
        self.check_cancellation()

        # # PHASE 2: collect results, resolve conflicts, merge, persist

        # collect all activity dicts from all job outputs
        all_dicts: list[dict] = []
        for job_dir in job_dirs:
            output_file = job_dir / "output" / "payload.json"
            if not output_file.exists():
                continue
            with open(output_file) as fh:
                chunk_data = json.load(fh)
            all_dicts.extend(chunk_data.get("activities", []))

        if not all_dicts:
            self.log("No activities produced by multiprocessing jobs")
            self.update_progress(100)
            return

        self.log(
            f"Collected {len(all_dicts)} activity dicts from "
            f"{len(job_dirs)} job outputs"
        )
        self.update_progress(55)
        self.check_cancellation()

        # resolve conflicts and assign final activity keys
        blob_svc = blob_svc_module.ActivityBlobService(
            store=self._blobstore,
            dataset=self._dataset,
            config=self._config,
        )

        # temp_key -> final_key mapping for sandbox directory renaming
        temp_to_final: dict[str, str] = {}
        skipped_temp_keys: list[str] = []
        new_entries: list[dict] = []  # (final_key, dict)
        override_entries: list[dict] = []  # (final_key, dict)
        skipped_count = 0
        failed_count = 0

        for d in all_dicts:
            temp_key = d["key"]
            fit_filename = d.get("src_key", "")

            try:
                # reconstruct a temporary ActivityEntity for conflict detection
                entity_fields = {k: v for k, v in d.items() if k in _ACTIVITY_FIELDS}
                activity = be_entities.ActivityEntity(**entity_fields)

                # determine filter year for conflict lookup
                filter_year = activity.when_year if activity.when_year else 0

                existing_key = self._find_activity_conflict(
                    user_id=user_id,
                    dataset_name=dataset_name,
                    activity=activity,
                    filter_year=filter_year,
                )

                if existing_key:
                    self.log(
                        f"Conflict detected for {fit_filename}: "
                        f"existing_key={existing_key}, strategy={on_conflict}"
                    )
                    if on_conflict == "skip":
                        self.log(f"Skipping {fit_filename} (conflict)")
                        skipped_temp_keys.append(temp_key)
                        skipped_count += 1
                        continue
                    elif on_conflict == "override":
                        temp_to_final[temp_key] = existing_key
                        override_entries.append(d)
                    else:
                        # new_key: generate fresh key
                        final_key = self._dataset.create_key()
                        temp_to_final[temp_key] = final_key
                        new_entries.append(d)
                else:
                    final_key = self._dataset.create_key()
                    temp_to_final[temp_key] = final_key
                    new_entries.append(d)

            except Exception as exc:
                failed_count += 1
                self.log(f"Failed to resolve conflict for {fit_filename}: {exc}")
                skipped_temp_keys.append(temp_key)

        self.update_progress(65)
        self.check_cancellation()

        processed_count = len(new_entries) + len(override_entries)
        if processed_count == 0:
            self.update_progress(100)
            self.log(
                f"FIT directory import complete: 0 imported, "
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

        # rename sandbox activity directories from temp keys to final keys
        for job_dir in job_dirs:
            sandbox_activities = _sandbox_blobs_dir(job_dir, user_id) / "activities"
            if not sandbox_activities.is_dir():
                continue
            for temp_key, final_key in temp_to_final.items():
                temp_dir = sandbox_activities / temp_key
                final_dir = sandbox_activities / final_key
                if temp_dir.is_dir() and not final_dir.exists():
                    temp_dir.rename(final_dir)

        # delete sandbox directories for skipped activities
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

        # build final ActivityEntity list with correct keys and blob references
        new_entity_list: list[be_entities.ActivityEntity] = []
        override_entity_list: list[be_entities.ActivityEntity] = []

        for d in new_entries:
            final_key = temp_to_final[d["key"]]
            d["key"] = final_key
            d.pop("_fit_path", None)
            d.pop("transient_fields", None)
            entity_fields = {k: v for k, v in d.items() if k in _ACTIVITY_FIELDS}
            new_entity_list.append(be_entities.ActivityEntity(**entity_fields))

        for d in override_entries:
            final_key = temp_to_final[d["key"]]
            d["key"] = final_key
            d.pop("_fit_path", None)
            d.pop("transient_fields", None)
            entity_fields = {k: v for k, v in d.items() if k in _ACTIVITY_FIELDS}
            override_entity_list.append(be_entities.ActivityEntity(**entity_fields))

        # bulk-create new activities
        if new_entity_list:
            self._dataset.create_activities(
                user_id=user_id,
                dataset_name=dataset_name,
                entity_list=new_entity_list,
            )
            self.log(f"Created {len(new_entity_list)} new activities")

        # update overridden activities
        if override_entity_list:
            self._dataset.update_activities(
                user_id=user_id,
                dataset_name=dataset_name,
                activities=override_entity_list,
            )
            self.log(f"Updated {len(override_entity_list)} overridden activities")

        self.update_progress(95)
        self.check_cancellation()

        imported_count = processed_count
        self.update_progress(100)
        self.log(
            f"FIT directory import complete: {imported_count} imported, "
            f"{skipped_count} skipped, {failed_count} failed"
        )

    def _find_activity_conflict(
        self,
        user_id: str,
        dataset_name: str,
        activity: be_entities.ActivityEntity,
        filter_year: int = 0,
    ) -> str | None:
        """Return existing activity's key if conflict, else None.

         Conflict is determined by matching ``(src, src_key)`` against existing
         activities.  When *filter_year* is non-zero the search is scoped to
         that year; otherwise all years are searched.

         Parameters
        -------
         user_id : str
             Owning user identifier.
         dataset_name : str
             Target dataset name.
         activity : ActivityEntity
             Activity with ``src`` and ``src_key`` set.
         filter_year : int
             Year to scope the search to (0 = all years).
        """
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


tasks.tasks_registry.register_task(FitDirectoryImportTask)
