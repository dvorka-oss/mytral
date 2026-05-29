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

"""Hello World task - simple demo task for testing."""

import time

from mytral import tasks


class HelloWorldTask(tasks.TaskBase):
    """Simple demo task that counts to 10 with delays.

    Demonstrates:
    - Logging
    - Progress updates
    - Cooperative cancellation
    """

    TASK_TYPE = "hello_world"
    TASK_DISPLAY_NAME = "Hello World"

    WAIT_TIME = 1.0

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
        """Initialize Hello World task.

        Parameters
        ----------
        task_entity : TaskEntity
            Task entity with metadata.
        logger :
            Logger instance.
        log_callback : callable, optional
            Callback for real-time logging.
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
        """Execute the Hello World task."""
        self.log("Hello World task started!")

        for i in range(1, 11):
            # check for cancellation (IMPORTANT for cooperative cancellation)
            self.check_cancellation()

            time.sleep(1)  # simulate work
            progress_pct = i * 10
            self.log(f"Progress: {i}/10 ({progress_pct}%)")
            self.update_progress(progress_pct)

        self.log("Hello World task completed!")


tasks.tasks_registry.register_task(HelloWorldTask)
