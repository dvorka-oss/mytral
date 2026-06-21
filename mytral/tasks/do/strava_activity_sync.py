# MyTraL: my trailing log
#
# Copyright (C) 2022-2026 Martin Dvorak <martin.dvorak@mindforger.com>
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

"""Strava single activity sync task - synchronizes one activity from Strava."""

import io
import time
import uuid

from mytral import tasks
from mytral.blobstore import activity_service as blob_svc_module
from mytral.integrations import gpx_recording
from mytral.integrations import strava
from mytral.tasks.do import strava_commons


class StravaActivitySyncTask(tasks.TaskBase):
    """Synchronizes a single activity from Strava without overriding existing data.

    Updates description (if empty), imports recordings (if none present),
    and imports photos (if none present) from Strava.

    Parameters are provided via task_entity.parameters:

    - user_id: str
    - dataset_name: str
    - activity_key: str  (MyTraL activity UUID)
    - src_key: str  (Strava activity ID)
    - access_token: str  (encrypted)
    - refresh_token: str  (encrypted)
    - client_id: str
    - client_secret: str  (encrypted)
    - auth_until: int
    """

    TASK_TYPE = "strava_sync_activity"
    TASK_DISPLAY_NAME = "Strava — Activity Synchronization"
    ENCRYPTED_PARAM_KEYS = ["access_token", "refresh_token", "client_secret"]

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
        """Execute single-activity sync from Strava."""
        params = self.task_entity.parameters
        user_id = params["user_id"]
        dataset_name = params["dataset_name"]
        activity_key = params["activity_key"]
        src_key = params["src_key"]

        self.log(
            f"Strava activity sync started for activity "
            f"'{activity_key}' (Strava ID: {src_key})"
        )
        self.check_cancellation()

        creds = strava_commons.build_strava_credentials(
            params, self._enc_key, with_refresh=True
        )

        # refresh token if expired or near expiry (< 600s remaining)
        if creds.strava_auth_until and (creds.strava_auth_until - time.time()) < 600:
            self.log("Access token near expiry, refreshing...")
            try:
                from mytral import settings

                profile = settings.UserProfile()
                profile.strava_access_token = creds.strava_access_token
                profile.strava_refresh_token = creds.strava_refresh_token
                profile.strava_client_id = creds.strava_client_id
                profile.strava_client_secret = creds.strava_client_secret
                profile.strava_auth_until = creds.strava_auth_until
                strava.auth_get_access_for_refresh_token(profile, self.logger)
                creds.strava_access_token = profile.strava_access_token
                self.log("Token refreshed successfully")
            except Exception as exc:
                self.log(
                    f"Token refresh failed: {exc} - proceeding with existing token"
                )

        self.check_cancellation()

        # load the activity from dataset
        activity = self._dataset.get_activity(
            user_id=user_id, dataset_name=dataset_name, key=activity_key
        )
        if not activity:
            raise RuntimeError(
                f"Activity '{activity_key}' not found in dataset '{dataset_name}'"
            )

        access_token = creds.strava_access_token

        # initialize blob service
        blob_svc = blob_svc_module.ActivityBlobService(
            store=self._blobstore,
            dataset=self._dataset,
            config=self._config,
        )

        desc_updated = False
        calories_updated = False
        recordings_imported = False
        photos_uploaded = 0

        # --- fetch activity detail from Strava ---
        self.log("Fetching activity detail from Strava...")
        self.update_progress(10)

        detail = strava.fetch_activity_detail(
            activity_id=src_key,
            access_token=access_token,
            logger=self.logger,
        )

        needs_update = False

        if detail:
            # update description if empty
            desc = detail.get("description", "")
            if desc and not activity.description:
                activity.description = str(desc)
                desc_updated = True
                needs_update = True
                self.log("Description updated from Strava")

            # update calories if zero
            detail_cal = detail.get("calories", 0)
            if detail_cal and activity.kcal == 0:
                activity.kcal = int(detail_cal)
                calories_updated = True
                needs_update = True
                self.log("Calories updated from Strava")

        if needs_update:
            self._dataset.update_activity(
                user_id=user_id,
                dataset_name=dataset_name,
                entity=activity,
            )
            self.log("Activity metadata saved")

        self.check_cancellation()
        self.update_progress(30)

        # --- import recording from streams if none present ---
        has_recordings = bool(activity.recorded_blob_keys)
        if has_recordings:
            self.log(
                f"Activity already has {len(activity.recorded_blob_keys)} "
                f"recording(s) - skipping recording import"
            )
        else:
            self.log("No recordings present - importing from Strava streams...")
            try:
                streams = strava.fetch_activity_streams(
                    activity_id=src_key,
                    access_token=access_token,
                    logger=self.logger,
                )
                if streams and streams.get("latlng", {}).get("data"):
                    gpx_bytes = strava.streams_to_gpx(
                        streams,
                        activity_name=activity.name,
                    )
                    gpx_recording.import_gpx_recording_bytes(
                        user_id=user_id,
                        activity_key=activity.key,
                        gpx_data=gpx_bytes,
                        original_filename=f"strava-{src_key}.gpx",
                        blob_svc=blob_svc,
                        extract_summary=False,
                        log=self.logger,
                    )
                    recordings_imported = True
                    self.log("GPS recording imported from Strava streams")
                else:
                    self.log(
                        f"No GPS streams available for activity '{activity.name}' "
                        f"({src_key})"
                    )
            except Exception as exc:
                self.log(f"Recording import failed: {exc}")

        self.check_cancellation()
        self.update_progress(60)

        # --- import photos if none present ---
        try:
            existing_photos = blob_svc.list_photos(
                user_id=user_id, activity_key=activity_key
            )
        except Exception:
            existing_photos = []

        if existing_photos:
            self.log(
                f"Activity already has {len(existing_photos)} "
                f"photo(s) - skipping photo import"
            )
        else:
            self.log("No photos present - importing from Strava...")
            try:
                photo_meta_list = strava.fetch_activity_photos(
                    activity_id=src_key,
                    access_token=access_token,
                    logger=self.logger,
                )
                if photo_meta_list:
                    uploaded_files = []
                    for photo_meta in photo_meta_list:
                        urls = photo_meta.get("urls", {})
                        photo_url = urls.get("2048") or urls.get("1024")
                        if not photo_url:
                            continue
                        photo_data = strava.download_photo(
                            photo_url=photo_url,
                            logger=self.logger,
                        )
                        if photo_data:
                            photo_name = (
                                f"strava-{src_key}-"
                                f"{photo_meta.get('unique_id', uuid.uuid4())}"
                                f".jpg"
                            )
                            uploaded_files.append((io.BytesIO(photo_data), photo_name))

                    if uploaded_files:
                        try:
                            blob_svc.upload_photos(
                                user_id=user_id,
                                activity_key=activity.key,
                                uploaded_files=uploaded_files,
                                name="",
                                description="",
                                keywords="strava,api,sync",
                            )
                            photos_uploaded = len(uploaded_files)
                            self.log(f"{photos_uploaded} photo(s) imported from Strava")
                        except Exception as exc:
                            self.log(f"Photo upload failed: {exc}")
            except Exception as exc:
                self.log(f"Photo fetch failed: {exc}")

        self.update_progress(100)

        # build summary
        summary_parts = []
        if desc_updated:
            summary_parts.append("description updated")
        if calories_updated:
            summary_parts.append("calories updated")
        if recordings_imported:
            summary_parts.append("recording imported")
        if photos_uploaded:
            summary_parts.append(f"{photos_uploaded} photo(s) imported")

        if summary_parts:
            self.log(f"Synchronization complete: {', '.join(summary_parts)}")
        else:
            self.log("Synchronization complete: activity is already up to date")


tasks.tasks_registry.register_task(StravaActivitySyncTask)
