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

"""Async task: import activities from a GoldenCheetah OSF athlete ZIP.

GoldenCheetahOsfImportTask.execute()
 1. Resolve task parameters
 2. Parse ZIP via GoldenCheetahOsfImportPlugin → list[ActivityEntity]
 3. Conflict-resolve (skip / override / add-as-new) with lazy year cache
 4. evaluate_activity() for each kept activity
 5. Bulk persist: create_activities() + update_activities()
 6. CSV → Parquet: Bulldozer-parallelised conversion of per-activity 1-second
    CSVs to canonical Parquet blobs so the Analysis page shows HR / power /
    cadence / altitude charts.  Each CSV is also stored as a downloadable
    ACTIVITY_RECORDING blob (UUID.csv) so it appears in the recordings list.
    Uses the same sandbox-merge pattern as the Strava archive import.

"""

import datetime
import hashlib
import io
import json
import os
import pathlib
import traceback
import zipfile

from mytral import app_logger
from mytral import config as mytral_config
from mytral import plugins
from mytral import tasks
from mytral.backends import entities
from mytral.blobstore import activity_service as blob_svc_module
from mytral.blobstore.filesystem import FilesystemBlobStore
from mytral.blobstore.models import BlobKind
from mytral.integrations import golden_cheetah_osf
from mytral.recordings import parquet_converter
from mytral.tasks import bulldozer
from mytral.tasks.bulldozer._sandbox_utils import _make_blob_metadata
from mytral.tasks.bulldozer._sandbox_utils import _sandbox_blobs_dir
from mytral.tasks.bulldozer._sandbox_utils import _split_evenly


def _gc_csv_blob_job(job_key: int, job_dir: pathlib.Path) -> None:
    """Bulldozer job: convert GoldenCheetah CSVs to blobs in a sandbox.

    For each activity whose CSV is found in the ZIP:
      - Stores the raw CSV as an ACTIVITY_RECORDING blob (downloadable).
      - Converts the CSV to Parquet and stores it as ACTIVITY_PARQUET.
      - Links recording → parquet in ``recorded_parquet_keys``.

    Reads ``job_dir/input/payload.json``.
    Writes updated activity dicts to ``job_dir/output/payload.json``.
    On failure writes ``job_dir/output/error.json``.
    """
    try:
        _gc_csv_blob_job_impl(job_key, job_dir)
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


def _gc_csv_blob_job_impl(job_key: int, job_dir: pathlib.Path) -> None:
    """Implementation of :func:`_gc_csv_blob_job`."""
    input_file = job_dir / "input" / "payload.json"
    if not input_file.exists():
        return

    with open(input_file) as fh:
        payload = json.load(fh)

    activities_data = payload.get("activities", [])
    if not activities_data:
        return

    user_id = payload["user_id"]
    zip_path = payload["zip_path"]
    now = payload.get(
        "now_iso", datetime.datetime.now(datetime.timezone.utc).isoformat()
    )

    sandbox_config = mytral_config.MytralConfig(persistence_data_dir=job_dir / "work")
    sandbox_store = FilesystemBlobStore(
        base_dir=sandbox_config.user_data_dir,
        blobs_subdir="blobs",
    )

    updated_activities = []

    with zipfile.ZipFile(zip_path) as zf:
        csv_stems: set[str] = {
            n.removesuffix(".csv") for n in zf.namelist() if n.endswith(".csv")
        }

        for d in activities_data:
            activity_key = d["key"]
            when_utc = datetime.datetime(
                d["when_year"],
                d["when_month"],
                d["when_day"],
                d["when_hour"],
                d["when_minute"],
                d["when_second"],
                tzinfo=datetime.timezone.utc,
            )
            csv_stem = golden_cheetah_osf.find_csv_stem(when_utc, csv_stems)
            if not csv_stem:
                continue

            with zf.open(f"{csv_stem}.csv") as fh:
                csv_bytes = fh.read()

            # store raw CSV as a downloadable ACTIVITY_RECORDING blob
            csv_meta = _make_blob_metadata(
                user_id=user_id,
                activity_key=activity_key,
                kind=BlobKind.ACTIVITY_RECORDING.value,
                file_name="data.csv",
                original_file_name=f"{csv_stem}.csv",
                extension=".csv",
                size_bytes=len(csv_bytes),
                sha256=hashlib.sha256(csv_bytes).hexdigest(),
                content_type="text/csv",
                name="GoldenCheetah recording",
                description="Imported from GoldenCheetah OSF archive",
                keywords=["golden-cheetah", "csv"],
                created_at=now,
            )
            sandbox_store.create_blob(csv_meta, io.BytesIO(csv_bytes))

            # convert CSV to Parquet and store as ACTIVITY_PARQUET
            try:
                pq_bytes = parquet_converter.gc_csv_to_parquet(csv_bytes, when_utc)
            except Exception:
                continue

            pq_meta = _make_blob_metadata(
                user_id=user_id,
                activity_key=activity_key,
                kind=BlobKind.ACTIVITY_PARQUET.value,
                file_name="data.parquet",
                original_file_name="data.parquet",
                extension=".parquet",
                size_bytes=len(pq_bytes),
                sha256=hashlib.sha256(pq_bytes).hexdigest(),
                created_at=now,
            )
            sandbox_store.create_blob(pq_meta, io.BytesIO(pq_bytes))

            # link: recording blob UUID → parquet blob UUID (Analysis page lookup key)
            d["recorded_blob_keys"] = list(d.get("recorded_blob_keys") or [])
            d["recorded_blob_keys"].append(f"{csv_meta.blob_key}.csv")
            d["recorded_parquet_keys"] = dict(d.get("recorded_parquet_keys") or {})
            d["recorded_parquet_keys"][csv_meta.blob_key] = pq_meta.blob_key
            updated_activities.append(d)

    output_file = job_dir / "output" / "payload.json"
    output_file.parent.mkdir(parents=True, exist_ok=True)
    with open(output_file, "w") as fh:
        json.dump({"activities": updated_activities}, fh)


