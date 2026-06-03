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

import datetime
import gzip
import pathlib
import traceback

from mytral import app_logger
from mytral import plugins
from mytral import tasks
from mytral.blobstore import activity_service as blob_svc_module
from mytral.integrations import gpx_recording
from mytral.integrations import strava_user_archive
from mytral.integrations import tcx_recording
from mytral.tasks.do import strava_commons


class StravaArchiveImportTask(tasks.TaskBase):
    """Import activities from a Strava user ZIP archive."""

    TASK_TYPE = "strava_archive_import"
    TASK_DISPLAY_NAME = "Strava Archive Import"

    DATA_DIR_KEY = strava_user_archive.STRAVA_ARCHIVE_DATA_DIR_KEY
    IMPORT_PHOTOS_KEY = "import_photos"
    IMPORT_RECORDINGS_KEY = "import_recordings"
    IMPORT_FROM_DATE_KEY = "import_from_date"
    IMPORT_TO_DATE_KEY = "import_to_date"

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
        on_conflict: str = str(params.get("on_conflict", "skip") or "skip")
        import_photos = strava_commons._to_bool(
            params.get(StravaArchiveImportTask.IMPORT_PHOTOS_KEY, True)
        )
        import_recordings = strava_commons._to_bool(
            params.get(StravaArchiveImportTask.IMPORT_RECORDINGS_KEY, True)
        )
        import_from_date = _parse_iso_date_param(
            params.get(StravaArchiveImportTask.IMPORT_FROM_DATE_KEY, ""),
            StravaArchiveImportTask.IMPORT_FROM_DATE_KEY,
        )
        import_to_date = _parse_iso_date_param(
            params.get(StravaArchiveImportTask.IMPORT_TO_DATE_KEY, ""),
            StravaArchiveImportTask.IMPORT_TO_DATE_KEY,
        )
        if import_from_date and import_to_date and import_from_date > import_to_date:
            raise RuntimeError(
                f"Invalid date range: {import_from_date.isoformat()} > "
                f"{import_to_date.isoformat()}"
            )

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

        self.log("Parsing activities.csv from Strava archive...")
        self.update_progress(5)

        try:
            activities = plugin.import_activities(
                datasets={StravaArchiveImportTask.DATA_DIR_KEY: data_dir},
                user_profile=user_profile,
                correlation_id=correlation_id,
            )
        except Exception as exc:
            raise RuntimeError(f"Failed to parse Strava archive data: {exc}") from exc

        parsed_total = len(activities)
        self.log(f"Parsed {parsed_total} activities from {data_dir_str}")
        activities = _filter_activities_by_date_range(
            activities=activities,
            import_from_date=import_from_date,
            import_to_date=import_to_date,
        )
        activities, conflict_stats = self._apply_on_conflict(
            activities=activities,
            user_id=user_id,
            dataset_name=dataset_name,
            on_conflict=on_conflict,
        )
        overridden_keys = conflict_stats["overridden_keys"]
        total = len(activities)
        if parsed_total != total:
            self.log(
                f"Date range filter kept {total} of {parsed_total} activities "
                f"(from={import_from_date}, to={import_to_date})"
            )
        if conflict_stats["skipped"] > 0:
            self.log(
                f"Conflict resolution skipped {conflict_stats['skipped']} "
                f"activities (on_conflict={on_conflict})"
            )
        if conflict_stats["overridden"] > 0:
            self.log(
                f"Conflict resolution overriding {conflict_stats['overridden']} "
                f"activities (on_conflict={on_conflict})"
            )
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
        for overridden_key in sorted(overridden_keys):
            try:
                blob_svc.delete_all_activity_blobs(
                    user_id=user_id,
                    activity_key=overridden_key,
                )
            except Exception as exc:
                self.log(
                    "  WARNING: failed to clear existing blobs for overridden "
                    f"activity {overridden_key}: {exc}"
                )
        photos_uploaded = 0
        photos_failed = 0
        recordings_imported = 0
        recordings_skipped = 0
        recordings_failed = 0
        for i, activity in enumerate(activities):
            self.check_cancellation()

            self.log(
                f"Processing activity {i}/{total} '{activity.name}' ({activity.key})",
                activity_key=activity.key,
            )

            photo_paths = getattr(activity, "_photo_paths", [])
            if import_photos and photo_paths:
                self.log(
                    f"  Uploading {len(photo_paths)} photo(s) for activity "
                    f"'{activity.name}'",
                    activity_key=activity.key,
                )

                uploaded_files = []
                for rel_path in photo_paths:
                    # rel_path from CSV already includes the media/ prefix,
                    # e.g. "media/abc.jpg"
                    photo_path = data_dir / rel_path
                    if not photo_path.is_file():
                        self.log(f"    WARNING: photo file not found: {photo_path}")
                        photos_failed += 1
                        continue

                    try:
                        uploaded_files.append((open(photo_path, "rb"), photo_path.name))
                    except OSError as exc:
                        self.log(
                            f"    WARNING: cannot open photo '{photo_path}': {exc}"
                        )
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
                            f"StravaArchiveImportTask: photo upload failed: {exc}",
                            activity_key=activity.key,
                            error=str(exc),
                            traceback=traceback.format_exc(),
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
            if recording_path and import_recordings:
                self.log(
                    f"  Importing recording(s) for '{activity.name}' ",
                    activity_key=activity.key,
                )

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
            elif recording_path and not import_recordings:
                recordings_skipped += 1

            self.log(f"DONE processing activity {i}/{total} '{activity.name}'")

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
        is_plain = suffixes[-1:] in ([".gpx"], [".tcx"])
        is_gz = suffixes[-2:] in ([".gpx", ".gz"], [".tcx", ".gz"])
        if not (is_plain or is_gz):
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
            if is_gz:
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
            self.log(f"  Imported recording for activity '{activity.name}'")
            return "imported"
        except Exception as exc:
            self.log(f"  WARNING: recording import failed for {full_path}: {exc}")
            return "failed"

    def _apply_on_conflict(
        self,
        activities: list,
        user_id: str,
        dataset_name: str,
        on_conflict: str,
    ) -> tuple[list, dict]:
        """Apply import on_conflict strategy by (src, src_key)."""
        mode = on_conflict.lower().strip()
        if mode not in ("skip", "override", "new_key"):
            mode = "new_key"
        if mode == "new_key":
            return activities, {"skipped": 0, "overridden": 0, "overridden_keys": set()}

        existing = {}
        for current in self._dataset.list_activities(
            user_id=user_id,
            dataset_name=dataset_name,
        ):
            src = str(getattr(current, "src", "") or "")
            src_key = str(getattr(current, "src_key", "") or "")
            if src and src_key:
                existing[(src, src_key)] = current.key

        skipped = 0
        overridden = 0
        overridden_keys: set[str] = set()
        resolved = []
        for activity in activities:
            src = str(getattr(activity, "src", "") or "")
            src_key = str(getattr(activity, "src_key", "") or "")
            current_key = existing.get((src, src_key))
            if current_key is None:
                resolved.append(activity)
                continue
            if mode == "skip":
                skipped += 1
                continue
            activity.key = current_key
            overridden += 1
            overridden_keys.add(current_key)
            resolved.append(activity)

        return resolved, {
            "skipped": skipped,
            "overridden": overridden,
            "overridden_keys": overridden_keys,
        }


