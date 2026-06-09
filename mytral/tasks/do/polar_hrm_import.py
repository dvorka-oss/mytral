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
 1. BLOB store initialization & orphans cleanup (remind that it's async)
 2. Create activities from .hrm/.pdd files:
    PolarHrmImportPlugin.import_activities()
      1) save ALL activities at ONCE (1 JSON save)
 3. Attach BLOBs to activities:
    for a in activities:
      1) find BLOB
      2) attach BLOB
      3) save activity (1000s of JSON saves)

"""

import io
import pathlib
import traceback

from mytral import app_logger
from mytral import plugins
from mytral import tasks
from mytral.blobstore import activity_service as blob_svc_module
from mytral.integrations import polar_hrm
from mytral.recordings import parquet_converter


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
        """Execute Polar HRM import.

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
            # import .hrm to activities in MEMORY (JSON not saved)
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

        # PHASE 2: upload blobs then persist activities using SINGLE JSON write
        imported = 0
        skipped = 0
        failed = 0

        # year_cache:
        # - lazy per-year list of existing activities:
        #   eliminates O(n) list_activities() JSON reads (loaded once per unique year)
        year_cache: dict[int, list] = {}

        self.log("BEGIN: Uploading HRM blobs & persisting activities & parquet...")
        # gather activities to update & create to do 2x JSON writes instead 1000s
        activities_to_create = []
        activities_to_update = []
        for i, activity in enumerate(activities):
            self.check_cancellation()

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

            # STEP 1: upload blobs (activity updated in-memory only, no disk write)
            try:
                self._attach_hrm_recording_and_parquet(
                    plugin=plugin,
                    blob_svc=blob_svc,
                    user_id=user_id,
                    activity=activity,
                    hrm_data=plugin._hrm_data_cache.get(activity.src_key),
                )
            except Exception as exc:
                app_logger.warning(
                    f"{self._log_name} HRM attachment lookup failed: {exc}"
                    f"\n{traceback.format_exc()}",
                    key=activity.key,
                    hrm=activity.src_key,
                    error=str(exc),
                    traceback=f"{traceback.format_exc()}",
                )

            # STEP 2: schedule persist activity
            if not existing_key:
                activities_to_create.append(activity)
            else:
                activities_to_update.append(activity)

            # # TODO change this to BULK create + BULK update - keep them in memory,
            # #   do not save them in cycle
            # try:
            #     if not existing_key:
            #         self._dataset.create_activity(
            #             user_id=user_id,
            #             dataset_name=dataset_name,
            #             entity=activity,
            #         )
            #     else:
            #         self._dataset.update_activity(
            #             user_id=user_id,
            #             dataset_name=dataset_name,
            #             entity=activity,
            #         )
            # except Exception as exc:
            #     # clean up uploaded blobs since the activity persist failed
            #     if rec_key:
            #         try:
            #             blob_svc._store.delete_blob(user_id, rec_key)
            #         except Exception:
            #             pass
            #     if pq_key:
            #         try:
            #             blob_svc._store.delete_blob(user_id, pq_key)
            #         except Exception:
            #             pass
            #     app_logger.warning(
            #         "PolarHrmImportTask: create/update activity failed",
            #         key=activity.key,
            #         error=str(exc),
            #     )
            #     failed += 1
            #     continue

            imported += 1
            progress = 10 + int(88 * (i + 1) / total)
            self.update_progress(progress)
            self.log(
                f"Progress: {i + 1}/{total} processed "
                f"(imported={imported}, skipped={skipped}, failed={failed})"
            )

        # DO bulk create & update of activities
        if activities_to_create:
            self._dataset.create_activities(
                user_id=user_id,
                dataset_name=dataset_name,
                entity_list=activities_to_create,
            )
        if activities_to_update:
            # TODO to be implemented
            # TODO to be implemented
            # TODO to be implemented
            self._dataset.update_activities(
                user_id=user_id,
                dataset_name=dataset_name,
                entity_list=activities_to_update,
            )
            raise NotImplementedError

        self.log("DONE: activities persisted & parquets created & HRM blobs uploaded")
        self.log(
            f"Polar HRM import complete: {imported} imported, "
            f"{skipped} skipped, {failed} failed"
        )
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

    # @staticmethod
    # def _discover_hrm_paths(data_dir: pathlib.Path) -> dict[str, pathlib.Path]:
    #     """Discover HRM files and map base filename to full path:
    #
    #     - HRM files are in directory: ${PPP}/[user ID]/[year]/*.hrm
    #     - HRM file names are unique
    #
    #     """
    #     mapping: dict[str, pathlib.Path] = {}
    #     for path in data_dir.rglob("*"):
    #         if not path.is_file():
    #             continue
    #         if path.suffix.lower() != ".hrm":
    #             continue
    #         mapping[path.name] = path
    #     return mapping

    def _attach_hrm_recording_and_parquet(
        self,
        plugin,
        blob_svc,
        user_id: str,
        activity,
        hrm_data: dict | None,
    ) -> tuple[str | None, str | None]:
        """Upload raw HRM recording, generate Parquet, update activity in-memory.

        Both blob operations use ``skip_persist=True`` — the caller is
        responsible for persisting the activity to disk afterwards.

        Parameters
        ----------
        blob_svc : ActivityBlobService
            Blob service for recording/parquet operations.
        user_id : str
            User identifier.
        activity : ActivityEntity
            Activity to enrich with recording references (mutated in-place).
        hrm_data : dict or None
            Parsed HRM structure from plugin cache.

        Returns
        -------
        tuple[str | None, str | None]
            (recording_blob_key, parquet_blob_key) — so the caller can
            clean up blobs if the subsequent activity persist fails.
        """
        self.log(
            f"Attaching HRM recording for activity {activity.key} "
            f"(src_key={activity.src_key})"
        )

        hrm_path = activity.transient_fields.get(plugin.KEY_POLAR_ROW_DATA, {}).get(
            plugin.KEY_HRM_PATH
        )
        if hrm_path is None or not hrm_path.is_file():
            self.log(
                "WARNING: HRM file not found for activity "
                f"{activity.key}: {activity.src_key}"
            )
            return None, None
        if not hrm_data or not hrm_data.get("rows"):
            self.log(
                f"WARNING: HRM parsed data missing for activity {activity.key}: "
                f"{activity.src_key}"
            )
            return None, None

        with hrm_path.open("rb") as fh:
            raw_bytes = fh.read()

        recording_meta = blob_svc.upload_recording(
            user_id=user_id,
            activity_key=activity.key,
            uploaded_file=io.BytesIO(raw_bytes),
            original_filename=hrm_path.name,
            content_type="application/octet-stream",
            name="Polar HRM",
            description="Imported from Polar Precision Performance",
            keywords="polar,hrm",
            activity=activity,
            skip_persist=True,
        )
        recording_blob_key = recording_meta.blob_key

        parquet_bytes = parquet_converter.hrm_to_parquet(hrm_data)
        parquet_blob_key = blob_svc.save_parquet(
            user_id=user_id,
            activity_key=activity.key,
            source_blob_key=recording_meta.blob_key,
            parquet_data=parquet_bytes,
            activity=activity,
            skip_persist=True,
        )

        return recording_blob_key, parquet_blob_key


tasks.tasks_registry.register_task(PolarHrmImportTask)
