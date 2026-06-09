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

import pathlib
import time

import pytest

from mytral.tasks import bulldozer


@pytest.mark.mytral
def test_bulldozer(tmp_path: pathlib.Path):
    #
    # GIVEN
    #

    def _job_fun(job_key: str, job_dir: pathlib.Path):
        print(f"{job_key} @ {job_dir}: alive...")
        for i in range(3):
            print(f"{job_key} @ {job_dir}: STEP {i}")
            time.sleep(1.0)
        print(f"{job_key} @ {job_dir}: DONE")

    #
    # WHEN
    #
    bzz = bulldozer.SubtaskBulldozer(usr_task_dir=tmp_path)
    job_dirs = bzz.make_sandbox()
    bzz.run(job_dirs=job_dirs, job_function=_job_fun)

    #
    # THEN
    #
    print(f"Test finished the run in: file://{tmp_path}")
