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
"""Async task: import a GPX recording file and attach it to an activity."""

from mytral import tasks
from mytral.blobstore import activity_service as blob_svc_module
from mytral.integrations import gpx_recording


class GpxImportTask(tasks.TaskBase):
    """Attach a GPX file blob to an activity and convert it to Parquet.

    Parameters are provided via ``task_entity.parameters``:

    - ``user_id`` (str): owning user identifier
    - ``activity_key`` (str): target activity key
    - ``source_blob_uuid`` (str): blob UUID of the already-uploaded GPX recording
    - ``blob_key`` (str, optional): backward-compatible alias for source_blob_uuid
    - ``extract_summary`` (bool, optional): update activity fields from GPX track
    """

    TASK_TYPE = "gpx_import"
    TASK_DISPLAY_NAME = "GPX Recording Import"

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
        """Execute GPX import task.

        Raises
        ------
        RuntimeError
            On unrecoverable failures.
        """
        params = self.task_entity.parameters
        user_id: str = params["user_id"]
        dataset_name: str = params["dataset_name"]
        activity_key: str = params["activity_key"]
        source_blob_uuid: str = params.get("source_blob_uuid") or params.get("blob_key")
        if not source_blob_uuid:
            raise RuntimeError("Missing source_blob_uuid in task parameters")
        extract_summary: bool = bool(params.get("extract_summary", False))

        self.log(
            "GPX import: "
            f"user={user_id}, activity={activity_key}, blob={source_blob_uuid}"
        )
        self.update_progress(5)
        self.check_cancellation()

        blob_svc = blob_svc_module.ActivityBlobService(
            store=self._blobstore,
            dataset=self._dataset,
            config=self._config,
        )

        # read GPX bytes from blobstore
        try:
            result = blob_svc.open_recording(user_id, activity_key, source_blob_uuid)
            stream, meta = result
            try:
                gpx_data = stream.read()
            finally:
                stream.close()
        except Exception as exc:
            raise RuntimeError(
                f"Failed to read GPX blob {source_blob_uuid}: {exc}"
            ) from exc

        self.update_progress(20)
        self.check_cancellation()

        def _persist_summary(summary) -> None:
            activity = self._dataset.get_activity(user_id, dataset_name, activity_key)
            if activity is None:
                raise RuntimeError(
                    f"Activity {activity_key} not found in dataset {dataset_name}"
                )
            gpx_recording.apply_gpx_summary(activity, summary)
            self._dataset.update_activity(
                user_id=user_id,
                dataset_name=dataset_name,
                entity=activity,
            )

        gpx_recording.import_gpx_recording_bytes(
            user_id=user_id,
            activity_key=activity_key,
            gpx_data=gpx_data,
            original_filename=meta.original_file_name
            or meta.file_name
            or (f"{source_blob_uuid}.gpx"),
            blob_svc=blob_svc,
            extract_summary=extract_summary,
            summary_handler=_persist_summary if extract_summary else None,
            log=self.logger,
        )

        self.update_progress(100)
        self.log("GPX import complete")


tasks.tasks_registry.register_task(GpxImportTask)
