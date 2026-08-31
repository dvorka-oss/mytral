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

"""Polar Flow sync task - pulls new exercises via the AccessLink transaction model."""

from mytral import tasks
from mytral.tasks.do import polar_flow_commons


class PolarFlowSyncTask(tasks.TaskBase):
    """Imports new Polar Flow exercises using the AccessLink transaction model.

    Parameters (via task_entity.parameters):

    - user_id: str
    - dataset_name: str  (target dataset)
    - access_token: str  (encrypted)
    - polar_user_id: str
    - import_recordings: bool
    """

    TASK_TYPE = "polar_flow_sync_new"
    TASK_DISPLAY_NAME = "Polar Flow - New Activities Sync"
    ENCRYPTED_PARAM_KEYS = ["access_token"]

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
        """Execute the Polar Flow new-exercises sync."""
        params = self.task_entity.parameters
        user_id = params["user_id"]
        dataset_name = params["dataset_name"]
        import_recordings = polar_flow_commons.to_bool(
            params.get("import_recordings", True)
        )

        self.log(f"Polar Flow sync started (dataset={dataset_name})")

        creds = polar_flow_commons.build_polar_credentials(params, self._enc_key)
        polar_flow_commons.pull_new_exercises(
            creds,
            dataset=self._dataset,
            blobstore=self._blobstore,
            config=self._config,
            user_id=user_id,
            dataset_name=dataset_name,
            import_recordings=import_recordings,
            log_fn=self.log,
            logger=self.logger,
            check_cancellation=self.check_cancellation,
            update_progress=self.update_progress,
        )


tasks.tasks_registry.register_task(PolarFlowSyncTask)
