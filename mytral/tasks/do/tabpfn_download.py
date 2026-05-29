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
"""TabPFN model weight download task."""

from mytral import tasks
from mytral.ml.icl import manager as icl_manager


class TabPFNDownloadTask(tasks.TaskBase):
    """Downloads TabPFN v2 model weights from HuggingFace Hub.

    Replaces the bare ``threading.Thread`` approach in
    ``mytral.ml.icl.manager.start_download()`` with a first-class task that
    surfaces progress, logs, and errors in the standard tasks UI at
    ``/app/tasks``.

    Checks made before initiating the HTTP download:

    1. ``tabpfn`` package is importable.
    2. ``scikit-learn`` (``sklearn``) is importable — a common missing dep when
       the server was started before ``uv sync --group ml`` completed.
    3. Weights are not already cached.
    4. A download is not already in progress.
    """

    TASK_TYPE = "tabpfn_download"
    TASK_DISPLAY_NAME = "TabPFN — Download Model Weights"

    def __init__(
        self,
        task_entity: tasks.TaskEntity,
        logger,
        log_callback,
        config=None,
        dataset=None,
        blobstore=None,
        enc_key="",
    ):
        super().__init__(
            task_entity=task_entity,
            logger=logger,
            log_callback=log_callback,
            config=config,
            dataset=dataset,
            blobstore=blobstore,
            enc_key=enc_key,
        )

    def execute(self) -> None:
        """Run the TabPFN weight download.

        Raises
        ------
        RuntimeError
            If a pre-condition check fails (package missing, already running, …).
        Exception
            If the HuggingFace download itself fails.
        """
        self.log(f"[{TabPFNDownloadTask.TASK_DISPLAY_NAME}] starting")
        self.update_progress(5)

        # check 1 — skip if weights already present (fast path, no import needed)
        if icl_manager.is_weights_cached():
            self.log("Model weights are already cached — nothing to do.")
            self.update_progress(100)
            return

        # check 2 — guard against concurrent downloads
        if icl_manager.is_download_in_progress():
            self.log(
                "A download is already in progress (possibly from another user). "
                "Please wait for it to finish."
            )
            self.update_progress(100)
            return

        # check 3 — tabpfn package and deps (including sklearn) must be importable
        if not icl_manager.is_tabpfn_installed():
            msg = (
                "tabpfn package is not installed. "
                "Run: uv sync --group ml  then restart the server."
            )
            self.log(f"ERROR: {msg}")
            raise RuntimeError(msg)

        # mark in-progress so the status card on the settings page reflects the
        # correct state while the task is running
        icl_manager.set_downloading(True)
        self.update_progress(10)
        self.log("Pre-flight checks passed. Starting HuggingFace weight download…")
        self.log(
            "Downloading TabPFN v2 weights (~100 MB) from HuggingFace Hub. "
            "This may take a few minutes depending on your connection speed."
        )

        try:
            self.check_cancellation()

            from huggingface_hub import snapshot_download

            self.log(
                "Downloading TabPFN v2 classifier weights (Prior-Labs/TabPFN-v2-clf)…"
            )
            self.update_progress(30)
            snapshot_download(icl_manager._HF_REPO_CLF)

            self.check_cancellation()

            self.log(
                "Downloading TabPFN v2 regressor weights (Prior-Labs/TabPFN-v2-reg)…"
            )
            self.update_progress(65)
            snapshot_download(icl_manager._HF_REPO_REG)

            self.update_progress(95)
            icl_manager.set_downloading(False)
            self.log("Model weights downloaded and verified successfully.")
            self.log(
                f"Cache location: {icl_manager.storage_info().get('path', 'unknown')}"
            )
            self.update_progress(100)
            self.log(f"[{TabPFNDownloadTask.TASK_DISPLAY_NAME}] DONE")
        except Exception as exc:
            icl_manager.set_failed(str(exc))
            self.log(f"ERROR: download failed — {exc}")
            raise


tasks.tasks_registry.register_task(TabPFNDownloadTask)
