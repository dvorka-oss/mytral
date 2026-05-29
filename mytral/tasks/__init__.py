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

"""MyTraL asynchronous task system."""

from mytral.tasks._base import TaskBase
from mytral.tasks._entities import TaskCancelledException
from mytral.tasks._entities import TaskEntity
from mytral.tasks._entities import TaskStatus
from mytral.tasks.executor import MytralTaskRegistry
from mytral.tasks.executor import ResourceLockError
from mytral.tasks.executor import TaskExecutor
from mytral.tasks.executor import tasks_registry
from mytral.tasks.locks import UserTaskLock
from mytral.tasks.manager import TaskManager
from mytral.tasks.storage import TaskStorage

__all__ = [
    "MytralTaskRegistry",
    "ResourceLockError",
    "TaskBase",
    "TaskCancelledException",
    "TaskEntity",
    "TaskExecutor",
    "TaskManager",
    "TaskStatus",
    "TaskStorage",
    "UserTaskLock",
    "tasks_registry",
]
