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
# along with this program.  If not, see <http://www.gnu.org/licenses/>.

"""Async task: import Polar Precision Performance (.hrm + .pdd) files:

PolarHrmImportTask.execute()
 1. BLOB store initialization & orphans cleanup
 2. Create activities from .hrm/.pdd files:
    PolarHrmImportPlugin.import_activities()
 3. Bulldozer-parallelized blob processing:
    - split activities evenly across workers
    - each subprocess creates sandbox blobstore and stores recordings + parquet
 4. Merge sandbox blobstores into main blobstore
 5. Conflict-resolve and bulk persist activities to main dataset

"""

import datetime
import hashlib
import io
import json
import os
import pathlib
import traceback
import uuid

from mytral import app_logger
from mytral import config as mytral_config
from mytral import plugins
from mytral import tasks
from mytral.backends import entities
from mytral.blobstore import activity_service as blob_svc_module
from mytral.blobstore.filesystem import FilesystemBlobStore
from mytral.blobstore.models import BlobKind
from mytral.blobstore.models import BlobMetadata
from mytral.blobstore.models import BlobOwnerKind
from mytral.integrations import polar_hrm
from mytral.recordings import parquet_converter
from mytral.tasks import bulldozer


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
    name: str,
    description: str,
    keywords: list[str],
    created_at: str,
) -> BlobMetadata:
    """Build a ``BlobMetadata`` for a recording or parquet blob."""
    blob_key = str(uuid.uuid4()).replace("-", "")
    return BlobMetadata(
        blob_key=blob_key,
        user_id=user_id,
        owner_kind=BlobOwnerKind.ACTIVITY.value,
        owner_key=activity_key,
        kind=kind,
        file_name=file_name,
        original_file_name=original_file_name,
        extension=extension,
        content_type="application/octet-stream",
        size_bytes=size_bytes,
        sha256=sha256,
        name=name,
        description=description,
        keywords=keywords,
        created_at=created_at,
        updated_at=created_at,
    )


def _split_evenly(items: list, num_chunks: int) -> list[list]:
    """Distribute items round-robin across *num_chunks* buckets."""
    if num_chunks < 1:
        return [items]
    chunks: list[list] = [[] for _ in range(num_chunks)]
    for i, item in enumerate(items):
        chunks[i % num_chunks].append(item)
    return [c for c in chunks if c]


def _polar_hrm_blob_job(job_key: int, job_dir: pathlib.Path) -> None:
    """Bulldozer job: process Polar HRM recordings in a sandbox.

    Reads activities from ``job_dir/input/activities.json``, creates an
    isolated blobstore for the sandbox, uploads HRM recordings and
    generates Parquet for each activity, then writes the updated
    activities to ``job_dir/output/activities.json``.

    On failure writes ``job_dir/output/error.json`` so the caller can
    detect and report errors.

    Parameters
    ----------
    job_key : int
        Worker index (1-based).
    job_dir : pathlib.Path
        Sandbox directory for this job.
    """
    try:
        _polar_hrm_blob_job_impl(job_key, job_dir)
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


