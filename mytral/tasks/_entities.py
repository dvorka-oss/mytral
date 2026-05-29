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

"""Task system entities - dataclasses and enums for async tasks."""

import dataclasses
import datetime
import enum


class TaskStatus(enum.Enum):
    """Task execution status."""

    QUEUED = "queued"
    RUNNING = "running"
    COMPLETED = "completed"
    FAILED = "failed"


@dataclasses.dataclass
class TaskEntity:
    """Task entity with metadata and state.

    Notes
    -----
    Logs are stored separately in .log files, not in this entity.
    This keeps JSON files small and fast to read/write.
    """

    key: str  # UUID
    user_id: str
    task_type: str  # "strava_sync_new", "hello_world", etc.
    status: TaskStatus
    created_at: datetime.datetime
    started_at: datetime.datetime | None
    completed_at: datetime.datetime | None

    # error handling - enhanced error capture
    error_message: str | None  # human-readable error message
    error_type: str | None  # exception class name (e.g., "StravaAPIError")
    error_traceback: str | None  # full Python traceback for debugging

    progress: int  # 0-100 percentage

    parameters: dict  # task-specific parameters

    # human-friendly task label shown in UI (falls back to task_type formatting)
    task_display_name: str = ""

    # cancellation support - flag for cooperative cancellation
    is_cancelled: bool = False

    # used to create UI button allowing user to take him to page where are task results
    result_route: str = "home"
    result_route_kwargs: dict[str, str | int] = dataclasses.field(default_factory=dict)

    @property
    def display_name(self) -> str:
        """Return human-friendly task name with a safe fallback."""
        if self.task_display_name:
            return self.task_display_name
        return self.task_type.replace("_", " ").title()

    def to_dict(self) -> dict:
        """Convert to dictionary for JSON serialization.

        Returns
        -------
        dict
            Dictionary representation with datetime objects converted to ISO format.
        """
        data = dataclasses.asdict(self)
        # convert enum to string
        data["status"] = self.status.value
        # convert datetime objects to ISO format strings
        for field in ["created_at", "started_at", "completed_at"]:
            if data[field] is not None:
                data[field] = data[field].isoformat()
        return data

    @classmethod
    def from_dict(cls, data: dict) -> "TaskEntity":
        """Create TaskEntity from dictionary.

        Parameters
        ----------
        data : dict
            Dictionary with task data from JSON.

        Returns
        -------
        TaskEntity
            Reconstructed task entity.
        """
        # convert status string to enum
        if isinstance(data.get("status"), str):
            data["status"] = TaskStatus(data["status"])

        # convert ISO format strings to datetime objects
        for field in ["created_at", "started_at", "completed_at"]:
            if data.get(field) is not None and isinstance(data[field], str):
                data[field] = datetime.datetime.fromisoformat(data[field])

        # backward compatibility: required_locks was removed when the task
        # system was simplified to a per-user mutex
        data.pop("required_locks", None)

        return cls(**data)


class TaskCancelledException(Exception):
    """Exception raised when task is canceled."""

    pass
