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
import datetime
import threading
import time

from mytral import loggers
from mytral import tasks
from mytral.tasks import executors
from mytral.tasks import storage

"""Task manager - Flask extension for task management."""


class TaskManager:
    """Flask extension for task management."""

    def __init__(
        self, app=None, dataset=None, enc_key: str = "", blobstore=None, config=None
    ):
        """Initialize task manager.

        Parameters
        ----------
        app : Flask | None
            Flask application instance (optional).
        dataset : UserDataset | None
            User dataset instance.
        enc_key : str
            Encryption key for sensitive task parameters.
        blobstore
            Blobstore instance passed to tasks that need blob operations.
        config
            Application configuration (MytralConfig).
        """
        self.executor = None
        self.storage = None
        self.dataset = dataset
        self._blobstore = blobstore
        self._config = config
        self._task_timeout_s = 3600
        self._watchdog_period = 60
        self._watchdog_started = False
        self._logger = loggers.MytralStructLogger("app_task_manager")

        if dataset:
            # initialize immediately if dataset is provided
            self.executor = executors.ThreadTaskExecutor(
                dataset=dataset, enc_key=enc_key, blobstore=blobstore, config=config
            )
            self.storage = storage.TaskStorage(dataset=dataset)

            # recover crashed tasks on startup
            self._recover_crashed_tasks(dataset)

        if app:
            self.init_app(
                app,
                dataset=dataset,
                enc_key=enc_key,
                blobstore=blobstore,
                config=config,
            )

    def init_app(
        self,
        app,
        dataset=None,
        enc_key: str = "",
        task_timeout_s: int = 3600,
        watchdog_period: int = 60,
        blobstore=None,
        config=None,
    ):
        """Initialize task manager with Flask app.

        Parameters
        ----------
        app : Flask
            Flask application instance.
        dataset : UserDataset | None
            User dataset instance (optional, uses self.dataset if not provided).
        enc_key : str
            Encryption key for sensitive task parameters.
        task_timeout_s : int
            Maximum task duration in seconds before auto-cancellation.
        watchdog_period : int
            How often (in seconds) the watchdog checks for timed-out tasks.
        blobstore :
            Blobstore instance passed to tasks that need blob operations.
        config : MytralConfig
            Mytral config instance.
        """
        self._watchdog_period = int(watchdog_period)

        # use provided dataset or fall back to stored one
        if dataset:
            self.dataset = dataset
        if blobstore:
            self._blobstore = blobstore
        if config:
            self._config = config

        if not self.dataset:
            raise ValueError("Dataset must be provided either in __init__ or init_app")

        # initialize if not already done
        if not self.executor:
            self.executor = executors.ThreadTaskExecutor(
                dataset=self.dataset,
                enc_key=enc_key,
                blobstore=self._blobstore,
                config=self._config,
            )
            self.storage = storage.TaskStorage(dataset=self.dataset)
            self._recover_crashed_tasks(self.dataset)

        self._task_timeout_s = task_timeout_s
        self._start_timeout_watchdog()

        # IMPORTANT: self-register on Flask app as task manager (could be any attribute)
        app.task_manager = self

    def _start_timeout_watchdog(self):
        """Start background thread that auto-cancels tasks exceeding max duration.

        Safe to call multiple times — only one watchdog thread is ever started.
        """
        if self._watchdog_started:
            return
        self._watchdog_started = True

        def watchdog():
            while True:
                time.sleep(self._watchdog_period)  # check every minute
                self._logger.debug(
                    "[Tasks] cleaning cancelled tasks using watchdog ..."
                )
                try:
                    now = datetime.datetime.now()
                    user_ids = self.dataset.list_profiles() if self.dataset else []
                    for user_id in user_ids:
                        task_list = self.storage.list_tasks(
                            user_id, status=tasks.TaskStatus.RUNNING
                        )
                        for task in task_list:
                            if task.started_at:
                                elapsed = (now - task.started_at).total_seconds()
                                if elapsed > self._task_timeout_s:
                                    # cancel via executor so the in-memory task
                                    # entity seen by the running thread is updated
                                    cancelled = self.executor.cancel(task.key, user_id)
                                    if cancelled:
                                        self.storage.append_logs(
                                            user_id,
                                            task.key,
                                            [
                                                f"{now.isoformat()} - Task "
                                                f"auto-cancelled: exceeded max "
                                                f"duration of "
                                                f"{self._task_timeout_s}s "
                                                f"(elapsed: {int(elapsed)}s)"
                                            ],
                                        )
                except Exception as e:
                    # log but never crash — watchdog must keep running
                    self._logger.warning(f"Watchdog error: {e}")

        t = threading.Thread(target=watchdog, daemon=True, name="task-watchdog")
        t.start()

    @property
    def lock_manager(self):
        """Get the user task lock from executor.

        Returns
        -------
        UserTaskLock
            Per-user task lock instance.
        """
        return self.executor._user_task_lock

    def _recover_crashed_tasks(self, dataset):
        """Recover tasks that were running/queued when app crashed.

        This method is called on app startup to handle tasks that were
        interrupted by server restart.
        """
        # get all users from dataset
        user_ids = dataset.list_profiles()

        for user_id in user_ids:
            # load all tasks for this user
            task_list = self.storage.list_tasks(user_id)

            for task in task_list:
                if task.status == tasks.TaskStatus.RUNNING:
                    # task was running when app crashed
                    task.status = tasks.TaskStatus.FAILED
                    task.error_message = "Server restarted while task was running"
                    task.error_type = "ServerRestartError"
                    task.completed_at = datetime.datetime.now()

                    # append recovery log
                    self.storage.append_logs(
                        user_id,
                        task.key,
                        [
                            f"{datetime.datetime.now().isoformat()} - "
                            f"Task marked as FAILED due to server restart"
                        ],
                    )

                    self.storage.save(task)

                elif task.status == tasks.TaskStatus.QUEUED:
                    # task was queued but never started
                    task.status = tasks.TaskStatus.FAILED
                    task.error_message = "Server restarted before task could start"
                    task.error_type = "ServerRestartError"
                    task.completed_at = datetime.datetime.now()

                    self.storage.append_logs(
                        user_id,
                        task.key,
                        [
                            f"{datetime.datetime.now().isoformat()} - "
                            f"Task marked as FAILED (never started before restart)"
                        ],
                    )

                    self.storage.save(task)
