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
import traceback

from mytral import loggers
from mytral import tasks

"""Task storage - persist tasks to JSON files and logs to separate .log files."""


class TaskStorage:
    """Persist tasks to JSON files and logs to separate .log files using dataset
    interface.
    """

    def __init__(self, dataset=None, logger=None):
        """Initialize task storage.

        Parameters
        ----------
        dataset : UserDataset | None
            User dataset instance (provides user_dir and persistence methods).
        """
        self._logger = logger or loggers.MytralPrintLogger()
        self.dataset = dataset
        # single lock to serialize all storage writes within a process
        self._storage_lock = threading.RLock()

    def _get_lock(self, lock_key: str) -> threading.RLock:
        """Get the storage lock.

        Parameters
        ----------
        lock_key : str
            Lock identifier (unused — kept for call-site compatibility).

        Returns
        -------
        threading.RLock
            Lock used to serialize all storage operations.
        """
        return self._storage_lock

    def save(self, task: tasks.TaskEntity) -> None:
        """Save task metadata to JSON file (excludes logs).

        Uses file locking to prevent corruption during concurrent writes.

        Parameters
        ----------
        task : TaskEntity
            Task entity to save.
        """
        # get or create file lock
        lock_key = f"{task.user_id}:{task.key}"
        lock = self._get_lock(lock_key)

        # thread-safe write
        with lock:
            task_dict = task.to_dict()
            self.dataset.save_task(task.user_id, task_dict)

    def append_logs(self, user_id: str, task_id: str, log_entries: list[str]) -> None:
        """Append log entries to task's .log file.

        This is the ONLY method that writes to log files.
        Log files are append-only for performance.

        Parameters
        ----------
        user_id : str
            User identifier.
        task_id : str
            Task identifier.
        log_entries : list[str]
            Log entries to append.
        """
        # append to log file (thread-safe)
        lock_key = f"log:{user_id}:{task_id}"
        lock = self._get_lock(lock_key)

        with lock:
            self.dataset.append_task_logs(user_id, task_id, log_entries)

    def load(self, task_id: str, user_id: str) -> tasks.TaskEntity:
        """Load task metadata from JSON file (excludes logs).

        Parameters
        ----------
        task_id : str
            Task identifier.
        user_id : str
            User identifier.

        Returns
        -------
        TaskEntity
            Loaded task entity.
        """
        task_dict = self.dataset.load_task(user_id, task_id)
        return tasks.TaskEntity.from_dict(task_dict)

    def load_logs(self, task_id: str, user_id: str, tail: int = 100) -> list[str]:
        """Load logs from .log file.

        Parameters
        ----------
        task_id : str
            Task identifier.
        user_id : str
            User identifier.
        tail : int
            Number of most recent log entries to return (default 100).

        Returns
        -------
        list[str]
            List of log entries (newest last).
        """
        return self.dataset.load_task_logs(user_id, task_id, tail)

    def list_tasks(
        self, user_id: str, status: tasks.TaskStatus | None = None
    ) -> list[tasks.TaskEntity]:
        """List all tasks for user, optionally filtered by status.

        NOTE: Does NOT load logs - logs are loaded separately via load_logs().

        Parameters
        ----------
        user_id : str
            User identifier.
        status : TaskStatus | None
            Optional status filter.

        Returns
        -------
        list[TaskEntity]
            List of task entities, sorted by creation time (newest first).
        """
        task_files = self.dataset.list_task_files(user_id)

        task_list = []
        for filepath in task_files:
            task_id = filepath.stem[5:]  # remove 'task-' prefix
            try:
                task = self.load(task_id, user_id)

                if status is None or task.status == status:
                    task_list.append(task)
            except Exception as ex:
                # skip corrupted task files
                self._logger.warning(
                    f"[Tasks] failed to load list corrupted {task_id} with status "
                    f"{status}: {ex}\n{traceback.format_exc()}",
                    filepath=filepath,
                    traceback=traceback.format_exc(),
                )
                continue

        return sorted(task_list, key=lambda t: t.created_at, reverse=True)

    def delete_task(self, user_id: str, task_id: str) -> None:
        """Delete task JSON and log files.

        Parameters
        ----------
        user_id : str
            User identifier.
        task_id : str
            Task identifier.
        """
        if not user_id or not task_id:
            self._logger.warning(
                "Invalid user_id or task_id for deletion",
                user_id={user_id},
                task_id={task_id},
            )

        self.dataset.delete_task_files(user_id=user_id, task_id=task_id)

    def cleanup_old_tasks(self, user_id: str, days: int = 30) -> int:
        """Delete completed/failed tasks older than N days.

        Deletes both .json and .log files.

        Parameters
        ----------
        user_id : str
            User identifier.
        days : int
            Number of days to keep tasks (default 30).

        Returns
        -------
        int
            Number of tasks deleted.
        """
        cutoff_date = datetime.datetime.now() - datetime.timedelta(days=days)
        deleted_count = 0

        for task in self.list_tasks(user_id):
            if task.status in [
                tasks.TaskStatus.COMPLETED,
                tasks.TaskStatus.FAILED,
            ]:
                if task.completed_at and task.completed_at < cutoff_date:
                    # delete JSON and log files
                    self.delete_task(user_id, task.key)
                    deleted_count += 1

        return deleted_count

    def cleanup_finished_tasks(self, user_id: str) -> int:
        """Delete all completed/failed tasks (regardless of age).

        Deletes both .json and .log files.

        Parameters
        ----------
        user_id : str
            User identifier.

        Returns
        -------
        int
            Number of tasks deleted.
        """
        deleted_count = 0

        for task in self.list_tasks(user_id):
            if task.status in [
                tasks.TaskStatus.COMPLETED,
                tasks.TaskStatus.FAILED,
            ]:
                # delete JSON and log files
                self.delete_task(user_id, task.key)
                deleted_count += 1

        return deleted_count
