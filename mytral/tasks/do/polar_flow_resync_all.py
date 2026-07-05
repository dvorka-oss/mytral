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

"""Polar Flow re-sync all task - purges all Polar Flow activities then re-pulls.

NOTE: the AccessLink API cannot backfill history - a re-pull after a purge only serves
exercises still within Polar's retention window (uncommitted / recent). A full
historical re-seed must come from the GDPR export ZIP (see PolarFlowExportImportTask).
"""

from mytral import commons
from mytral import tasks
from mytral.backends.datasets import dataset_json as dataset_json_module
from mytral.blobstore import activity_service as blob_svc_module
from mytral.integrations import polar_flow
from mytral.tasks.do import polar_flow_commons


class PolarFlowResyncAllTask(tasks.TaskBase):
    """Purges all Polar-Flow-sourced activities from all datasets, then re-pulls.

    IMPORTANT: requires params["purge_confirmed"] == True as a safety guard.
    Activities with src == "polar-flow" are deleted from all year datasets and the
    lifelong (aggregation) dataset. Gear is never deleted.
    """

    TASK_TYPE = "polar_flow_resync_all"
    TASK_DISPLAY_NAME = "Polar Flow - Re-sync All Activities"
    ENCRYPTED_PARAM_KEYS = ["access_token"]

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
        """Execute full re-sync: purge all Polar Flow activities then re-pull."""
        params = self.task_entity.parameters
        user_id = params["user_id"]
        dataset_name = params["dataset_name"]
        import_recordings = polar_flow_commons.to_bool(
            params.get("import_recordings", True)
        )

        if not params.get("purge_confirmed"):
            raise ValueError(
                "Re-sync requires explicit confirmation (purge_confirmed=True). "
                "Aborting to prevent accidental data loss."
            )

        self.log(
            "Polar Flow re-sync started: purging all Polar-Flow-sourced activities "
            "from all datasets"
        )
        self.check_cancellation()

        user_dir = self._dataset.user_dir(user_id=user_id)
        year_ds_names = dataset_json_module.list_activity_year_dataset_names(user_dir)
        all_ds_names = list(year_ds_names)
        if commons.DS_LIFELONG not in all_ds_names:
            all_ds_names.append(commons.DS_LIFELONG)

        blob_svc = blob_svc_module.ActivityBlobService(
            store=self._blobstore,
            dataset=self._dataset,
            config=self._config,
        )
        total_deleted = 0
        for ds_name in all_ds_names:
            self.check_cancellation()
            try:
                activities = self._dataset.all_activities(user_id, ds_name)
                polar_keys = [
                    key
                    for key, act in activities.items()
                    if act.src == polar_flow.SRC_POLAR_FLOW
                ]
                for i, key in enumerate(polar_keys):
                    if i % 10 == 0:
                        self.check_cancellation()
                    try:
                        blob_svc.delete_all_activity_blobs(
                            user_id=user_id, activity_key=key
                        )
                    except Exception as exc:
                        self.log(f"  Warning: failed to delete blobs for {key}: {exc}")
                    self._dataset.delete_activity(
                        user_id=user_id, dataset_name=ds_name, key=key
                    )
                    total_deleted += 1
                self.log(f"Dataset '{ds_name}': deleted {len(polar_keys)} activities")
            except Exception as exc:
                self.log(f"Warning: error purging dataset '{ds_name}': {exc}")

        self.log(f"Purge complete: {total_deleted} Polar Flow activities deleted")
        self.update_progress(10)

        try:
            self._dataset.cache_evict(user_id)
        except Exception as exc:
            self.log(f"Cache eviction warning (non-fatal): {exc}")

        self.log("Re-pulling new exercises from Polar AccessLink...")
        creds = polar_flow_commons.build_polar_credentials(params, self._enc_key)
        polar_flow_commons.pull_new_exercises(
            creds,
            dataset=self._dataset,
            blobstore=self._blobstore,
            config=self._config,
            user_id=user_id,
            dataset_name=dataset_name,
            import_recordings=import_recordings,
            log_fn=self.log,
            logger=self.logger,
            check_cancellation=self.check_cancellation,
            update_progress=self.update_progress,
        )


tasks.tasks_registry.register_task(PolarFlowResyncAllTask)
