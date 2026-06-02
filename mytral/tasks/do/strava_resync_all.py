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

"""Strava re-sync all task - purges all Strava activities then re-imports."""

import pathlib

from mytral import commons
from mytral import plugins
from mytral import tasks
from mytral.backends.datasets import dataset_json as dataset_json_module
from mytral.integrations import strava
from mytral.tasks.do import strava_commons
from mytral.tasks.do import strava_gear_sync


class StravaResyncAllActivitiesTask(tasks.TaskBase):
    """Purges all Strava-sourced activities from all datasets, then re-imports.

    IMPORTANT: requires params["purge_confirmed"] == True as a safety guard.
    Activities with src == "strava" are deleted from all year datasets and
    the lifelong (aggregation) dataset.
    Gear is never deleted.
    """

    TASK_TYPE = "strava_resync_all"
    TASK_DISPLAY_NAME = "Strava — Re-sync All Activities"
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
        """Execute full re-sync: purge all Strava activities then re-import."""
        params = self.task_entity.parameters
        user_id = params["user_id"]
        dataset_name = params["dataset_name"]
        import_recordings = strava_commons._to_bool(
            params.get("import_recordings", True)
        )
        import_photos = strava_commons._to_bool(params.get("import_photos", True))

        # safety guard - must be explicitly confirmed
        if not params.get("purge_confirmed"):
            raise ValueError(
                "Re-sync requires explicit confirmation (purge_confirmed=True). "
                "Aborting to prevent accidental data loss."
            )

        self.log(
            "Strava re-sync started: purging all Strava-sourced activities "
            f"from all datasets (recordings={import_recordings}, "
            f"photos={import_photos})"
        )
        self.check_cancellation()

        # find all year datasets + lifelong for this user
        user_dir = pathlib.Path(self._dataset.user_data_dir) / user_id
        year_ds_names = dataset_json_module.list_activity_year_dataset_names(user_dir)
        all_ds_names = list(year_ds_names)
        if commons.DS_LIFELONG not in all_ds_names:
            all_ds_names.append(commons.DS_LIFELONG)

        self.log(f"Datasets to purge: {all_ds_names}")
        self.check_cancellation()

        # purge phase: delete all src=strava activities from all datasets
        total_deleted = 0
        for ds_name in all_ds_names:
            self.check_cancellation()
            try:
                activities = self._dataset.all_activities(user_id, ds_name)
                strava_keys = [
                    key
                    for key, act in activities.items()
                    if act.src == strava.SRC_STRAVA
                ]
                self.log(
                    f"Dataset '{ds_name}': found {len(strava_keys)} "
                    "Strava activities to delete"
                )
                deleted_in_ds = 0
                for i, key in enumerate(strava_keys):
                    if i % 10 == 0:
                        self.check_cancellation()
                    self._dataset.delete_activity(
                        user_id=user_id,
                        dataset_name=ds_name,
                        key=key,
                    )
                    deleted_in_ds += 1
                    total_deleted += 1
                    if deleted_in_ds % 10 == 0:
                        self.log(
                            f"  Deleted {deleted_in_ds}/{len(strava_keys)} "
                            f"in '{ds_name}'"
                        )
                self.log(f"Dataset '{ds_name}': deleted {deleted_in_ds} activities")
            except Exception as exc:
                self.log(f"Warning: error purging dataset '{ds_name}': {exc}")

        self.log(
            f"Purge complete: {total_deleted} Strava activities deleted "
            f"from {len(all_ds_names)} datasets"
        )
        self.update_progress(10)
        self.check_cancellation()

        # evict cache after bulk deletes
        try:
            self._dataset.cache_evict(user_id)
        except Exception as exc:
            self.log(f"Cache eviction warning (non-fatal): {exc}")

        # import phase: re-import all activities from Strava (after_ts=0 = all)
        self.log("Starting full import from Strava (all time)...")

        creds = strava_commons.build_strava_credentials(
            params, self._enc_key, with_refresh=True
        )

        self.check_cancellation()

        try:
            strava_activities = strava.export_json_from_strava_service(
                user_profile=creds,
                after_timestamp=0,
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
            self.log("No activities returned from Strava")
            self.update_progress(100)
            return

        t_plugin = strava.StravaActivitiesImportPlugin
        gear = self._dataset.list_gear(user_id=user_id, dataset_name=dataset_name)
        activities_plugin: t_plugin = plugins.registry.get_plugin(t_plugin.NAME)
        user_profile = self._dataset.profile(user_id)
        new_activities = activities_plugin.import_activities(
            datasets={t_plugin.USE_TYPE_STRAVA_LIST: strava_activities},
            user_profile=user_profile,
            gear=gear,
        )

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
            f"Import phase complete: {imported} activities imported to '{dataset_name}'"
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
        # gear sync step is needed after the re-import
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


tasks.tasks_registry.register_task(StravaResyncAllActivitiesTask)
