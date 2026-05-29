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
import time
from typing import Self

from mytral import loggers


class Profiler:
    def __init__(self, logger: loggers.MytralLogger | None = None):
        self._start = 0
        self._end = 0
        self.duration = 0
        self.logger = logger or loggers.MytralStructLogger()

    def start(self) -> Self:
        self._start = time.perf_counter()
        return self

    def stop(self, do_log: bool = True) -> float:
        self._end = time.perf_counter()
        self.duration = self._end - self._start
        if do_log:
            self.print()
        return self.duration

    def print(self, msg: str = "the action") -> None:
        self.logger.info(f"[Profiling] duration of {msg}: {self.duration}")
