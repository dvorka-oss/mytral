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

"""Async task: reprocess all recording blobs for an activity into Parquet."""

import traceback

from mytral import commons
from mytral import tasks
from mytral.backends import entities as backend_entities
from mytral.blobstore import activity_service as blob_svc_module
from mytral.integrations import polar_hrm
from mytral.recordings import parquet_converter


class RecordingReprocessTask(tasks.TaskBase):
    """Reprocess all recording blobs for a single activity into fresh Parquet.

    Useful when the Parquet schema changes or conversion logic is updated.

    Parameters are provided via ``task_entity.parameters``:

    - ``user_id`` (str): owning user identifier
    - ``activity_key`` (str): target activity key
    - ``source_blob_uuid`` (str, optional): specific recording blob UUID to reprocess
    - ``blob_key`` (str, optional): backward-compatible alias for source_blob_uuid
    """

    TASK_TYPE = "recording_reprocess"
    TASK_DISPLAY_NAME = "Recording Reprocess"

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
        """Execute recording reprocess task.

        Raises
        ------
        RuntimeError
            On unrecoverable failures.
        """
        try:
            params = self.task_entity.parameters
            user_id: str = params["user_id"]
            activity_key: str = params["activity_key"]
            dataset_name: str = params.get("dataset_name", commons.DS_LIFELONG)
            requested_blob_key: str = params.get("source_blob_uuid") or params.get(
                "blob_key", ""
            )

            self.log(f"Recording reprocess: user={user_id}, activity={activity_key}")
            self.update_progress(5)
            self.check_cancellation()

            blob_svc = blob_svc_module.ActivityBlobService(
                store=self._blobstore,
                dataset=self._dataset,
                config=self._config,
            )

            try:
                activity = self._dataset.get_activity(
                    user_id=user_id, dataset_name=dataset_name, key=activity_key
                )
            except (ValueError, KeyError) as exc:
                raise RuntimeError(f"Activity not found: {activity_key}") from exc

            entries: list[str] = activity.recorded_blob_keys
            if requested_blob_key:
                entries = [
                    entry
                    for entry in entries
                    if backend_entities.recording_blob_uuid(entry) == requested_blob_key
                ]
            total = len(entries)
            self.log(f"Found {total} recording(s) to reprocess")

            if total == 0:
                self.update_progress(100)
                self.log("Nothing to reprocess")
                return

            success = 0
            failed = 0

            for i, entry in enumerate(entries):
                self.check_cancellation()
                blob_key = backend_entities.recording_blob_uuid(entry)
                ext = backend_entities.recording_ext(entry)

                try:
                    result = blob_svc.open_recording(user_id, activity_key, blob_key)
                    stream, _meta = result
                    data = stream.read()
                except Exception as exc:
                    self.log(f"WARNING: Cannot read blob {blob_key}: {exc}")
                    failed += 1
                    continue

                try:
                    if ext == ".fit":
                        parquet_bytes = parquet_converter.fit_to_parquet(data)
                    elif ext == ".gpx":
                        parquet_bytes = parquet_converter.gpx_to_parquet(data)
                    elif ext == ".hrm":
                        hrm_dict = polar_hrm.parse_hrm(data.decode("utf-8", "ignore"))
                        parquet_bytes = parquet_converter.hrm_to_parquet(hrm_dict)
                    else:
                        self.log(
                            f"Unknown extension '{ext}' for blob {blob_key}, skipping"
                        )
                        continue

                    blob_svc.save_parquet(
                        user_id=user_id,
                        activity_key=activity_key,
                        source_blob_key=blob_key,
                        parquet_data=parquet_bytes,
                    )
                    success += 1
                    self.log(f"Reprocessed {blob_key} ({ext})")
                except Exception as exc:
                    self.log(f"WARNING: Conversion failed for {blob_key}: {exc}")
                    failed += 1

                self.update_progress(5 + int(90 * (i + 1) / total))

            self.update_progress(100)
            self.log(
                f"Reprocess complete: {success} converted, "
                f"{failed} failed out of {total}"
            )
        except Exception as ex:
            self.logger.error(
                f"Recording process task failed: {ex}", traceback=traceback.format_exc()
            )
            raise


tasks.tasks_registry.register_task(RecordingReprocessTask)
