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

"""Notification entities - dataclasses for persistent user notifications."""

import dataclasses
import datetime
import uuid


@dataclasses.dataclass
class NotificationEntity:
    """A single user notification.

    Notes
    -----
    Stored as a JSON file per notification in the user's notifications directory.
    """

    key: str  # UUID
    user_id: str
    category: str  # success, info, error, message
    message: str
    created_at: datetime.datetime

    @classmethod
    def create(cls, user_id: str, category: str, message: str) -> "NotificationEntity":
        """Create a new notification with auto-generated key and timestamp.

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
            New notification entity.

        """
        return cls(
            key=str(uuid.uuid4()),
            user_id=user_id,
            category=category,
            message=message,
            created_at=datetime.datetime.now(),
        )

    def to_dict(self) -> dict:
        """Convert to dictionary for JSON serialization.

        Returns
        -------
        dict
            Dictionary representation with datetime as ISO format.

        """
        data = dataclasses.asdict(self)
        data["created_at"] = self.created_at.isoformat()
        return data

    @classmethod
    def from_dict(cls, data: dict) -> "NotificationEntity":
        """Create NotificationEntity from dictionary.

        Parameters
        ----------
        data : dict
            Dictionary with notification data from JSON.

        Returns
        -------
        NotificationEntity
            Reconstructed notification entity.

        """
        if isinstance(data.get("created_at"), str):
            data["created_at"] = datetime.datetime.fromisoformat(data["created_at"])
        return cls(**data)
