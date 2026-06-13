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

"""Notification storage - in-memory per-user notification lists."""

import threading

from mytral.notifications import _entities


class NotificationStorage:
    """In-memory notification store, keyed by user ID."""

    def __init__(self, max_notifications: int = 10):
        """Initialize notification storage.

        Parameters
        ----------
        max_notifications : int
            Maximum number of notifications to keep per user.

        """
        self.max_notifications = max_notifications
        # per-user notification lists: dict[str, list[NotificationEntity]]
        self._store: dict[str, list[_entities.NotificationEntity]] = {}
        self._store_lock = threading.RLock()

    def add(
        self, user_id: str, category: str, message: str
    ) -> _entities.NotificationEntity:
        """Add a new notification for a user, trimming to max.

        Parameters
        ----------
        user_id : str
            User identifier.
        category : str
            Notification category (success, info, error, message).
        message : str
            Notification message text.

        Returns
        -------
        NotificationEntity
            The newly created notification.

        """
        notification = _entities.NotificationEntity.create(
            user_id=user_id,
            category=category,
            message=message,
        )

        with self._store_lock:
            if user_id not in self._store:
                self._store[user_id] = []
            # prepend newest, keep within max
            notifs = self._store[user_id]
            notifs.insert(0, notification)
            if len(notifs) > self.max_notifications:
                self._store[user_id] = notifs[: self.max_notifications]

        return notification

    def list(self, user_id: str) -> list[_entities.NotificationEntity]:
        """List all notifications for a user, sorted by newest first.

        Parameters
        ----------
        user_id : str
            User identifier.

        Returns
        -------
        list[NotificationEntity]
            List of notification entities, sorted by creation time (newest first).

        """
        with self._store_lock:
            notifs = self._store.get(user_id, [])
        return list(notifs)  # return a copy

    def get_count(self, user_id: str) -> int:
        """Get the number of notifications for a user.

        Parameters
        ----------
        user_id : str
            User identifier.

        Returns
        -------
        int
            Number of notifications.

        """
        with self._store_lock:
            return len(self._store.get(user_id, []))

    def clear_all(self, user_id: str) -> int:
        """Delete all notifications for a user.

        Parameters
        ----------
        user_id : str
            User identifier.

        Returns
        -------
        int
            Number of notifications deleted.

        """
        with self._store_lock:
            deleted_count = len(self._store.get(user_id, []))
            self._store.pop(user_id, None)
        return deleted_count