class GoldenCheetahOsfImportTask(tasks.TaskBase):
    """Import activities from a GoldenCheetah OSF athlete ZIP archive."""

    TASK_TYPE = "golden_cheetah_osf_import"
    TASK_DISPLAY_NAME = "GoldenCheetah OSF Import"

    ZIP_PATH_KEY = golden_cheetah_osf.GC_OSF_ZIP_PATH_KEY

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
        self._log_name = "[GoldenCheetah OSF Import Task]"

    def execute(self) -> None:
        """Execute GoldenCheetah OSF import.

        Raises
        ------
        RuntimeError
            On unrecoverable failures.
        """
        params = self.task_entity.parameters
        user_id: str = params["user_id"]
        dataset_name: str = params["dataset_name"]
        zip_path_str: str = params[GoldenCheetahOsfImportTask.ZIP_PATH_KEY]
        on_conflict: str = params.get("on_conflict", "skip")

        self.log(
            f"GoldenCheetah OSF import started "
            f"(zip={zip_path_str}, on_conflict={on_conflict})"
        )
        self.update_progress(2)

        # PHASE 1: parse ZIP via plugin
        plugin: golden_cheetah_osf.GoldenCheetahOsfImportPlugin = (
            plugins.registry.get_plugin(
                golden_cheetah_osf.GoldenCheetahOsfImportPlugin.NAME
            )
        )
        user_profile = self._dataset.profile(user_id)
        self.log("Parsing GoldenCheetah JSON index...")

        try:
            activities = plugin.import_activities(
                datasets={golden_cheetah_osf.GC_OSF_ZIP_PATH_KEY: zip_path_str},
                user_profile=user_profile,
            )
        except Exception as exc:
            raise RuntimeError(f"Failed to parse GoldenCheetah archive: {exc}") from exc

        total = len(activities)
        self.log(f"Parsed {total} activities from {zip_path_str}")
        self.update_progress(20)
        self.check_cancellation()

        if total == 0:
            self.log("No activities found — import complete")
            self.update_progress(100)
            return

        # PHASE 2: conflict-resolve and evaluate
        year_cache: dict[int, list] = {}
        activities_to_create: list[entities.ActivityEntity] = []
        activities_to_update: list[entities.ActivityEntity] = []
        skipped = 0
        imported = 0

        for i, activity in enumerate(activities):
            if i % 50 == 0:
                self.check_cancellation()
            existing_key = self._find_conflict(user_id, activity, year_cache)
            if existing_key:
                if on_conflict == "skip":
                    skipped += 1
                    continue
                if on_conflict == "override":
                    activity.key = existing_key
                else:
                    # new_key: keep the generated key, treat as new
                    existing_key = None

            entities.evaluate_activity(entity=activity, user_profile=user_profile)
            if not existing_key:
                activities_to_create.append(activity)
            else:
                activities_to_update.append(activity)
            imported += 1

        self.log(
            f"Conflict resolution: {imported} to import, {skipped} skipped, "
            f"{len(activities_to_create)} to create, "
            f"{len(activities_to_update)} to update"
        )
        self.update_progress(60)

        # PHASE 3: bulk persist
        try:
            if activities_to_create:
                self._dataset.create_activities(
                    user_id=user_id,
                    dataset_name=dataset_name,
                    entity_list=activities_to_create,
                )
            if activities_to_update:
                self._dataset.update_activities(
                    user_id=user_id,
                    dataset_name=dataset_name,
                    activities=activities_to_update,
                )
        except Exception as exc:
            app_logger.exception(
                f"{self._log_name} persist failed",
                error=str(exc),
                traceback=traceback.format_exc(),
                user_id=user_id,
            )
            raise RuntimeError(f"Failed to persist activities: {exc}") from exc

        self.update_progress(70)

        # PHASE 4: CSV → Parquet recordings for the Analysis page (Bulldozer)
        self._ingest_csv_recordings(
            user_id=user_id,
            dataset_name=dataset_name,
            zip_path_str=zip_path_str,
            activities=activities_to_create + activities_to_update,
        )

        self.log(
            f"GoldenCheetah OSF import complete: {imported} imported, {skipped} skipped"
        )
        self.update_progress(100)

    def _ingest_csv_recordings(
        self,
        user_id: str,
        dataset_name: str,
        zip_path_str: str,
        activities: list[entities.ActivityEntity],
    ) -> None:
        """Convert per-activity CSVs to blobs via Bulldozer worker processes.

        Each matching CSV is stored as a downloadable ACTIVITY_RECORDING blob
        and also converted to Parquet for the Analysis page charts.
        """
        if not activities:
            return

        # delete old recording + parquet blobs for activities being re-imported
        for a in activities:
            for entry in list(a.recorded_blob_keys or []):
                entry_uuid = entry.rsplit(".", 1)[0]
                try:
                    self._blobstore.delete_blob(user_id, entry_uuid)
                except Exception:
                    pass
            for pq_key in list((a.recorded_parquet_keys or {}).values()):
                try:
                    self._blobstore.delete_blob(user_id, pq_key)
                except Exception:
                    pass

        total = len(activities)
        workers = max(1, (os.cpu_count() or 1) // 2)
        chunks = _split_evenly(activities, min(workers, total))

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

        now_iso = datetime.datetime.now(datetime.timezone.utc).isoformat()
        for i, chunk in enumerate(chunks):
            input_file = job_dirs[i] / "input" / "payload.json"
            with open(input_file, "w") as fh:
                json.dump(
                    {
                        "user_id": user_id,
                        "zip_path": zip_path_str,
                        "now_iso": now_iso,
                        "activities": [a.to_dict() for a in chunk],
                    },
                    fh,
                )

        self.log(
            f"Split {total} activities into {len(chunks)} CSV chunks "
            f"({len(chunks)} workers)"
        )
        self.check_cancellation()

        bzz.run(job_dirs=job_dirs, job_function=_gc_csv_blob_job)
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
                    f"ERROR: CSV Bulldozer job {err['job_key']} failed:\n"
                    f"{err['traceback']}"
                )
        if failed_jobs:
            raise RuntimeError(
                f"CSV Bulldozer jobs {failed_jobs} failed — see log for details"
            )

        # merge sandbox blobstores into main blobstore
        main_blobs_dir = persistence_root / "data" / user_id / "blobs"
        sandbox_blobs_dirs = [_sandbox_blobs_dir(d, user_id) for d in job_dirs]
        merged = blob_svc_module.ActivityBlobService.merge_sandbox_blobstores(
            sandbox_blobs_dirs=sandbox_blobs_dirs,
            main_blobs_dir=main_blobs_dir,
        )
        self.log(f"Merged {merged} CSV/Parquet blobs from sandboxes into main store")

        # collect updated activities from worker outputs
        updated_activities: list[entities.ActivityEntity] = []
        for job_dir in job_dirs:
            output_file = job_dir / "output" / "payload.json"
            if not output_file.exists():
                continue
            with open(output_file) as fh:
                chunk_data = json.load(fh)
            for d in chunk_data.get("activities", []):
                d.pop("transient_fields", None)
                updated_activities.append(entities.ActivityEntity(**d))

        recordings_added = len(updated_activities)

        # batch-update activities with new recorded_blob_keys + recorded_parquet_keys
        if updated_activities:
            self._dataset.update_activities(
                user_id=user_id,
                dataset_name=dataset_name,
                activities=updated_activities,
            )

        self.log(f"CSV recordings ingested as Parquet: {recordings_added}")

    def _find_conflict(
        self,
        user_id: str,
        activity: entities.ActivityEntity,
        year_cache: dict[int, list],
    ) -> str | None:
        """Return the key of an existing conflicting activity or None.

        Uses src + src_key matching.  year_cache is populated lazily on
        first access per year to avoid repeated JSON reads.
        """
        if not activity.src_key:
            return None
        year = activity.when_year
        if year not in year_cache:
            try:
                year_cache[year] = self._dataset.list_activities(
                    user_id=user_id,
                    year=year,
                )
            except Exception:
                year_cache[year] = []
        for act in year_cache[year]:
            if act.src == activity.src and act.src_key == activity.src_key:
                return act.key
        return None


tasks.tasks_registry.register_task(GoldenCheetahOsfImportTask)
