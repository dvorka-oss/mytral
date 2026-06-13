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
# along with this program.  If not, see <http://www.gnu.org/licenses/>.

"""Background task that warms the 3D IRM file cache on first access.

When a user visits /insight/irm3d and no cached workout strain data exists
for their current power-model parameters, this task is dispatched to compute
the strain breakdowns in the background.  The UI shows a progress bar while
the task runs; on completion the page renders instantly from cache.
"""

from mytral import tasks
from mytral.metrics import irm3d


class Irm3dCacheWarmupTask(tasks.TaskBase):
    """Compute 3D IRM workout-strain cache asynchronously.

    Reads all activities for the owning user, opens their power recordings
    from the blob store, computes per-sample strain decomposition, and
    persists the results to the file-based IRM3D cache.
    """

    TASK_TYPE = "irm3d_cache_warmup"
    TASK_DISPLAY_NAME = "3D IRM Cold-Cache Warmup"

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
        """Initialize IRM3D cache warmup task.

        Parameters
        ----------
        task_entity : TaskEntity
            Task entity with metadata and ``parameters["user_id"]``.
        logger :
            Structured logger instance.
        log_callback : callable
            Callback for real-time log streaming.
        """
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
        """Execute the cache warmup (called in a background thread)."""
        # lazy imports to avoid circular dependency with irm3d_uri_space
        from mytral import app_user_ds as ds
        from mytral.blueprints.irm3d_uri_space import _compute_workout_rows_with_cache

        user_id = self.task_entity.parameters["user_id"]
        cp_watts = float(self.task_entity.parameters["cp_watts"])
        w_prime_joules = float(self.task_entity.parameters["w_prime_joules"])
        pmax_watts = float(self.task_entity.parameters["pmax_watts"])

        model_params = irm3d.PowerModelParams(
            cp_watts=cp_watts,
            w_prime_joules=w_prime_joules,
            pmax_watts=pmax_watts,
        )

        self.log(
            f"Starting 3D IRM cache warmup "
            f"(CP={cp_watts:.0f} W, "
            f"W\u2032={w_prime_joules:.0f} J, "
            f"Pmax={pmax_watts:.0f} W)"
        )

        # load all activities for the user
        user_profile = ds.profile(user_id)
        activities = ds.list_activities(
            user_id=user_id,
            dataset_name=user_profile.dataset_name,
            sort_by_when=True,
            skip_future=True,
        )

        total = len(activities)
        self.log(f"Loaded {total} activities — scanning for power recording...")

        # compute strain rows (populates the file cache on the way)
        user_data_dir = str(ds.user_dir(user_id))
        workout_rows = _compute_workout_rows_with_cache(
            activities=activities,
            user_id=user_id,
            model_params=model_params,
            user_data_dir=user_data_dir,
        )

        self.log(f"Cache warmup complete — {len(workout_rows)} workouts analysed")
        self.update_progress(100)


tasks.tasks_registry.register_task(Irm3dCacheWarmupTask)
