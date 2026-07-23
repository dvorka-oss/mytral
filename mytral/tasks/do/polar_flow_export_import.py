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

"""Polar Flow GDPR-export import task - backfills history from the export ZIP."""

import io

from mytral import config as mytral_config
from mytral import plugins
from mytral import tasks
from mytral.blobstore import activity_service as blob_svc_module
from mytral.integrations import polar_flow
from mytral.integrations import polar_flow_export
from mytral.integrations import polar_flow_recording
from mytral.tasks.do import polar_flow_commons
from mytral.tasks.do import recording_maps

ON_CONFLICT_SKIP = "skip"
ON_CONFLICT_OVERRIDE = "override"
ON_CONFLICT_NEW_KEY = "new_key"


class PolarFlowExportImportTask(tasks.TaskBase):
    """Imports historical activities from a Polar Flow "Download your data" ZIP.

    Parameters (via task_entity.parameters):

    - user_id: str
    - dataset_name: str  (target dataset)
    - zip_path: str  (path to the uploaded export ZIP)
    - on_conflict: str  (skip | override | new_key)
    """

    TASK_TYPE = "polar_flow_export_import"
    TASK_DISPLAY_NAME = "Polar Flow - Historical Export Import"
    ENCRYPTED_PARAM_KEYS: list[str] = []

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
        """Parse the export ZIP and import its training sessions and recordings."""
        params = self.task_entity.parameters
        user_id = params["user_id"]
        dataset_name = params["dataset_name"]
        zip_path = params["zip_path"]
        on_conflict = params.get("on_conflict", ON_CONFLICT_SKIP)

        self.log(f"Polar Flow export import started (zip={zip_path})")
        self.check_cancellation()

        summaries = polar_flow_export.parse_export(zip_path)
        total = len(summaries)
        self.log(f"Parsed {total} training session(s) from the export")
        if not summaries:
            self.update_progress(100)
            return

        self.update_progress(10)
        recorded_targets = self._import_summaries(
            summaries=summaries,
            user_id=user_id,
            dataset_name=dataset_name,
            on_conflict=on_conflict,
        )
        self._dataset.cache_evict(user_id)

        recorded = self._import_recordings(
            zip_path=zip_path,
            user_id=user_id,
            dataset_name=dataset_name,
            recorded_targets=recorded_targets,
        )
        self._dataset.cache_evict(user_id)

        # precompute GPS maps so the activity feed does not lazily block on them
        if recorded:
            self.update_progress(90)
            recording_maps.precompute_maps(
                user_id=user_id,
                activities=recorded,
                blob_svc=blob_svc_module.ActivityBlobService(
                    store=self._blobstore, dataset=self._dataset, config=self._config
                ),
                usr_task_dir=self._task_dir(user_id),
                config=self._config,
                logger=self.logger,
                log=self.log,
                check_cancellation=self.check_cancellation,
            )
        self.update_progress(100)

    def _task_dir(self, user_id: str):
        """Return this task's directory (the bulldozer sandbox root)."""
        return (
            self._config.persistence_data_dir
            / mytral_config.MytralPersistenceFsConfig.DIR_DATA
            / user_id
            / mytral_config.MytralPersistenceFsConfig.DIR_TASKS
            / f"task-{self.task_entity.key}"
        )

    def _import_summaries(
        self, *, summaries, user_id: str, dataset_name: str, on_conflict: str
    ) -> dict:
        """Persist activity summaries; return {src_key: activity} for imported ones."""
        plugin = plugins.registry.get_plugin(
            polar_flow.PolarFlowActivitiesImportPlugin.NAME
        )
        user_profile = self._dataset.profile(user_id)
        activities = plugin.import_activities(
            datasets={plugin.USE_TYPE_POLAR_FLOW_LIST: summaries},
            user_profile=user_profile,
        )

        total = len(activities)
        self.log(f"Importing {total} activities...")
        log_step = max(1, total // 10)
        imported = skipped = overridden = 0
        recorded_targets: dict = {}
        for i, activity in enumerate(activities):
            self.check_cancellation()
            if (i + 1) % log_step == 0 or i + 1 == total:
                self.log(f"  activities: {i + 1}/{total} processed")
            existing_key = polar_flow_commons.find_existing_polar_flow_activity(
                dataset=self._dataset,
                user_id=user_id,
                dataset_name=dataset_name,
                candidate=activity,
            )
            if existing_key and on_conflict == ON_CONFLICT_SKIP:
                skipped += 1
                continue
            if existing_key and on_conflict == ON_CONFLICT_OVERRIDE:
                activity.key = existing_key
                self._dataset.update_activity(
                    user_id=user_id, dataset_name=dataset_name, entity=activity
                )
                overridden += 1
            else:
                # no conflict, or on_conflict == new_key: create fresh
                self._dataset.create_activity(
                    user_id=user_id, dataset_name=dataset_name, entity=activity
                )
                imported += 1
            # only imported/overridden activities receive a recording
            if activity.src_key:
                recorded_targets[activity.src_key] = activity
            if total:
                self.update_progress(10 + int(50 * (i + 1) / total))

        self.log(
            f"Activities imported: {imported} new, {overridden} overridden, "
            f"{skipped} skipped (duplicates)"
        )
        return recorded_targets

    def _import_recordings(
        self, *, zip_path: str, user_id: str, dataset_name: str, recorded_targets: dict
    ) -> list:
        """Attach a recording (per-second charts) to each activity; return them.

        Artifacts are built directly from the session samples (no XML re-parse) and
        the owning activities are persisted once at the end (no per-recording cache
        churn), so the recording phase stays fast on large archives.
        """
        if not recorded_targets:
            return []

        blob_svc = blob_svc_module.ActivityBlobService(
            store=self._blobstore, dataset=self._dataset, config=self._config
        )
        target_count = len(recorded_targets)
        self.log(f"Building per-second recordings for {target_count} activities...")
        log_step = max(1, target_count // 10)
        recorded: list = []
        processed = 0
        for session in polar_flow_export.iter_sessions(zip_path):
            self.check_cancellation()
            for summary in polar_flow_export.normalize_session(session):
                activity = recorded_targets.get(summary["id"])
                if activity is None:
                    continue
                processed += 1
                # progress across the recording phase spans 60% -> 88%
                self.update_progress(60 + int(28 * processed / target_count))
                if processed % log_step == 0 or processed == target_count:
                    self.log(f"  recordings: {processed}/{target_count} built")
                artifacts = polar_flow_recording.build_recording(session)
                if artifacts is None:
                    continue
                self._store_recording(
                    blob_svc, user_id, activity, summary["id"], artifacts
                )
                recorded.append(activity)

        if recorded:
            self._dataset.update_activities(
                user_id=user_id, dataset_name=dataset_name, activities=recorded
            )
        self.log(f"Recordings imported: {len(recorded)} (per-second charts)")
        return recorded

    def _store_recording(self, blob_svc, user_id, activity, src_key, artifacts) -> None:
        """Persist one recording's TCX source and chart Parquet (deferred save).

        The GPS map is precomputed from the stored TCX in a later parallel phase.
        """
        meta = blob_svc.upload_recording(
            user_id=user_id,
            activity_key=activity.key,
            uploaded_file=io.BytesIO(artifacts.tcx_bytes),
            original_filename=f"polar-flow-{src_key}.tcx",
            content_type="application/vnd.garmin.tcx+xml",
            activity=activity,
            skip_persist=True,
        )
        blob_svc.save_parquet(
            user_id=user_id,
            activity_key=activity.key,
            source_blob_key=meta.blob_key,
            parquet_data=artifacts.parquet_bytes,
            activity=activity,
            skip_persist=True,
        )


tasks.tasks_registry.register_task(PolarFlowExportImportTask)
