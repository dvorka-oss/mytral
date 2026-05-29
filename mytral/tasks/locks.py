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

"""Per-user task mutex — at most one task may run per user at any time."""

import threading


class UserTaskLock:
    """Ensures at most one task runs concurrently per user.

    Any running task places the user's account in read-only mode.
    Write operations (guarded by sync_guard middleware) are rejected
    while this lock is held.

    Different users are fully independent and can run tasks concurrently.
    """

    def __init__(self):
        """Initialize the user task lock."""
        self._locked_users: set[str] = set()
        self._lock = threading.Lock()

    def acquire(self, user_id: str) -> bool:
        """Attempt to acquire the task lock for a user.

        Parameters
        ----------
        user_id : str
            User identifier.

        Returns
        -------
        bool
            True if the lock was acquired, False if a task is already running
            for this user.
        """
        with self._lock:
            if user_id in self._locked_users:
                return False
            self._locked_users.add(user_id)
            return True

    def release(self, user_id: str) -> None:
        """Release the task lock for a user.

        Parameters
        ----------
        user_id : str
            User identifier.
        """
        with self._lock:
            self._locked_users.discard(user_id)

    def is_locked(self, user_id: str) -> bool:
        """Return True if a task is currently running for this user.

        Parameters
        ----------
        user_id : str
            User identifier.

        Returns
        -------
        bool
            True if locked (task running), False otherwise.
        """
        with self._lock:
            return user_id in self._locked_users
