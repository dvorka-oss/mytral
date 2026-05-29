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
import concurrent.futures
import datetime
import threading
import time
import traceback

from mytral import loggers
from mytral import tasks
from mytral.tasks import locks
from mytral.tasks import storage


class ThreadTaskExecutor(tasks.TaskExecutor):
    """Local implementation using Python threading:

    - Cooperative multitasking.
    - Shared memory between the main thread and worker threads
      (enables in-memory caching of task status and logs for real-time updates).

    """

    def __init__(
        self,
        max_workers: int = 3,
        dataset=None,
        enc_key: str = "",
        blobstore=None,
        config=None,
    ):
        """Initialize thread task executor.

        Parameters
        ----------
        max_workers : int
            Maximum number of concurrent worker threads (default 3).
            Only one task per user can run at a time regardless of this limit.
        dataset : UserDataset | None
            User dataset instance for storage operations.
        enc_key : str
            Encryption key for decrypting sensitive task parameters.
        blobstore :
            Blobstore instance passed to tasks that need blob operations.
        config
            Application configuration (MytralConfig).
        """
        self._logger = loggers.MytralStructLogger("task-executor")
        self._executor = concurrent.futures.ThreadPoolExecutor(max_workers=max_workers)
        self._tasks: dict[str, tasks.TaskEntity] = {}  # in-memory cache
        self._lock = threading.Lock()
        self._storage = storage.TaskStorage(dataset=dataset, logger=self._logger)
        self._user_task_lock = locks.UserTaskLock()
        self._dataset = dataset
        self._enc_key = enc_key
        self._blobstore = blobstore
        self._config = config

        # log buffering
        self._log_buffers: dict[str, list[str]] = {}  # task_id -> buffered logs
        self._log_buffer_lock = threading.Lock()

        # start background thread for periodic log flushing
        self._start_log_flusher()

        self._log_name = "[MytralTaskExecutor]"

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

        Raises
        ------
        ResourceLockError
            If the user already has a running task.
        """
        # enforce at-most-one-task-per-user rule
        if not self._user_task_lock.acquire(task.user_id):
            raise tasks.ResourceLockError(
                "Another task is already running. "
                "Please wait for it to finish before starting a new one."
            )

        # fill human-friendly label early so queued tasks show proper name in UI
        if not task.task_display_name:
            task.task_display_name = tasks.tasks_registry.get_task_display_name(
                task.task_type
            )

        # persist task to JSON (without logs)
        self._storage.save(task)

        # add to in-memory cache
        with self._lock:
            self._tasks[task.key] = task

        # submit to thread pool
        self._executor.submit(self._execute_task_wrapper, task)

        return task.key

    def _execute_task_wrapper(self, task: tasks.TaskEntity):
        """Wrapper that handles task execution, error capture, and cleanup.

        Parameters
        ----------
        task : TaskEntity
            Task to execute.
        """
        log = self._logger.bind(
            task_id=task.key, task_type=task.task_type, user_id=task.user_id
        )
        log.debug(f"{self._log_name} starting task wrapper")
        try:
            # update status to RUNNING
            log.debug(f"{self._log_name} setting status to running")
            task.status = tasks.TaskStatus.RUNNING
            task.started_at = datetime.datetime.now()
            self._storage.save(task)
            log.debug(f"{self._log_name} saved running status to storage")

            # update in-memory cache
            with self._lock:
                self._tasks[task.key] = task
            log.debug(f"{self._log_name} updated in-memory cache with running status")

            # execute task
            log.debug(f"{self._log_name} about to execute task")
            task_instance = self._create_task_instance(task)
            task_instance.execute()
            log.info(f"{self._log_name} task execution completed")

            # NOTE: Logs are already written via callback during execution
            # No need to flush buffered logs again - would cause duplicates

            # mark as COMPLETED
            log.debug(f"{self._log_name} marking task as completed")
            task.status = tasks.TaskStatus.COMPLETED
            task.completed_at = datetime.datetime.now()
            task.progress = 100
            log.info(
                f"{self._log_name} task marked as completed",
                status=task.status,
                completed_at=task.completed_at,
                progress=task.progress,
            )

            # IMPORTANT: save and update cache immediately after marking complete
            log.debug(f"{self._log_name} saving completed status to storage")
            self._storage.save(task)
            log.debug(f"{self._log_name} saved completed status to storage")

            log.debug(
                f"{self._log_name} updating in-memory cache with completed status"
            )
            with self._lock:
                self._tasks[task.key] = task
            log.debug(f"{self._log_name} updated in-memory cache with completed status")

        except Exception as ex:
            log.error(
                f"{self._log_name} exception caught in task",
                error_type=type(ex).__name__,
                error=str(ex),
            )
            # capture full error details
            task.status = tasks.TaskStatus.FAILED
            task.error_message = str(ex)
            task.error_type = type(ex).__name__
            task.error_traceback = traceback.format_exc()
            task.completed_at = datetime.datetime.now()

            self._log(task.user_id, task.key, f"ERROR: {task.error_message}")
            log.error(f"{self._log_name} task marked as failed")

        finally:
            log.debug(f"{self._log_name} entering finally block")
            # flush remaining logs
            self._flush_logs(task.user_id, task.key)
            log.debug(f"{self._log_name} flushed remaining logs")

            # save final task state to storage (in case of exception)
            self._storage.save(task)
            log.debug(f"{self._log_name} saved final task state to storage")

            # update in-memory cache with final state (in case of exception)
            with self._lock:
                self._tasks[task.key] = task
            log.debug(f"{self._log_name} updated final in-memory cache")

            # release the per-user task lock, restoring write access
            self._user_task_lock.release(task.user_id)
            log.debug(f"{self._log_name} released user task lock")
            log.info(f"{self._log_name} task wrapper completed", status=task.status)

    def _create_task_instance(self, task: tasks.TaskEntity):
        """Create task implementation instance.

        Parameters
        ----------
        task : TaskEntity
            Task entity.

        Returns
        -------
        TaskBase
            Task implementation instance.
        """

        # create log callback for real-time logging
        def log_callback(user_id: str, task_id: str, message: str):
            """Callback to write logs to executor buffer in real-time."""
            with self._log_buffer_lock:
                buffer_key = f"{user_id}:{task_id}"
                if buffer_key not in self._log_buffers:
                    self._log_buffers[buffer_key] = []
                self._log_buffers[buffer_key].append(message)

        enc_key = self._enc_key

        return tasks.tasks_registry.get_task(task.task_type)(
            task_entity=task,
            logger=self._logger,
            log_callback=log_callback,
            config=self._config,
            dataset=self._dataset,
            blobstore=self._blobstore,
            enc_key=enc_key,
        )

    def _log(self, user_id: str, task_id: str, message: str):
        """Add log entry to buffer (buffered writes).

        Parameters
        ----------
        user_id : str
            User identifier.
        task_id : str
            Task identifier.
        message : str
            Log message.
        """
        timestamp = datetime.datetime.now().isoformat()
        log_entry = f"{timestamp} - {message}"

        with self._log_buffer_lock:
            buffer_key = f"{user_id}:{task_id}"
            if buffer_key not in self._log_buffers:
                self._log_buffers[buffer_key] = []
            self._log_buffers[buffer_key].append(log_entry)

            # flush if buffer is full (10 entries)
            if len(self._log_buffers[buffer_key]) >= 10:
                # flush without re-acquiring lock (we already have it)
                self._flush_logs_unlocked(user_id, task_id)

    def _log_entries(self, user_id: str, task_id: str, entries: list[str]):
        """Add multiple log entries to buffer.

        Parameters
        ----------
        user_id : str
            User identifier.
        task_id : str
            Task identifier.
        entries : list[str]
            Log entries (already timestamped).
        """
        with self._log_buffer_lock:
            buffer_key = f"{user_id}:{task_id}"
            if buffer_key not in self._log_buffers:
                self._log_buffers[buffer_key] = []
            self._log_buffers[buffer_key].extend(entries)

            # flush if buffer is full
            if len(self._log_buffers[buffer_key]) >= 10:
                # flush without re-acquiring lock (we already have it)
                self._flush_logs_unlocked(user_id, task_id)

    def _flush_logs(self, user_id: str, task_id: str):
        """Flush buffered logs to .log file (with locking).

        Parameters
        ----------
        user_id : str
            User identifier.
        task_id : str
            Task identifier.
        """
        with self._log_buffer_lock:
            self._flush_logs_unlocked(user_id, task_id)

    def _flush_logs_unlocked(self, user_id: str, task_id: str):
        """Flush buffered logs to .log file (assumes lock is already held).

        Parameters
        ----------
        user_id : str
            User identifier.
        task_id : str
            Task identifier.
        """
        buffer_key = f"{user_id}:{task_id}"
        if buffer_key in self._log_buffers and self._log_buffers[buffer_key]:
            self._storage.append_logs(user_id, task_id, self._log_buffers[buffer_key])
            self._log_buffers[buffer_key] = []

    def _start_log_flusher(self):
        """Start background thread to periodically flush logs (every 5 seconds)."""

        def flush_periodically():
            while True:
                time.sleep(5)
                with self._log_buffer_lock:
                    for buffer_key in list(self._log_buffers.keys()):
                        if ":" in buffer_key:
                            user_id, task_id = buffer_key.split(":", 1)
                            # use unlocked version since we already have the lock
                            self._flush_logs_unlocked(user_id, task_id)

        flusher_thread = threading.Thread(target=flush_periodically, daemon=True)
        flusher_thread.start()

    def cancel(self, task_id: str, user_id: str) -> bool:
        """Set cancellation flag for cooperative cancellation.

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
        with self._lock:
            if task_id in self._tasks:
                task = self._tasks[task_id]
                if task.user_id == user_id and task.status == tasks.TaskStatus.RUNNING:
                    task.is_cancelled = True
                    self._storage.save(task)
                    self._log(user_id, task_id, "Cancellation requested by user")
                    return True
        return False

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
        # try in-memory cache first
        with self._lock:
            if task_id in self._tasks:
                task = self._tasks[task_id]
                if task.user_id == user_id:
                    return task

        # load from storage
        return self._storage.load(task_id, user_id)

    def get_logs(self, task_id: str, user_id: str, tail: int = 100) -> list[str]:
        """Get task logs including any buffered (not yet flushed) logs.

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
            List of log entries (flushed + buffered).
        """
        # get flushed logs from storage
        flushed_logs = self._storage.load_logs(task_id, user_id, tail=10000)

        # get buffered logs (not yet flushed)
        buffered_logs = []
        with self._log_buffer_lock:
            buffer_key = f"{user_id}:{task_id}"
            if buffer_key in self._log_buffers:
                buffered_logs = self._log_buffers[buffer_key].copy()

        # combine and return last N
        all_logs = flushed_logs + buffered_logs
        return all_logs[-tail:] if len(all_logs) > tail else all_logs

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
        # get tasks from storage (disk)
        tasks_from_storage = self._storage.list_tasks(user_id)

        # merge with in-memory cache for running tasks (has live progress)
        with self._lock:
            result = []
            for task in tasks_from_storage:
                # if task is in memory, use in-memory version (has live progress)
                if task.key in self._tasks:
                    result.append(self._tasks[task.key])
                else:
                    result.append(task)
            return result
