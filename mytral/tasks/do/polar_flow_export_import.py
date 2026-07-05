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

"""Polar Flow GDPR-export import task - backfills history from the export ZIP."""

from mytral import plugins
from mytral import tasks
from mytral.integrations import polar_flow
from mytral.integrations import polar_flow_export
from mytral.tasks.do import polar_flow_commons

ON_CONFLICT_SKIP = "skip"
ON_CONFLICT_OVERRIDE = "override"
ON_CONFLICT_NEW_KEY = "new_key"


class PolarFlowExportImportTask(tasks.TaskBase):
    """Imports historical activities from a Polar Flow "Download your data" ZIP.

    Parameters (via task_entity.parameters):

    - user_id: str
    - dataset_name: str  (target dataset)
    - zip_path: str  (path to the uploaded export ZIP)
    - on_conflict: str  (skip | override | new_key)
    """

    TASK_TYPE = "polar_flow_export_import"
    TASK_DISPLAY_NAME = "Polar Flow - Historical Export Import"
    ENCRYPTED_PARAM_KEYS: list[str] = []

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
        """Parse the export ZIP and import its training sessions."""
        params = self.task_entity.parameters
        user_id = params["user_id"]
        dataset_name = params["dataset_name"]
        zip_path = params["zip_path"]
        on_conflict = params.get("on_conflict", ON_CONFLICT_SKIP)

        self.log(f"Polar Flow export import started (zip={zip_path})")
        self.check_cancellation()

        summaries = polar_flow_export.parse_export(zip_path)
        total = len(summaries)
        self.log(f"Parsed {total} training session(s) from the export")
        if not summaries:
            self.update_progress(100)
            return

        self.update_progress(10)
        plugin = plugins.registry.get_plugin(
            polar_flow.PolarFlowActivitiesImportPlugin.NAME
        )
        user_profile = self._dataset.profile(user_id)
        activities = plugin.import_activities(
            datasets={plugin.USE_TYPE_POLAR_FLOW_LIST: summaries},
            user_profile=user_profile,
        )

        imported = 0
        skipped = 0
        overridden = 0
        for i, activity in enumerate(activities):
            self.check_cancellation()
            existing_key = polar_flow_commons.find_existing_polar_flow_activity(
                dataset=self._dataset,
                user_id=user_id,
                dataset_name=dataset_name,
                candidate=activity,
            )
            if existing_key and on_conflict == ON_CONFLICT_SKIP:
                skipped += 1
            elif existing_key and on_conflict == ON_CONFLICT_OVERRIDE:
                activity.key = existing_key
                self._dataset.update_activity(
                    user_id=user_id, dataset_name=dataset_name, entity=activity
                )
                overridden += 1
            else:
                # no conflict, or on_conflict == new_key: create fresh
                self._dataset.create_activity(
                    user_id=user_id, dataset_name=dataset_name, entity=activity
                )
                imported += 1

            if total:
                self.update_progress(10 + int(85 * (i + 1) / total))

        self._dataset.cache_evict(user_id)
        self.log(
            f"Polar Flow export import complete: {imported} imported, "
            f"{overridden} overridden, {skipped} skipped (duplicates)"
        )
        self.update_progress(100)


tasks.tasks_registry.register_task(PolarFlowExportImportTask)
