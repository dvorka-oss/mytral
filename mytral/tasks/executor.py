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

"""Task executor interface and thread-based implementation."""

import abc

from mytral import tasks
from mytral.tasks import _base


class MytralTaskRegistry:
    """MyTraL tasks registry - tasks execute task entities."""

    __create_key = object()
    __singleton = None

    @classmethod
    def registry(cls):
        if cls.__singleton is None:
            return MytralTaskRegistry(cls.__create_key)
        return cls.__singleton

    def __init__(self, create_key):
        assert create_key == MytralTaskRegistry.__create_key, (
            "This is singleton! Constructor calls are forbidden"
        )

        self._tasks: dict[str, _base.TaskBase] = {}

    def register_task(self, task_cls: type[_base.TaskBase]):
        if not issubclass(task_cls, _base.TaskBase):
            raise ValueError(
                "Task implementation class must be a subclass of MyTraL's TaskBase"
            )

        self._tasks[task_cls.TASK_TYPE] = task_cls

    def get_task(self, task_type: str) -> _base.TaskBase:
        return self._tasks[task_type]

    def get_task_display_name(self, task_type: str) -> str:
        return self.get_task(task_type).TASK_DISPLAY_NAME


# registry of UserDataset do
tasks_registry = MytralTaskRegistry.registry()


class TaskExecutor(abc.ABC):
    """Abstract interface for task execution - enables cloud migration."""

    @abc.abstractmethod
    def submit(self, task: tasks.TaskEntity) -> str:
        """Submit task for execution.

        Parameters
        ----------
        task : TaskEntity
            Task to execute.

        Returns
        -------
        str
            Task ID.
        """
        pass

    @abc.abstractmethod
    def get_status(self, task_id: str, user_id: str) -> tasks.TaskEntity:
        """Get current task status and details (excludes logs).

        Parameters
        ----------
        task_id : str
            Task identifier.
        user_id : str
            User identifier.

        Returns
        -------
        TaskEntity
            Task entity with current status.
        """
        pass

    @abc.abstractmethod
    def get_logs(self, task_id: str, user_id: str, tail: int = 100) -> list[str]:
        """Get task logs (separate from status).

        Parameters
        ----------
        task_id : str
            Task identifier.
        user_id : str
            User identifier.
        tail : int
            Number of most recent log entries to return.

        Returns
        -------
        list[str]
            List of log entries.
        """
        pass

    @abc.abstractmethod
    def get_all_tasks(self, user_id: str) -> list[tasks.TaskEntity]:
        """Get all tasks for a user.

        Parameters
        ----------
        user_id : str
            User identifier.

        Returns
        -------
        list[TaskEntity]
            List of all tasks for the user.
        """
        pass

    @abc.abstractmethod
    def cancel(self, task_id: str, user_id: str) -> bool:
        """Attempt to cancel a running task (sets cancellation flag).

        Parameters
        ----------
        task_id : str
            Task identifier.
        user_id : str
            User identifier.

        Returns
        -------
        bool
            True if cancellation flag was set, False otherwise.
        """
        pass


class ResourceLockError(Exception):
    """Exception raised when a task is submitted while another task is running."""

    pass
