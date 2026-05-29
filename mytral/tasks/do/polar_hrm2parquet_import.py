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

"""Async task: convert an already-imported Polar HRM activity set to Parquet.

This task post-processes existing Polar HRM import results by converting
parsed HRM data dicts to Parquet blobs via hrm_to_parquet().
"""

from mytral import tasks
from mytral.blobstore import activity_service as blob_svc_module
from mytral.recordings import parquet_converter


class PolarHrm2ParquetImportTask(tasks.TaskBase):
    """Convert parsed Polar HRM data to Parquet for a set of activities.

    This task expects that activities already exist in the dataset and that
    the ``hrm_data`` dicts (as produced by ``polar_hrm.parse_hrm()``) are
    available via the task parameters.

    Parameters are provided via ``task_entity.parameters``:

    - ``user_id`` (str): owning user identifier
    - ``activity_keys`` (list[str]): activity keys to process
    - ``hrm_data_map`` (dict[str, dict]): maps activity_key → hrm_data dict
    """

    TASK_TYPE = "polar_hrm2parquet_import"
    TASK_DISPLAY_NAME = "Polar HRM → Parquet"

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
        """Execute Polar HRM → Parquet conversion task.

        Raises
        ------
        RuntimeError
            On unrecoverable failures.
        """
        params = self.task_entity.parameters
        user_id: str = params["user_id"]
        activity_keys: list[str] = params.get("activity_keys", [])
        hrm_data_map: dict[str, dict] = params.get("hrm_data_map", {})

        self.log(
            f"Polar HRM → Parquet: user={user_id}, activities={len(activity_keys)}"
        )
        self.update_progress(5)
        self.check_cancellation()

        blob_svc = blob_svc_module.ActivityBlobService(
            store=self._blobstore,
            dataset=self._dataset,
            config=self._config,
        )

        total = len(activity_keys)
        if total == 0:
            self.update_progress(100)
            self.log("No activities to process")
            return

        success = 0
        failed = 0

        for i, activity_key in enumerate(activity_keys):
            self.check_cancellation()
            hrm_data = hrm_data_map.get(activity_key)
            if not hrm_data:
                self.log(f"No HRM data for {activity_key}, skipping")
                continue

            try:
                parquet_bytes = parquet_converter.hrm_to_parquet(hrm_data)
                # store the parquet blob; use activity_key as a surrogate source key
                # since HRM activities don't have a recording blob UUID
                blob_svc.save_parquet(
                    user_id=user_id,
                    activity_key=activity_key,
                    source_blob_key=activity_key,
                    parquet_data=parquet_bytes,
                )
                success += 1
                self.log(f"Parquet saved for activity {activity_key}")
            except Exception as exc:
                self.log(f"WARNING: Failed for {activity_key}: {exc}")
                failed += 1

            self.update_progress(5 + int(90 * (i + 1) / total))

        self.update_progress(100)
        self.log(
            f"HRM > Parquet complete: {success} converted, "
            f"{failed} failed out of {total}"
        )


tasks.tasks_registry.register_task(PolarHrm2ParquetImportTask)
