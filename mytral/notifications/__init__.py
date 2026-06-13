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

"""Notification module for user notifications."""

from mytral.notifications._entities import NotificationEntity
from mytral.notifications._storage import NotificationStorage

# maximum number of notifications kept per user
MAX_NOTIFICATIONS = 10

# module-level in-memory store shared across all requests
store = NotificationStorage(max_notifications=MAX_NOTIFICATIONS)

# ensure re-exported symbols are recognized as used
__all__ = [
    "MAX_NOTIFICATIONS",
    "NotificationEntity",
    "NotificationStorage",
    "notify",
    "store",
]


def notify(user_id: str, category: str, message: str) -> None:
    """Create and store a notification for a user, trimming to max.

    Parameters
    ----------
    user_id : str
        User identifier.
    category : str
        Notification category (success, info, error, message).
    message : str
        Notification message text.

    """
    store.add(user_id=user_id, category=category, message=message)
