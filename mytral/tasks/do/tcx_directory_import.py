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
"""Async task: import multiple TCX files from a directory."""

import io
import pathlib
import uuid

from mytral import app_logger
from mytral import app_user_ds as ds
from mytral import tasks
from mytral.backends import entities as be_entities
from mytral.blobstore import activity_service as blob_svc_module
from mytral.recordings import parquet_converter
from mytral.recordings import tcx_extractor


class TcxDirectoryImportTask(tasks.TaskBase):
    """Import all TCX files from a directory, creating activities for each."""

    TASK_TYPE = "tcx_directory_import"
    TASK_DISPLAY_NAME = "TCX Directory Import"

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
        """Execute TCX directory import task."""
        params = self.task_entity.parameters
        user_id: str = params["user_id"]
        dataset_name: str = params["dataset_name"]
        data_dir: str = params["data_dir"]
        sport_type: str = params.get("sport_type", "")
        on_conflict: str = params.get("on_conflict", "skip")
        correlation_id: str = params.get("correlation_id", str(uuid.uuid4()))

        self.log(f"TCX directory import: user={user_id}, dir={data_dir}")
        self.update_progress(5)
        self.check_cancellation()

        dir_path = pathlib.Path(data_dir)
        if not dir_path.is_dir():
            raise RuntimeError(f"Directory does not exist: {data_dir}")

        tcx_files = sorted(
            path
            for path in dir_path.iterdir()
            if path.is_file()
            and (path.suffix.lower() == ".tcx" or path.suffixes[-2:] == [".tcx", ".gz"])
        )
        self.log(f"Found {len(tcx_files)} TCX files")
        for f in tcx_files:
            self.log(f"  - {f.name}")

        if not tcx_files:
            self.log("No TCX files found in directory")
            self.update_progress(100)
            return

        self.update_progress(10)
        self.check_cancellation()

        blob_svc = blob_svc_module.ActivityBlobService(
            store=self._blobstore,
            dataset=self._dataset,
            config=self._config,
        )

        imported_count = 0
        skipped_count = 0
        failed_count = 0

        for idx, tcx_path in enumerate(tcx_files):
            progress = 10 + int((idx / len(tcx_files)) * 85)
            self.update_progress(progress)
            self.check_cancellation()

            try:
                result = self._process_single_tcx(
                    user_id=user_id,
                    dataset_name=dataset_name,
                    tcx_path=tcx_path,
                    sport_type=sport_type,
                    on_conflict=on_conflict,
                    correlation_id=correlation_id,
                    blob_svc=blob_svc,
                )
                if result == "imported":
                    imported_count += 1
                elif result == "skipped":
                    skipped_count += 1
            except Exception as exc:
                failed_count += 1
                self.log(f"Failed to import {tcx_path.name}: {exc}")
                app_logger.error(
                    "TCX directory import failed for file",
                    file=str(tcx_path),
                    error=str(exc),
                )

        self.update_progress(100)
        self.log(
            f"TCX directory import complete: {imported_count} imported, "
            f"{skipped_count} skipped, {failed_count} failed"
        )

    def _process_single_tcx(
        self,
        user_id: str,
        dataset_name: str,
        tcx_path: pathlib.Path,
        sport_type: str,
        on_conflict: str,
        correlation_id: str,
        blob_svc: blob_svc_module.ActivityBlobService,
    ) -> str:
        """Process a single TCX file."""
        max_size = self._config.blobstore_max_recording_size_bytes
        file_size = tcx_path.stat().st_size
        if file_size > max_size:
            raise RuntimeError(
                f"TCX file {tcx_path.name} exceeds maximum allowed size "
                f"({max_size // (1024 * 1024)} MiB)"
            )

        tcx_data = tcx_path.read_bytes()
        summary = tcx_extractor.extract_tcx_summary(tcx_data)

        if summary.name_hint:
            activity_name = summary.name_hint
        else:
            activity_name = tcx_path.stem

        activity = be_entities.ActivityEntity()
        activity.key = ds.create_key()
        activity.name = activity_name

        if sport_type:
            activity.activity_type_key = sport_type
        elif summary.activity_type_key:
            activity.activity_type_key = summary.activity_type_key

        if summary.when:
            activity.when = summary.when.strftime("%Y-%m-%d %H:%M")
            activity.when_year = summary.when.year
            activity.when_month = summary.when.month
            activity.when_day = summary.when.day
            activity.when_hour = summary.when.hour
            activity.when_minute = summary.when.minute

        if summary.hours is not None:
            activity.hours = summary.hours
        if summary.minutes is not None:
            activity.minutes = summary.minutes
        if summary.seconds is not None:
            activity.seconds = summary.seconds
        if summary.distance:
            activity.distance = summary.distance
        if summary.avg_hr:
            activity.avg_hr = summary.avg_hr
        if summary.max_hr:
            activity.max_hr = summary.max_hr
        if summary.avg_cadence:
            activity.avg_cadence = summary.avg_cadence
        if summary.max_cadence:
            activity.max_cadence = summary.max_cadence
        if summary.elevation_gain:
            activity.elevation_gain = summary.elevation_gain

        activity.src = "tcx-import"
        activity.src_key = tcx_path.name
        activity.src_descriptor = f"directory-import-{correlation_id}"

        existing_key = self._find_activity_conflict(
            user_id=user_id,
            dataset_name=dataset_name,
            activity=activity,
            summary=summary,
        )

        if existing_key:
            self.log(
                f"Conflict detected for {tcx_path.name}: "
                f"existing_key={existing_key}, strategy={on_conflict}"
            )
            if on_conflict == "skip":
                self.log(f"Skipping {tcx_path.name} (conflict)")
                return "skipped"
            if on_conflict == "override":
                blob_svc.delete_all_activity_blobs(
                    user_id=user_id,
                    activity_key=existing_key,
                )
                activity.key = existing_key
                ds.update_activity(
                    user_id=user_id,
                    dataset_name=dataset_name,
                    entity=activity,
                )
                self.log(f"Updated activity from {tcx_path.name}")

        if not existing_key or on_conflict != "override":
            ds.create_activity(
                user_id=user_id,
                dataset_name=dataset_name,
                entity=activity,
            )
            self.log(f"Created activity {activity.key} from {tcx_path.name}")

        self.log(
            f"Processing {tcx_path.name}: key={activity.key}, "
            f"when_year={activity.when_year}, src_key={activity.src_key}"
        )

        original_filename = _normalized_recording_filename(tcx_path)
        meta = blob_svc.upload_recording(
            user_id=user_id,
            activity_key=activity.key,
            uploaded_file=io.BytesIO(tcx_data),
            original_filename=original_filename,
            content_type="application/xml",
        )

        try:
            parquet_bytes = parquet_converter.tcx_to_parquet(tcx_data)
            blob_svc.save_parquet(
                user_id=user_id,
                activity_key=activity.key,
                source_blob_key=meta.blob_key,
                parquet_data=parquet_bytes,
            )
            self.log(f"Parquet saved for {tcx_path.name}")
        except Exception as exc:
            self.log(f"WARNING: Parquet conversion failed for {tcx_path.name}: {exc}")

        try:
            self.log("Generating map data...")
            blob_svc.ensure_gpx_map_data(
                user_id=user_id,
                activity_key=activity.key,
                blob_key=meta.blob_key,
            )
            self.log("Map data generated")
        except Exception as exc:
            self.log(f"WARNING: Map data generation failed for {tcx_path.name}: {exc}")

        return "imported"

    def _find_activity_conflict(
        self,
        user_id: str,
        dataset_name: str,
        activity: be_entities.ActivityEntity,
        summary: tcx_extractor.RecordingSummary,
    ) -> str | None:
        """Return existing activity's key if conflict, else None."""
        if activity.src_key:
            filter_year = summary.when.year if summary.when else 0
            year_activities = ds.list_activities(
                user_id=user_id,
                dataset_name=dataset_name,
                filter_year=filter_year,
            )
            for existing in year_activities:
                if (
                    existing.src == activity.src
                    and existing.src_key == activity.src_key
                ):
                    return existing.key
        return None


def _normalized_recording_filename(recording_path: pathlib.Path) -> str:
    """Return a filename acceptable to the recording validator."""
    suffixes = [suffix.lower() for suffix in recording_path.suffixes]
    if suffixes[-2:] == [".tcx", ".gz"]:
        return recording_path.with_suffix("").name
    return recording_path.name


tasks.tasks_registry.register_task(TcxDirectoryImportTask)
