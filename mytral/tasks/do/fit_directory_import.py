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
"""Async task: import multiple FIT files from a directory."""

import io
import pathlib
import uuid

from mytral import app_logger
from mytral import app_user_ds as ds
from mytral import tasks
from mytral.backends import entities as be_entities
from mytral.blobstore import activity_service as blob_svc_module
from mytral.recordings import fit_extractor
from mytral.recordings import parquet_converter


class FitDirectoryImportTask(tasks.TaskBase):
    """Import all FIT files from a directory, creating activities for each.

    Parameters are provided via ``task_entity.parameters``:

    - ``user_id`` (str): owning user identifier
    - ``dataset_name`` (str): target dataset name
    - ``data_dir`` (str): absolute path to directory containing .fit files
    - ``sport_type`` (str, optional): default sport type for imported activities
    - ``on_conflict`` (str): conflict resolution strategy (skip, override, new_key)
    - ``correlation_id`` (str): import run identifier
    """

    TASK_TYPE = "fit_directory_import"
    TASK_DISPLAY_NAME = "FIT Directory Import"

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
        """Execute FIT directory import task.

        Raises
        ------
        RuntimeError
            On unrecoverable failures.
        """
        params = self.task_entity.parameters
        user_id: str = params["user_id"]
        dataset_name: str = params["dataset_name"]
        data_dir: str = params["data_dir"]
        sport_type: str = params.get("sport_type", "")
        on_conflict: str = params.get("on_conflict", "skip")
        correlation_id: str = params.get("correlation_id", str(uuid.uuid4()))

        self.log(f"FIT directory import: user={user_id}, dir={data_dir}")
        self.update_progress(5)
        self.check_cancellation()

        # validate directory
        dir_path = pathlib.Path(data_dir)
        if not dir_path.is_dir():
            raise RuntimeError(f"Directory does not exist: {data_dir}")

        # find all .fit files (case-insensitive extension match)
        fit_files = sorted(
            path
            for path in dir_path.iterdir()
            if path.is_file() and path.suffix.lower() == ".fit"
        )
        self.log(f"Found {len(fit_files)} FIT files")
        for f in fit_files:
            self.log(f"  - {f.name}")

        if not fit_files:
            self.log("No FIT files found in directory")
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

        # process each FIT file
        for idx, fit_path in enumerate(fit_files):
            progress = 10 + int((idx / len(fit_files)) * 85)
            self.update_progress(progress)
            self.check_cancellation()

            try:
                result = self._process_single_fit(
                    user_id=user_id,
                    dataset_name=dataset_name,
                    fit_path=fit_path,
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
                self.log(f"Failed to import {fit_path.name}: {exc}")
                app_logger.error(
                    "FIT directory import failed for file",
                    file=str(fit_path),
                    error=str(exc),
                )

        self.update_progress(100)
        self.log(
            f"FIT directory import complete: {imported_count} imported, "
            f"{skipped_count} skipped, {failed_count} failed"
        )

    def _process_single_fit(
        self,
        user_id: str,
        dataset_name: str,
        fit_path: pathlib.Path,
        sport_type: str,
        on_conflict: str,
        correlation_id: str,
        blob_svc: blob_svc_module.ActivityBlobService,
    ) -> str:
        """Process a single FIT file.

        Parameters
        ----------
        user_id : str
            Owning user identifier.
        dataset_name : str
            Target dataset name.
        fit_path : pathlib.Path
            Path to the FIT file.
        sport_type : str
            Optional sport type override.
        on_conflict : str
            Conflict resolution strategy.
        correlation_id : str
            Import run identifier.
        blob_svc : ActivityBlobService
            Blob service instance.

        Returns
        -------
        str
            "imported", "skipped", or raises exception on failure.
        """
        # validate file size before reading
        max_size = self._config.blobstore_max_recording_size_bytes
        file_size = fit_path.stat().st_size
        if file_size > max_size:
            raise RuntimeError(
                f"FIT file {fit_path.name} exceeds maximum allowed size "
                f"({max_size // (1024 * 1024)} MiB)"
            )

        # read FIT file once and reuse for summary extraction
        fit_data = fit_path.read_bytes()

        # extract summary to get name and other metadata
        summary = fit_extractor.extract_fit_summary(fit_data)

        # determine activity name: use filename stem
        activity_name = fit_path.stem

        # create activity entity
        activity = be_entities.ActivityEntity()
        activity.key = ds.create_key()
        activity.name = activity_name

        # set sport type from parameter or summary
        if sport_type:
            activity.activity_type_key = sport_type
        elif summary.activity_type_key:
            activity.activity_type_key = summary.activity_type_key

        # set datetime from summary if available
        if summary.when:
            activity.when = summary.when.strftime("%Y-%m-%d %H:%M")
            activity.when_year = summary.when.year
            activity.when_month = summary.when.month
            activity.when_day = summary.when.day
            activity.when_hour = summary.when.hour
            activity.when_minute = summary.when.minute

        # set duration from summary
        if summary.hours is not None:
            activity.hours = summary.hours
        if summary.minutes is not None:
            activity.minutes = summary.minutes
        if summary.seconds is not None:
            activity.seconds = summary.seconds

        # set distance from summary
        if summary.distance:
            activity.distance = summary.distance

        # set kcal from summary
        if summary.kcal:
            activity.kcal = summary.kcal

        # set HR data from summary
        if summary.avg_hr:
            activity.avg_hr = summary.avg_hr
        if summary.max_hr:
            activity.max_hr = summary.max_hr

        # set cadence from summary
        if summary.avg_cadence:
            activity.avg_cadence = summary.avg_cadence
        if summary.max_cadence:
            activity.max_cadence = summary.max_cadence

        # set speed from summary
        if summary.avg_speed:
            activity.avg_speed = summary.avg_speed

        # set elevation from summary
        if summary.elevation_gain:
            activity.elevation_gain = summary.elevation_gain

        activity.src = "fit-import"
        activity.src_key = fit_path.name
        activity.src_descriptor = f"directory-import-{correlation_id}"

        # check for conflicts
        existing_key = self._find_activity_conflict(
            user_id=user_id,
            dataset_name=dataset_name,
            activity=activity,
            summary=summary,
        )

        if existing_key:
            self.log(
                f"Conflict detected for {fit_path.name}: "
                f"existing_key={existing_key}, strategy={on_conflict}"
            )
            if on_conflict == "skip":
                self.log(f"Skipping {fit_path.name} (conflict)")
                return "skipped"
            if on_conflict == "override":
                # delete existing blobs to avoid storage leak
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
                self.log(f"Updated activity from {fit_path.name}")

        # create activity if not overriding
        if not existing_key or on_conflict != "override":
            ds.create_activity(
                user_id=user_id,
                dataset_name=dataset_name,
                entity=activity,
            )
            self.log(f"Created activity {activity.key} from {fit_path.name}")

        self.log(
            f"Processing {fit_path.name}: key={activity.key}, "
            f"when_year={activity.when_year}, src_key={activity.src_key}"
        )

        # upload FIT blob (reuse already-read data via BytesIO)
        meta = blob_svc.upload_recording(
            user_id=user_id,
            activity_key=activity.key,
            uploaded_file=io.BytesIO(fit_data),
            original_filename=fit_path.name,
            content_type="application/octet-stream",
        )

        # convert to parquet directly
        try:
            parquet_bytes = parquet_converter.fit_to_parquet(fit_data)
            blob_svc.save_parquet(
                user_id=user_id,
                activity_key=activity.key,
                source_blob_key=meta.blob_key,
                parquet_data=parquet_bytes,
            )
            self.log(f"Parquet saved for {fit_path.name}")
        except Exception as exc:
            self.log(f"WARNING: Parquet conversion failed for {fit_path.name}: {exc}")

        # pre-generate map data (polylines, elevation profile) so that the
        # first page view of the activity is fast instead of blocking the UI
        # for tens of seconds while the FIT is re-parsed on the request thread
        try:
            self.log("Generating map data...")
            blob_svc.ensure_gpx_map_data(
                user_id=user_id,
                activity_key=activity.key,
                blob_key=meta.blob_key,
            )
            self.log("Map data generated")
        except Exception as exc:
            self.log(f"WARNING: Map data generation failed for {fit_path.name}: {exc}")

        return "imported"

    def _find_activity_conflict(
        self,
        user_id: str,
        dataset_name: str,
        activity: be_entities.ActivityEntity,
        summary: fit_extractor.RecordingSummary,
    ) -> str | None:
        """Return existing activity's key if conflict, else None.

        Conflict is determined by src_key (FIT filename).
        Uses summary.when.year when available, otherwise searches all years.
        """
        if activity.src_key:
            # use summary year when available; otherwise search all years
            # (activity.when_year defaults to current year, which would miss
            # conflicts from the same file imported in a prior year)
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


tasks.tasks_registry.register_task(FitDirectoryImportTask)