def _polar_hrm_blob_job_impl(job_key: int, job_dir: pathlib.Path) -> None:
    input_file = job_dir / "input" / "activities.json"
    if not input_file.exists():
        return

    with open(input_file) as fh:
        payload = json.load(fh)

    activities_data = payload.get("activities", [])
    if not activities_data:
        return

    user_id = payload.get("user_id", "")

    # create isolated blobstore inside the sandbox
    sandbox_config = mytral_config.MytralConfig(persistence_data_dir=job_dir / "work")
    sandbox_store = FilesystemBlobStore(
        base_dir=sandbox_config.user_data_dir,
        blobs_subdir="blobs",
    )

    now = datetime.datetime.now(datetime.timezone.utc).isoformat()

    for d in activities_data:
        raw_data = (d.get("transient_fields") or {}).get(
            polar_hrm.PolarHrmImportPlugin.KEY_POLAR_ROW_DATA, {}
        )
        hrm_path_str = raw_data.get(polar_hrm.PolarHrmImportPlugin.KEY_HRM_PATH)
        if not hrm_path_str:
            continue
        hrm_path = pathlib.Path(hrm_path_str)
        if not hrm_path.is_file():
            continue

        activity_key = d["key"]

        # read raw HRM bytes for the recording blob
        with hrm_path.open("rb") as fh:
            raw_bytes = fh.read()

        sha = hashlib.sha256(raw_bytes).hexdigest()

        rec_meta = _make_blob_metadata(
            user_id=user_id,
            activity_key=activity_key,
            kind=BlobKind.ACTIVITY_RECORDING.value,
            file_name="data.hrm",
            original_file_name=hrm_path.name,
            extension=".hrm",
            size_bytes=len(raw_bytes),
            sha256=sha,
            name="Polar HRM",
            description="Imported from Polar Precision Performance",
            keywords=["polar", "hrm"],
            created_at=now,
        )
        sandbox_store.create_blob(rec_meta, io.BytesIO(raw_bytes))

        # update activity recording reference in the dict
        recorded_keys = d.get("recorded_blob_keys") or []
        recorded_keys.append(f"{rec_meta.blob_key}.hrm")
        d["recorded_blob_keys"] = recorded_keys

        # parse HRM and generate parquet
        try:
            hrm_data = polar_hrm.parse_hrm(hrm_path)
        except Exception:
            continue

        if not hrm_data or not hrm_data.get("rows"):
            continue

        pq_bytes = parquet_converter.hrm_to_parquet(hrm_data)
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
            name="",
            description="",
            keywords=[],
            created_at=now,
        )
        sandbox_store.create_blob(pq_meta, io.BytesIO(pq_bytes))

        # update activity parquet reference in the dict
        recorded_pq = d.get("recorded_parquet_keys") or {}
        recorded_pq[rec_meta.blob_key] = pq_meta.blob_key
        d["recorded_parquet_keys"] = recorded_pq

    # write processed activities to output
    output_file = job_dir / "output" / "activities.json"
    with open(output_file, "w") as fh:
        json.dump(activities_data, fh)


