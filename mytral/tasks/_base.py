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

"""Base class for all task do."""

import abc
import datetime

from mytral.tasks import _entities


class TaskBase(abc.ABC):
    """Base class for all task do."""

    TASK_TYPE = "base_task"
    TASK_DISPLAY_NAME = "FIT Recording Import"

    def __init__(
        self,
        task_entity: _entities.TaskEntity,
        logger,
        log_callback,
        config=None,
        dataset=None,
        blobstore=None,
        enc_key="",
    ):
        """Initialize task base.

        Parameters
        ----------
        task_entity : TaskEntity
            Task entity with metadata.
        logger :
            Logger instance for application logging.
        log_callback : callable, optional
            Callback function to call with (user_id, task_id, message) when logging.
            Used to write logs to executor buffer in real-time.
        config :
            MyTral config instance.
        dataset :
            Dataset instance.
        blobstore :
            Blobstore instance.
        enc_key : str
            Encryption key.
        """
        self.task_entity = task_entity

        self._config = config
        self._enc_key = enc_key

        self._dataset = dataset
        self._blobstore = blobstore

        self._log_buffer: list[str] = []
        self._log_callback = log_callback

        self.logger = logger

    @abc.abstractmethod
    def execute(self) -> None:
        """Execute the task. Raises exception on error.

        Must periodically call self.check_cancellation() to support
        cooperative cancellation.
        """
        pass

    def log(self, message: str, **kwargs) -> None:
        """Add timestamped log entry (buffered).

        Parameters
        ----------
        message : str
            Log message to add.
        """
        timestamp = datetime.datetime.now().isoformat()
        log_entry = f"{timestamp} - {message}"
        self._log_buffer.append(log_entry)
        self.logger.info(f"[Task] {message}", task_id=self.task_entity.key, **kwargs)

        # also send to executor buffer for real-time visibility
        if self._log_callback:
            self._log_callback(
                self.task_entity.user_id, self.task_entity.key, log_entry
            )

    def get_buffered_logs(self) -> list[str]:
        """Get buffered logs and clear the buffer.

        Returns
        -------
        list[str]
            List of buffered log entries.
        """
        logs = self._log_buffer.copy()
        self._log_buffer = []
        return logs

    def update_progress(self, percentage: int) -> None:
        """Update task progress (0-100).

        Parameters
        ----------
        percentage : int
            Progress percentage (0-100).
        """
        self.task_entity.progress = min(100, max(0, percentage))

    def check_cancellation(self) -> None:
        """Check if task has been cancelled.

        Raises
        ------
        TaskCancelledException
            If task has been cancelled.

        Notes
        -----
        Task do MUST call this periodically (e.g., in loops) to
        support cooperative cancellation.
        """
        if self.task_entity.is_cancelled:
            self.log("Task cancelled by user")
            raise _entities.TaskCancelledException(
                f"Task {self.task_entity.key} was cancelled"
            )
