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

import multiprocessing
import os
import pathlib
import uuid

from mytral import loggers


class SubtaskBulldozer:
    """Method:

    1. create filesystem sandbox w/ make_sandbox()
    2. copy job data to sandbox
    3. prepare function which can process data as job_function(sandbox_dir)
       and expect that job will read all instructions and input from its sandbox
    4. run tasks w/ run(job_function)
    5. post-process the results

    """

    DIR_INPUT = "input"
    DIR_OUTPUT = "output"
    DIR_SUBTASKS = "subtasks"
    DIR_WORK = "work"

    def __init__(
        self,
        usr_task_dir: pathlib.Path,
        subtask_key: str = "",
        logger: loggers.MytralLogger | None = None,
    ):
        """Constructor.

        Parameters
        ----------
        usr_task_dir : pathlib.Path
          Particular task directory in user's tasks directory.

        """
        self.logger = logger or loggers.MytralPrintLogger()

        self.usr_task_dir = usr_task_dir

        self.subtask_key = subtask_key or f"{uuid.uuid4()}"

        self.subtasks_dir = self.usr_task_dir / self.DIR_SUBTASKS
        self.subtask_dir = self.subtasks_dir / self.subtask_key

        self._worker_to_cpu = 2

    @staticmethod
    def _cpu_count() -> int:
        return max(1, os.cpu_count() or 1)

    def _workers_count(self):
        return max(1, SubtaskBulldozer._cpu_count() // self._worker_to_cpu)

    def make_sandbox(self) -> list[pathlib.Path]:
        """Create subtask sandbox:

        $MYTRAL_DATA_DIR/data/[user UUID]/tasks/task-[task UUID]/
          subtasks/
            [subtasks UUID]/            ... new subtask w/ per CPU core jobs
                [job SEQUENCE NUMBER]/
                  job.json              ... metadata - see task JSON metadata
                  job.log               ... log - see task log
                  input/
                    ...
                  work/
                    ...
                  output/
                    ...
        """
        job_dirs = []

        job_workers_count = self._workers_count()
        for i in range(job_workers_count):
            job_dir_name = f"job-{i}"
            job_dir = self.subtask_dir / job_dir_name
            input_dir = job_dir / self.DIR_INPUT
            work_dir = job_dir / self.DIR_WORK
            output_dir = job_dir / self.DIR_OUTPUT

            input_dir.mkdir(parents=True, exist_ok=True)
            work_dir.mkdir(parents=True, exist_ok=True)
            output_dir.mkdir(parents=True, exist_ok=True)

            job_dirs.append(job_dir)

        return job_dirs

    def run(self, job_dirs: list[pathlib.Path], job_function) -> list[pathlib.Path]:
        """Run the bulldozer subtask.

        This method should be overridden by subclasses to implement the actual
        subtask logic. The base implementation does nothing.

        Parameters
        ----------
        job_dirs : list[pathlib.Path]
          Paths to job sandboxed
        job_function : function
          Function to run for each job, which should accept a job key and a job
          directory as parameters.

        Returns
        -------
        list[pathlib.Path]
          Sandboxes paths.

        """
        job_processes = []
        for e, job_dir in enumerate(job_dirs):
            job_key = e + 1
            job_process = multiprocessing.Process(
                target=job_function, args=(job_key, job_dir)
            )
            job_processes.append(job_process)

            # RUN the job
            job_process.start()
            self.logger.info(f"  Subtask {self.subtask_key}: job {job_key} started...")
        self.logger.info(f"Subtask {self.subtask_key}: ALL jobs started")

        # WAIT for jobs to finish
        for job_process in job_processes:
            job_process.join()

        self.logger.info(f"Subtask {self.subtask_key}: ALL jobs DONE")
        return job_dirs
