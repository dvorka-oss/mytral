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

"""Async task: import Strava user ZIP archive data."""

import gzip
import pathlib

from mytral import app_logger
from mytral import plugins
from mytral import tasks
from mytral.blobstore import activity_service as blob_svc_module
from mytral.integrations import gpx_recording
from mytral.integrations import strava_user_archive
from mytral.integrations import tcx_recording


class StravaArchiveImportTask(tasks.TaskBase):
    """Import activities from a Strava user ZIP archive."""

    TASK_TYPE = "strava_archive_import"
    TASK_DISPLAY_NAME = "Strava Archive Import"

    DATA_DIR_KEY = strava_user_archive.STRAVA_ARCHIVE_DATA_DIR_KEY

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
        """Execute Strava archive import.

        Raises
        ------
        RuntimeError
            On unrecoverable failures.
        """

        params = self.task_entity.parameters
        user_id: str = params["user_id"]
        dataset_name: str = params["dataset_name"]
        data_dir_str: str = params[StravaArchiveImportTask.DATA_DIR_KEY]

        self.log(f"Strava archive import started (dir={data_dir_str})")
        self.update_progress(2)

        data_dir = pathlib.Path(data_dir_str)
        if not data_dir.is_dir():
            raise RuntimeError(f"Data directory not found: {data_dir}")

        plugin: strava_user_archive.StravaUserArchiveActivitiesImportPlugin = (
            plugins.registry.get_plugin(
                strava_user_archive.StravaUserArchiveActivitiesImportPlugin.NAME
            )
        )
        plugin.logger = self.logger

        user_profile = self._dataset.profile(user_id)
        correlation_id: str = params.get("correlation_id", "")

        self.log("Parsing activities.csv from Strava archive…")
        self.update_progress(5)

        try:
            activities = plugin.import_activities(
                datasets={StravaArchiveImportTask.DATA_DIR_KEY: data_dir},
                user_profile=user_profile,
                correlation_id=correlation_id,
            )
        except Exception as exc:
            raise RuntimeError(f"Failed to parse Strava archive data: {exc}") from exc

        total = len(activities)
        self.log(f"Parsed {total} activities from {data_dir_str}")
        self.update_progress(10)

        if total == 0:
            self.log("No activities found — import complete")
            self.update_progress(100)
            return

        # ---- phase 1: create activities in dataset ----
        self._dataset.create_activities(
            user_id=user_id,
            dataset_name=dataset_name,
            entity_list=activities,
        )
        self.log(f"Created {total} activities in dataset '{dataset_name}'")
        self.update_progress(25)
        self.check_cancellation()

        # ---- phase 2: upload photos ----
        blob_svc = blob_svc_module.ActivityBlobService(
            store=self._blobstore,
            dataset=self._dataset,
            config=self._config,
        )
        photos_uploaded = 0
        photos_failed = 0
        recordings_imported = 0
        recordings_skipped = 0
        recordings_failed = 0
        for i, activity in enumerate(activities):
            self.check_cancellation()

            photo_paths = getattr(activity, "_photo_paths", [])
            if photo_paths:
                self.log(
                    f"Uploading {len(photo_paths)} photo(s) for activity "
                    f"'{activity.name}' ({activity.key})"
                )

                uploaded_files = []
                for rel_path in photo_paths:
                    # rel_path from CSV already includes the media/ prefix,
                    # e.g. "media/abc.jpg"
                    photo_path = data_dir / rel_path
                    if not photo_path.is_file():
                        self.log(f"  WARNING: photo file not found: {photo_path}")
                        photos_failed += 1
                        continue

                    try:
                        uploaded_files.append((open(photo_path, "rb"), photo_path.name))
                    except OSError as exc:
                        self.log(f"  WARNING: cannot open photo '{photo_path}': {exc}")
                        photos_failed += 1

                if uploaded_files:
                    try:
                        blob_svc.upload_photos(
                            user_id=user_id,
                            activity_key=activity.key,
                            uploaded_files=uploaded_files,
                            name="",
                            description="",
                            keywords="strava,archive,import",
                        )
                        photos_uploaded += len(uploaded_files)
                    except Exception as exc:
                        app_logger.warning(
                            "StravaArchiveImportTask: photo upload failed",
                            activity_key=activity.key,
                            error=str(exc),
                        )
                        photos_failed += len(uploaded_files)
                    finally:
                        # close file handles
                        for file_stream, _ in uploaded_files:
                            try:
                                file_stream.close()
                            except Exception:
                                pass

            recording_path = getattr(activity, "_recording_path", "")
            if recording_path:
                recording_status = self._import_recording(
                    blob_svc=blob_svc,
                    data_dir=data_dir,
                    activity=activity,
                    recording_path=pathlib.Path(recording_path),
                    user_id=user_id,
                    dataset_name=dataset_name,
                )
                if recording_status == "imported":
                    recordings_imported += 1
                elif recording_status == "skipped":
                    recordings_skipped += 1
                elif recording_status == "failed":
                    recordings_failed += 1

            progress = 25 + int(70 * (i + 1) / total)
            self.update_progress(progress)

        self.update_progress(100)

        self.log(
            f"Strava archive import complete: {total} activities imported, "
            f"{photos_uploaded} photos uploaded, {photos_failed} photos failed, "
            f"{recordings_imported} recordings imported, "
            f"{recordings_skipped} recordings skipped, "
            f"{recordings_failed} recordings failed"
        )

    def _import_recording(
        self,
        blob_svc: blob_svc_module.ActivityBlobService,
        data_dir: pathlib.Path,
        activity,
        recording_path: pathlib.Path,
        user_id: str,
        dataset_name: str,
    ) -> str:
        """Import a Strava archive recording for one activity."""
        suffixes = [suffix.lower() for suffix in recording_path.suffixes]
        if suffixes[-1:] not in ([".gpx"], [".tcx"], [".gz"]):
            self.log(
                f"  WARNING: skipping unsupported recording format: {recording_path}"
            )
            return "skipped"

        full_path = data_dir / recording_path
        if not full_path.is_file():
            self.log(f"  WARNING: recording file not found: {full_path}")
            return "failed"

        try:
            payload = full_path.read_bytes()
            if suffixes[-1:] == [".gz"]:
                payload = gzip.decompress(payload)
            normalized_filename = _normalized_recording_filename(full_path)
        except Exception as exc:
            self.log(f"  WARNING: cannot read recording '{full_path}': {exc}")
            return "failed"

        def _persist_summary(summary) -> None:
            activity_to_save = self._dataset.get_activity(
                user_id,
                dataset_name,
                activity.key,
            )
            if activity_to_save is None:
                raise RuntimeError(f"Activity {activity.key} not found")
            if normalized_filename.lower().endswith(".tcx"):
                tcx_recording.apply_tcx_summary(activity_to_save, summary)
            else:
                gpx_recording.apply_gpx_summary(activity_to_save, summary)
            self._dataset.update_activity(
                user_id=user_id,
                dataset_name=dataset_name,
                entity=activity_to_save,
            )

        try:
            if normalized_filename.lower().endswith(".tcx"):
                tcx_recording.import_tcx_recording_bytes(
                    user_id=user_id,
                    activity_key=activity.key,
                    tcx_data=payload,
                    original_filename=normalized_filename,
                    blob_svc=blob_svc,
                    extract_summary=True,
                    summary_handler=_persist_summary,
                    log=self.logger,
                )
            else:
                gpx_recording.import_gpx_recording_bytes(
                    user_id=user_id,
                    activity_key=activity.key,
                    gpx_data=payload,
                    original_filename=normalized_filename,
                    blob_svc=blob_svc,
                    extract_summary=True,
                    summary_handler=_persist_summary,
                    log=self.logger,
                )
            self.log(f"Imported recording for activity '{activity.name}'")
            return "imported"
        except Exception as exc:
            self.log(f"  WARNING: recording import failed for {full_path}: {exc}")
            return "failed"


def _normalized_recording_filename(recording_path: pathlib.Path) -> str:
    """Return a filename acceptable to the recording validator."""
    suffixes = [suffix.lower() for suffix in recording_path.suffixes]
    if suffixes[-2:] in ([".gpx", ".gz"], [".tcx", ".gz"]):
        return recording_path.with_suffix("").name
    return recording_path.name


tasks.tasks_registry.register_task(StravaArchiveImportTask)