class PolarHrmImportTask(tasks.TaskBase):
    """Import Polar Precision Performance activities."""

    TASK_TYPE = "polar_hrm_import"
    TASK_DISPLAY_NAME = "Polar Precision Performance Import"

    DATA_DIR_KEY = polar_hrm.POLAR_HRM_DATA_DIR_KEY

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

        self._log_name = "[Polar HRM import Task]"

    def execute(self) -> None:
        """Execute Polar HRM import using Bulldozer for parallel blob processing.

        Raises
        ------
        RuntimeError
            On unrecoverable failures.
        """

        params = self.task_entity.parameters
        user_id: str = params["user_id"]
        dataset_name: str = params["dataset_name"]
        data_dir_str: str = params[PolarHrmImportTask.DATA_DIR_KEY]
        on_conflict: str = params.get("on_conflict", "skip")

        self.log(
            f"Polar HRM import started (dir={data_dir_str}, on_conflict={on_conflict})"
        )
        self.update_progress(2)

        data_dir = pathlib.Path(data_dir_str)
        if not data_dir.is_dir():
            raise RuntimeError(f"Data directory not found: {data_dir}")

        # PHASE 0: clean up orphan blobs from previously crashed imports ----
        blob_svc = blob_svc_module.ActivityBlobService(
            store=self._blobstore,
            dataset=self._dataset,
            config=self._config,
        )
        try:
            removed = blob_svc.cleanup_orphan_recordings(user_id=user_id)
            if removed:
                self.log(
                    f"Cleaned up {removed} orphan blob directories from previous import"
                )
        except Exception as exc:
            app_logger.warning(
                f"{self._log_name} orphan blob cleanup failed: {exc}\n"
                f"{traceback.format_exc()}",
                user_id=user_id,
                error=str(exc),
                traceback=f"{traceback.format_exc()}",
            )

        # PHASE 1: parse + build activities via plugin
        plugin: polar_hrm.PolarHrmImportPlugin = plugins.registry.get_plugin(
            polar_hrm.PolarHrmImportPlugin.NAME
        )
        user_profile = self._dataset.profile(user_id)
        self.log("Parsing .pdd and .hrm files...")

        try:
            activities = plugin.import_activities(
                datasets={polar_hrm.POLAR_HRM_DATA_DIR_KEY: data_dir},
                user_profile=user_profile,
            )
        except Exception as exc:
            raise RuntimeError(f"Failed to parse Polar data: {exc}") from exc

        total = len(activities)
        self.log(f"Parsed {total} activities from {data_dir_str}")
        self.update_progress(10)
        self.check_cancellation()

        if total == 0:
            self.log("No activities found — import complete")
            self.update_progress(100)
            return

        # PHASE 2: Bulldozer-parallelized blob processing -------------------
        self.log("BEGIN: Uploading HRM blobs & generating parquet (parallel)...")

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

        # ensure we don't have more job dirs than chunks
        job_dirs = job_dirs[: len(chunks)]

        # write each chunk to its job input directory
        for i, chunk in enumerate(chunks):
            input_file = job_dirs[i] / "input" / "activities.json"
            with open(input_file, "w") as fh:
                json.dump(
                    {
                        "user_id": user_id,
                        "activities": [a.to_dict() for a in chunk],
                    },
                    fh,
                    cls=_PathEncoder,
                )

        self.log(
            f"Split {total} activities into {len(chunks)} chunks "
            f"({len(chunks)} workers)"
        )

        # run Bulldozer
        bzz.run(job_dirs=job_dirs, job_function=_polar_hrm_blob_job)

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
        self.update_progress(50)

        # PHASE 3: merge sandbox blobstores into main blobstore ------------
        # main blobstore uses base_dir=config.user_data_dir (= persistence_root/"data")
        main_blobs_dir = (
            persistence_root
            / mytral_config.MytralPersistenceFsConfig.DIR_DATA
            / user_id
            / "blobs"
        )
        sandbox_blobs_dirs = [_sandbox_blobs_dir(d, user_id) for d in job_dirs]
        merged = blob_svc_module.ActivityBlobService.merge_sandbox_blobstores(
            sandbox_blobs_dirs=sandbox_blobs_dirs,
            main_blobs_dir=main_blobs_dir,
        )
        self.log(f"Merged {merged} blob directories from sandboxes into main store")
        self.update_progress(60)

        # PHASE 4: collect activities, conflict-resolve, bulk persist -------
        self.log("Collecting activities from sandbox outputs...")

        # collect all processed activities from job outputs
        all_activities: list[entities.ActivityEntity] = []
        for job_dir in job_dirs:
            output_file = job_dir / "output" / "activities.json"
            if output_file.exists():
                with open(output_file) as fh:
                    chunk_data = json.load(fh)
                for d in chunk_data:
                    # strip transient_fields before reconstructing entity
                    d.pop("transient_fields", None)
                    all_activities.append(entities.ActivityEntity(**d))

        if len(all_activities) != total:
            self.log(
                f"WARNING: collected {len(all_activities)} activities, expected {total}"
            )

        # conflict detection and classification
        year_cache: dict[int, list] = {}
        activities_to_create: list[entities.ActivityEntity] = []
        activities_to_update: list[entities.ActivityEntity] = []
        imported = 0
        skipped = 0

        for activity in all_activities:
            existing_key = self._find_conflict(user_id, activity, year_cache)
            if existing_key:
                if on_conflict == "skip":
                    skipped += 1
                    continue
                if on_conflict == "override":
                    activity.key = existing_key
                else:
                    # new_key: keep newly generated key and create as new
                    existing_key = None

            entities.evaluate_activity(entity=activity, user_profile=user_profile)
            if not existing_key:
                activities_to_create.append(activity)
            else:
                activities_to_update.append(activity)
            imported += 1

        self.log(
            f"Conflict resolution: {imported} to import, "
            f"{skipped} skipped, "
            f"{len(activities_to_create)} to create, "
            f"{len(activities_to_update)} to update"
        )
        self.update_progress(70)

        # bulk persist
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
                entity_list=activities_to_update,
            )
            raise NotImplementedError

        self.log("DONE: activities persisted & parquets created & HRM blobs uploaded")
        self.log(f"Polar HRM import complete: {imported} imported, {skipped} skipped")
        self.update_progress(100)

    def _find_conflict(
        self, user_id: str, activity, year_cache: dict[int, list]
    ) -> str | None:
        """Return the key of an existing conflicting activity or None.

        Uses ``src`` + ``src_key`` matching for Polar-sourced activities.
        The ``year_cache`` dict is populated lazily on first access per year,
        eliminating repeated ``list_activities()`` JSON reads.

        Parameters
        ----------
        user_id : str
            User identifier.
        activity :
            Activity to check against existing records.
        year_cache : dict[int, list]
            Mutable cache mapping ``when_year`` to existing activity list;
            populated on demand and reused across calls.

        Returns
        -------
        str or None
            Existing activity key if a conflict is found, else None.
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


tasks.tasks_registry.register_task(PolarHrmImportTask)
