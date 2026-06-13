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

"""Strava new activities sync task - imports activities newer than latest in dataset."""

import time

from mytral import plugins
from mytral import settings
from mytral import tasks
from mytral.integrations import strava
from mytral.tasks.do import strava_commons
from mytral.tasks.do import strava_gear_sync


class StravaNewActivitiesSyncTask(tasks.TaskBase):
    """Imports Strava activities newer than the latest activity in the current dataset.

    Parameters are provided via task_entity.parameters:

    - user_id: str
    - dataset_name: str  (target dataset)
    - after_ts: int  (Unix timestamp, activities after this will be fetched; 0=all)
    - access_token: str  (encrypted)
    - refresh_token: str  (encrypted)
    - client_id: str
    - client_secret: str  (encrypted)
    - strava_url: str
    """

    TASK_TYPE = "strava_sync_new_to_current"
    TASK_DISPLAY_NAME = "Strava — New Activities Sync"
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
        """Execute new-activities sync from Strava."""
        params = self.task_entity.parameters
        user_id = params["user_id"]
        dataset_name = params["dataset_name"]
        after_ts = int(params.get("after_ts", 0))
        import_recordings = strava_commons._to_bool(
            params.get("import_recordings", True)
        )
        import_photos = strava_commons._to_bool(params.get("import_photos", True))

        self.log(
            f"Strava new-activities sync started "
            f"(after_ts={after_ts}, dataset={dataset_name}, "
            f"recordings={import_recordings}, photos={import_photos})"
        )
        self.check_cancellation()

        creds = strava_commons.build_strava_credentials(
            params, self._enc_key, with_refresh=True
        )

        # refresh token if expired or near expiry (< 600s remaining)
        if creds.strava_auth_until and (creds.strava_auth_until - time.time()) < 600:
            self.log("Access token near expiry, refreshing...")
            try:
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

        # fetch activities from Strava
        self.log("Fetching activities from Strava API...")
        self.update_progress(5)

        try:
            strava_activities = strava.export_json_from_strava_service(
                user_profile=creds,
                after_timestamp=after_ts,
                logger=self.logger,
            )
        except Exception as exc:
            raise RuntimeError(
                f"Failed to fetch activities from Strava: {exc}"
            ) from exc

        total = len(strava_activities) if strava_activities else 0
        self.log(f"Fetched {total} activities from Strava")
        self.check_cancellation()

        if not strava_activities:
            self.log("No new activities to import")
            self.update_progress(100)
            return

        # convert Strava JSON to MyTraL entities
        self.update_progress(10)
        t_plugin = strava.StravaActivitiesImportPlugin
        gear = self._dataset.list_gear(user_id=user_id, dataset_name=dataset_name)
        activities_plugin: t_plugin = plugins.registry.get_plugin(t_plugin.NAME)
        user_profile = self._dataset.profile(user_id)
        new_activities = activities_plugin.import_activities(
            datasets={t_plugin.USE_TYPE_STRAVA_LIST: strava_activities},
            user_profile=user_profile,
            gear=gear,
        )

        self.check_cancellation()

        # import each activity
        imported = 0
        for activity in new_activities:
            self.check_cancellation()
            self._dataset.create_activity(
                user_id=user_id,
                dataset_name=dataset_name,
                entity=activity,
            )
            imported += 1
            if imported % 10 == 0 or imported == total:
                progress = 10 + int(20 * imported / total)
                self.update_progress(progress)
                self.log(f"Imported {imported}/{total} activities")

        self.log(
            f"Import phase complete: {imported} activities "
            f"imported to dataset '{dataset_name}'"
        )

        # media enrichment phase: fetch detail, recordings, photos from Strava
        if import_recordings or import_photos:
            self.log("Starting media enrichment phase...")
            strava_commons.enrich_strava_activities(
                activities=new_activities,
                creds=creds,
                user_id=user_id,
                dataset_name=dataset_name,
                import_recordings=import_recordings,
                import_photos=import_photos,
                total=total,
                dataset=self._dataset,
                blobstore=self._blobstore,
                config=self._config,
                log_fn=self.log,
                logger=self.logger,
                check_cancellation=self.check_cancellation,
                update_progress=self.update_progress,
            )

        # sync gear and relink activity gear references so no separate manual
        # gear sync step is needed after an activity import
        self.log("Starting automatic gear sync and re-link...")
        strava_gear_sync.run_gear_sync_and_relink(
            creds=creds,
            dataset=self._dataset,
            user_id=user_id,
            dataset_name=dataset_name,
            log_fn=self.log,
            logger=self.logger,
        )

        self.update_progress(100)


tasks.tasks_registry.register_task(StravaNewActivitiesSyncTask)