def _normalized_recording_filename(recording_path: pathlib.Path) -> str:
    """Return a filename acceptable to the recording validator."""
    suffixes = [suffix.lower() for suffix in recording_path.suffixes]
    if suffixes[-2:] in ([".gpx", ".gz"], [".tcx", ".gz"]):
        return recording_path.with_suffix("").name
    return recording_path.name


def _parse_iso_date_param(value, param_name: str) -> datetime.date | None:
    """Parse optional YYYY-MM-DD date task parameter."""
    text = str(value or "").strip()
    if not text:
        return None
    try:
        return datetime.datetime.strptime(text, "%Y-%m-%d").date()
    except ValueError as exc:
        raise RuntimeError(
            f"Invalid {param_name} value '{text}'. Expected YYYY-MM-DD."
        ) from exc


def _activity_date(activity) -> datetime.date | None:
    """Extract activity date for range filtering."""
    year = int(getattr(activity, "when_year", 0) or 0)
    month = int(getattr(activity, "when_month", 0) or 0)
    day = int(getattr(activity, "when_day", 0) or 0)
    if year <= 0 or month <= 0 or day <= 0:
        return None
    try:
        return datetime.date(year=year, month=month, day=day)
    except ValueError:
        return None


def _filter_activities_by_date_range(
    activities: list,
    import_from_date: datetime.date | None,
    import_to_date: datetime.date | None,
) -> list:
    """Return activities filtered by optional inclusive date bounds."""
    if import_from_date is None and import_to_date is None:
        return activities
    filtered: list = []
    for activity in activities:
        activity_date = _activity_date(activity)
        if activity_date is None:
            filtered.append(activity)
            continue
        if import_from_date and activity_date < import_from_date:
            continue
        if import_to_date and activity_date > import_to_date:
            continue
        filtered.append(activity)
    return filtered


tasks.tasks_registry.register_task(StravaArchiveImportTask)
