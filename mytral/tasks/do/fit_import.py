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
"""Async task: import a FIT recording file and attach it to an activity."""

import copy
import traceback

from mytral import tasks
from mytral.backends import entities
from mytral.blobstore import activity_service as blob_svc_module
from mytral.recordings import fit_extractor
from mytral.recordings import parquet_converter


class FitImportTask(tasks.TaskBase):
    """Attach a FIT file blob to an activity and convert it to Parquet.

    Parameters are provided via ``task_entity.parameters``:

    - ``user_id`` (str): owning user identifier
    - ``activity_key`` (str): target activity key
    - ``source_blob_uuid`` (str): blob UUID of the already-uploaded FIT recording
    - ``blob_key`` (str, optional): backward-compatible alias for source_blob_uuid
    - ``extract_summary`` (bool, optional): update activity fields from session
    """

    TASK_TYPE = "fit_import"
    TASK_DISPLAY_NAME = "FIT Recording Import"

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
        """Execute FIT import task.

        Raises
        ------
        RuntimeError
            On unrecoverable failures.
        """
        try:
            params = self.task_entity.parameters
            user_id: str = params["user_id"]
            dataset_name: str = params["dataset_name"]
            activity_key: str = params["activity_key"]
            source_blob_uuid: str = params.get("source_blob_uuid") or params.get(
                "blob_key"
            )
            if not source_blob_uuid:
                raise RuntimeError("Missing source_blob_uuid in task parameters")
            extract_summary: bool = bool(params.get("extract_summary", False))

            self.log(
                f"FIT import: {activity_key=}",
                user={user_id},
                activity={activity_key},
                blob={source_blob_uuid},
            )
            self.update_progress(5)
            self.check_cancellation()

            blob_svc = blob_svc_module.ActivityBlobService(
                store=self._blobstore,
                dataset=self._dataset,
                config=self._config,
            )

            # read FIT bytes from blobstore
            try:
                result = blob_svc.open_recording(
                    user_id, activity_key, source_blob_uuid
                )
                stream, _meta = result
                fit_data = stream.read()
            except Exception as exc:
                raise RuntimeError(
                    f"Failed to read FIT blob {source_blob_uuid}: {exc}"
                ) from exc

            self.update_progress(20)
            self.check_cancellation()

            # convert to parquet
            try:
                parquet_bytes = parquet_converter.fit_to_parquet(fit_data)
                blob_svc.save_parquet(
                    user_id=user_id,
                    activity_key=activity_key,
                    source_blob_key=source_blob_uuid,
                    parquet_data=parquet_bytes,
                )
                self.log(f"Parquet saved for blob {source_blob_uuid}")
            except Exception as exc:
                self.log(
                    f"WARNING: Parquet conversion failed: {exc}"
                    f"\n{traceback.format_exc()}"
                )

            self.update_progress(60)
            self.check_cancellation()

            # optional summary extraction
            if extract_summary:
                try:
                    summary = fit_extractor.extract_fit_summary(fit_data)
                    activity = self._dataset.get_activity(
                        user_id=user_id, dataset_name=dataset_name, key=activity_key
                    )
                    if activity is not None and summary is not None:
                        activity_to_save = copy.deepcopy(activity)
                        _apply_fit_summary(activity=activity_to_save, summary=summary)
                        self._dataset.update_activity(
                            user_id=user_id,
                            dataset_name=dataset_name,
                            entity=activity_to_save,
                        )
                        self.log("Summary fields updated from FIT session message")
                except Exception as exc:
                    self.log(
                        f"WARNING: Summary extraction failed: {exc}\n"
                        f"{traceback.format_exc()}",
                        traceback=traceback.format_exc(),
                    )

            self.update_progress(100)
            self.log("FIT import complete")
        except Exception as exc:
            self.log(f"WARNING: FIT conversion failed: {exc}\n{traceback.format_exc()}")
            raise


def _apply_fit_summary(activity, summary) -> None:
    """Write non-None RecordingSummary fields into *activity* in-place.

    Parameters
    ----------
    activity :
        ActivityEntity to update.
    summary :
        RecordingSummary instance.
    """
    if summary.activity_type_key and not activity.activity_type_key:
        activity.activity_type_key = summary.activity_type_key
    if summary.when:
        # always apply the FIT timestamp - it is always more accurate than the
        # "now" placeholder set by ActivityEntity.__post_init__ at creation time
        activity.when_year = summary.when.year
        activity.when_month = summary.when.month
        activity.when_day = summary.when.day
        activity.when_hour = summary.when.hour
        activity.when_minute = summary.when.minute
        activity.when_second = summary.when.second
    if summary.hours is not None:
        activity.hours = summary.hours
    if summary.minutes is not None:
        activity.minutes = summary.minutes
    if summary.seconds is not None:
        activity.seconds = summary.seconds
    if summary.distance and activity.distance == 0:
        activity.distance = summary.distance
    if summary.kcal and activity.kcal == 0:
        activity.kcal = summary.kcal
    if summary.avg_hr and activity.avg_hr == 0:
        activity.avg_hr = summary.avg_hr
    if summary.max_hr and activity.max_hr == 0:
        activity.max_hr = summary.max_hr
    if summary.avg_cadence and activity.avg_cadence == 0:
        activity.avg_cadence = summary.avg_cadence
    if summary.avg_speed and activity.avg_speed == 0.0:
        activity.avg_speed = summary.avg_speed

    # ensure auto calculated fields
    entities.evaluate_activity(activity)


tasks.tasks_registry.register_task(FitImportTask)
