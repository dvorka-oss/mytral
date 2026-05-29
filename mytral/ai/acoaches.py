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
# along with this program. If not, see <http://www.gnu.org/licenses/>.
import dataclasses
import pathlib
import traceback

from mytral import loggers
from mytral import persistences

#
# AI coaches: chats
#


@dataclasses.dataclass
class ACoachMessage:
    """Single message in a coach chat conversation."""

    role: str  # "user" | "assistant"
    content: str
    ts: str  # ISO 8601
    status: str = "done"  # "done" | "pending" | "error"

    @staticmethod
    def from_dict(d: dict) -> "ACoachMessage":
        """Deserialize from dictionary.

        Parameters
        ----------
        d : dict
            Source dictionary.

        Returns
        -------
        ACoachMessage
            Deserialized instance.
        """
        return ACoachMessage(
            role=d.get("role", "user"),
            content=d.get("content", ""),
            ts=d.get("ts", ""),
            status=d.get("status", "done"),
        )

    def to_dict(self) -> dict:
        """Serialize to dictionary.

        Returns
        -------
        dict
            Serialized dictionary.
        """
        return {
            "role": self.role,
            "content": self.content,
            "ts": self.ts,
            "status": self.status,
        }


@dataclasses.dataclass
class ACoachChat:
    """A full conversation thread with an AI coach."""

    key: str
    coach_key: str
    title: str
    created_at: str
    messages: list[ACoachMessage]

    @staticmethod
    def from_dict(d: dict) -> "ACoachChat":
        """Deserialize from dictionary.

        Parameters
        ----------
        d : dict
            Source dictionary.

        Returns
        -------
        ACoachChat
            Deserialized instance.
        """
        return ACoachChat(
            key=d.get("key", ""),
            coach_key=d.get("coach_key", ""),
            title=d.get("title", ""),
            created_at=d.get("created_at", ""),
            messages=[ACoachMessage.from_dict(m) for m in d.get("messages", [])],
        )

    def to_dict(self) -> dict:
        """Serialize to dictionary.

        Returns
        -------
        dict
            Serialized dictionary.
        """
        return {
            "key": self.key,
            "coach_key": self.coach_key,
            "title": self.title,
            "created_at": self.created_at,
            "messages": [m.to_dict() for m in self.messages],
        }


#
# Persistence
#


def load_acoach_chats(user_id: str, data_dir: str) -> list:
    """Load AI coaching chats from JSON file.

    Parameters
    ----------
    user_id : str
        User identifier.
    data_dir : str
        Base data directory path.

    Returns
    -------
    list :
        List of ACoachChat objects, or empty list if file missing.
    """
    file_path = pathlib.Path(data_dir) / user_id / "user-ai-chats.json"
    if not file_path.exists():
        return []
    try:
        data = persistences.load_json(file_path)
        if not isinstance(data, list):
            logger: loggers.MytralLogger = loggers.MytralStructLogger()
            logger.warning(
                f"Invalid AI coach chats payload in '{file_path}':"
                f" expected list, got {type(data).__name__}"
            )
            return []
        return [ACoachChat.from_dict(c) for c in data]
    except Exception as exc:
        logger = loggers.MytralStructLogger()
        logger.error(
            f"Failed to load AI coach chats from '{file_path}':"
            f" {exc}\n{traceback.format_exc()}"
        )
        return []


def save_acoach_chats(user_id: str, data_dir: str, chats: list) -> None:
    """Save AI coaching chats to JSON file.

    Parameters
    ----------
    user_id : str
        User identifier.
    data_dir : str
        Base data directory path.
    chats : list
        List of ACoachChat objects.
    """
    file_path = pathlib.Path(data_dir) / user_id / "user-ai-chats.json"
    file_path.parent.mkdir(parents=True, exist_ok=True)
    persistences.save_json(file_path=file_path, data_dict=[c.to_dict() for c in chats])
