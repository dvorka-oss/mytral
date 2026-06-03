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
"""Async task: import a TCX recording file and attach it to an activity."""

import traceback

from mytral import tasks
from mytral.blobstore import activity_service as blob_svc_module
from mytral.integrations import tcx_recording
from mytral.recordings import parquet_converter
from mytral.recordings import tcx_extractor


class TcxImportTask(tasks.TaskBase):
    """Attach a TCX file blob to an activity and convert it to Parquet."""

    TASK_TYPE = "tcx_import"
    TASK_DISPLAY_NAME = "TCX Recording Import"

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
        """Execute TCX import task."""
        params = self.task_entity.parameters
        user_id: str = params["user_id"]
        dataset_name: str = params["dataset_name"]
        activity_key: str = params["activity_key"]
        source_blob_uuid: str = params.get("source_blob_uuid") or params.get("blob_key")
        if not source_blob_uuid:
            raise RuntimeError("Missing source_blob_uuid in task parameters")
        extract_summary: bool = bool(params.get("extract_summary", False))

        self.log(
            f"TCX import of its blob {source_blob_uuid} ...",
            user=user_id,
            activity=activity_key,
            blob=source_blob_uuid,
        )
        self.update_progress(5)
        self.check_cancellation()

        blob_svc = blob_svc_module.ActivityBlobService(
            store=self._blobstore,
            dataset=self._dataset,
            config=self._config,
        )

        try:
            result = blob_svc.open_recording(user_id, activity_key, source_blob_uuid)
            stream, _ = result
            try:
                tcx_data = stream.read()
            finally:
                stream.close()
        except Exception as exc:
            raise RuntimeError(
                f"Failed to read TCX blob {source_blob_uuid}: {exc}"
            ) from exc

        self.update_progress(20)
        self.check_cancellation()

        try:
            parquet_bytes = parquet_converter.tcx_to_parquet(tcx_data)
            blob_svc.save_parquet(
                user_id=user_id,
                activity_key=activity_key,
                source_blob_key=source_blob_uuid,
                parquet_data=parquet_bytes,
            )
            self.log(f"Parquet saved for blob {source_blob_uuid}")
        except Exception as exc:
            self.log(
                f"WARNING: Parquet conversion failed: {exc}\n{traceback.format_exc()}"
            )

        self.update_progress(60)
        self.check_cancellation()

        if extract_summary:
            try:
                summary = tcx_extractor.extract_tcx_summary(tcx_data)
                activity = self._dataset.get_activity(
                    user_id=user_id,
                    dataset_name=dataset_name,
                    key=activity_key,
                )
                if activity is not None and summary is not None:
                    tcx_recording.apply_tcx_summary(activity, summary)
                    self._dataset.update_activity(
                        user_id=user_id,
                        dataset_name=dataset_name,
                        entity=activity,
                    )
                    self.log("Summary fields updated from TCX")
            except Exception as exc:
                self.log(
                    f"WARNING: Summary extraction failed: {exc}\n"
                    f"{traceback.format_exc()}",
                    traceback=traceback.format_exc(),
                )

        self.update_progress(85)
        self.check_cancellation()

        try:
            blob_svc.ensure_gpx_map_data(
                user_id=user_id,
                activity_key=activity_key,
                blob_key=source_blob_uuid,
            )
            self.log("Map data generated")
        except Exception as exc:
            self.log(
                f"WARNING: Map data generation failed: {exc}\n{traceback.format_exc()}",
            )

        self.update_progress(100)
        self.log("TCX import complete")


tasks.tasks_registry.register_task(TcxImportTask)
