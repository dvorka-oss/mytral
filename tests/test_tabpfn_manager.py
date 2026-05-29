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

import datetime
import pathlib
import uuid

import pytest

from mytral import loggers
from mytral import tasks
from mytral.ml.icl import manager as icl_manager
from mytral.ml.icl import settings as icl_settings
from mytral.tasks.do import tabpfn_download


@pytest.mark.mytral
def test_get_status_returns_not_installed_when_tabpfn_missing(monkeypatch):
    """Test get_status() returns not_installed when tabpfn is not importable."""
    # GIVEN
    monkeypatch.setattr(icl_manager, "is_tabpfn_installed", lambda: False)

    # WHEN
    status = icl_manager.get_status()

    # THEN
    assert status == icl_settings.MODEL_STATUS_NOT_INSTALLED
    print("DONE: get_status returns not_installed when tabpfn is missing")


@pytest.mark.mytral
def test_get_status_returns_not_downloaded_when_installed_but_no_weights(monkeypatch):
    """Test get_status() returns not_downloaded when package is installed, but weights
    are absent.
    """
    # GIVEN
    monkeypatch.setattr(icl_manager, "is_tabpfn_installed", lambda: True)
    monkeypatch.setattr(icl_manager, "is_weights_cached", lambda: False)
    # reset any in-memory flags
    icl_manager._is_downloading = False
    icl_manager._download_failed = False

    # WHEN
    status = icl_manager.get_status()

    # THEN
    assert status == icl_settings.MODEL_STATUS_NOT_DOWNLOADED
    print("DONE: get_status returns not_downloaded when weights absent")


@pytest.mark.mytral
def test_get_status_returns_downloaded_when_weights_present(monkeypatch):
    """Test get_status() returns downloaded when package and weights are present."""
    # GIVEN
    monkeypatch.setattr(icl_manager, "is_tabpfn_installed", lambda: True)
    monkeypatch.setattr(icl_manager, "is_weights_cached", lambda: True)
    icl_manager._is_downloading = False
    icl_manager._download_failed = False

    # WHEN
    status = icl_manager.get_status()

    # THEN
    assert status == icl_settings.MODEL_STATUS_DOWNLOADED
    print("DONE: get_status returns downloaded when weights present")


@pytest.mark.mytral
def test_get_status_returns_downloading_while_in_progress(monkeypatch):
    """Test get_status() returns downloading while download thread is running."""
    # GIVEN
    monkeypatch.setattr(icl_manager, "is_tabpfn_installed", lambda: True)
    icl_manager._is_downloading = True
    icl_manager._download_failed = False

    # WHEN
    status = icl_manager.get_status()

    # THEN
    assert status == icl_settings.MODEL_STATUS_DOWNLOADING

    # cleanup
    icl_manager._is_downloading = False
    print("DONE: get_status returns downloading while thread active")


@pytest.mark.mytral
def test_get_status_returns_failed_after_download_error(monkeypatch):
    """Test get_status() returns failed after a download error."""
    # GIVEN
    monkeypatch.setattr(icl_manager, "is_tabpfn_installed", lambda: True)
    monkeypatch.setattr(icl_manager, "is_weights_cached", lambda: False)
    icl_manager._is_downloading = False
    icl_manager._download_failed = True
    icl_manager._download_error = "network error"

    # WHEN
    status = icl_manager.get_status()
    error = icl_manager.get_last_error()

    # THEN
    assert status == icl_settings.MODEL_STATUS_FAILED
    assert error == "network error"

    # cleanup
    icl_manager._download_failed = False
    icl_manager._download_error = ""
    print("DONE: get_status returns failed after download error")


@pytest.mark.mytral
def test_set_downloading_clears_failure_flags(monkeypatch):
    """Test set_downloading(True) resets previous failure state."""
    # GIVEN
    icl_manager._download_failed = True
    icl_manager._download_error = "previous error"

    # WHEN
    icl_manager.set_downloading(True)

    # THEN
    assert icl_manager.is_download_in_progress() is True
    assert icl_manager._download_failed is False
    assert icl_manager._download_error == ""
    # cleanup
    icl_manager.set_downloading(False)
    print("DONE: set_downloading(True) resets failure flags")


@pytest.mark.mytral
def test_set_failed_marks_failure_state():
    """Test set_failed() records error and clears downloading flag."""
    # GIVEN
    icl_manager.set_downloading(True)

    # WHEN
    icl_manager.set_failed("connection reset")

    # THEN
    assert icl_manager.is_download_in_progress() is False
    assert icl_manager._download_failed is True
    assert icl_manager._download_error == "connection reset"
    # cleanup
    icl_manager._download_failed = False
    icl_manager._download_error = ""
    print("DONE: set_failed records error state")


@pytest.mark.mytral
def test_storage_info_not_cached(tmp_path: pathlib.Path, monkeypatch):
    """Test storage_info() returns cached=False when weights dir does not exist."""
    # GIVEN
    monkeypatch.setattr(icl_manager, "_hf_cache_root", lambda: tmp_path)

    # WHEN
    info = icl_manager.storage_info()

    # THEN
    assert info["cached"] is False
    assert info["size_mb"] == 0.0
    print("DONE: storage_info returns cached=False when dir absent")


@pytest.mark.mytral
def test_storage_info_cached(tmp_path: pathlib.Path, monkeypatch):
    """Test storage_info() returns cached=True and correct size when both weight
    dirs exist.
    """
    # GIVEN — create both clf and reg cache dirs with snapshot files
    for dir_name in (icl_manager._HF_CACHE_DIR_CLF, icl_manager._HF_CACHE_DIR_REG):
        snapshots_dir = tmp_path / dir_name / "snapshots" / "abc123"
        snapshots_dir.mkdir(parents=True)
        (snapshots_dir / "model.bin").write_bytes(b"x" * 1024 * 250)  # 250 KB each

    monkeypatch.setattr(icl_manager, "_hf_cache_root", lambda: tmp_path)

    # WHEN
    info = icl_manager.storage_info()

    # THEN
    assert info["cached"] is True
    assert info["size_mb"] > 0
    print("DONE: storage_info returns cached=True with correct size")


@pytest.mark.mytral
def test_delete_weights_returns_false_when_not_present(
    tmp_path: pathlib.Path, monkeypatch
):
    """Test delete_weights() returns False when there are no weights to delete."""
    # GIVEN
    monkeypatch.setattr(icl_manager, "_hf_cache_root", lambda: tmp_path)

    # WHEN
    result = icl_manager.delete_weights()

    # THEN
    assert result is False
    print("DONE: delete_weights returns False when no weights present")


@pytest.mark.mytral
def test_delete_weights_removes_directory(tmp_path: pathlib.Path, monkeypatch):
    """Test delete_weights() removes both weight directories and returns True."""
    # GIVEN — create both clf and reg dirs
    for dir_name in (icl_manager._HF_CACHE_DIR_CLF, icl_manager._HF_CACHE_DIR_REG):
        weights_dir = tmp_path / dir_name
        weights_dir.mkdir()
        (weights_dir / "dummy.bin").write_bytes(b"data")

    monkeypatch.setattr(icl_manager, "_hf_cache_root", lambda: tmp_path)

    # WHEN
    result = icl_manager.delete_weights()

    # THEN
    assert result is True
    for dir_name in (icl_manager._HF_CACHE_DIR_CLF, icl_manager._HF_CACHE_DIR_REG):
        assert not (tmp_path / dir_name).exists()
    print("DONE: delete_weights removes directories and returns True")


@pytest.mark.mytral
def test_is_tabpfn_installed_returns_false_when_sklearn_missing(monkeypatch):
    """Test is_tabpfn_installed() returns False when sklearn is not importable."""
    import importlib

    # GIVEN — tabpfn finds a spec but sklearn does not
    real_find_spec = importlib.util.find_spec

    def patched_find_spec(name):
        if name == "sklearn":
            return None
        return real_find_spec(name)

    monkeypatch.setattr(importlib.util, "find_spec", patched_find_spec)

    # WHEN
    result = icl_manager.is_tabpfn_installed()

    # THEN
    assert result is False
    print("DONE: is_tabpfn_installed returns False when sklearn is absent")


@pytest.mark.mytral
def test_is_download_in_progress_returns_current_flag():
    """Test is_download_in_progress() reflects the module-level flag."""
    # GIVEN
    icl_manager._is_downloading = False

    # WHEN / THEN
    assert icl_manager.is_download_in_progress() is False

    icl_manager.set_downloading(True)
    assert icl_manager.is_download_in_progress() is True

    icl_manager.set_downloading(False)
    assert icl_manager.is_download_in_progress() is False
    print("DONE: is_download_in_progress reflects set_downloading flag")


@pytest.mark.mytral
def test_tabpfn_download_task_aborts_when_not_installed(monkeypatch):
    """Test TabPFNDownloadTask raises RuntimeError when tabpfn is not installed."""

    # GIVEN — tabpfn not installed, no weights cached
    monkeypatch.setattr(icl_manager, "is_weights_cached", lambda: False)
    monkeypatch.setattr(icl_manager, "is_download_in_progress", lambda: False)
    monkeypatch.setattr(icl_manager, "is_tabpfn_installed", lambda: False)

    task_entity = tasks.TaskEntity(
        key=str(uuid.uuid4()),
        user_id="test_user",
        task_type=tabpfn_download.TabPFNDownloadTask.TASK_TYPE,
        status=tasks.TaskStatus.QUEUED,
        created_at=datetime.datetime.now(),
        started_at=None,
        completed_at=None,
        error_message=None,
        error_type=None,
        error_traceback=None,
        progress=0,
        parameters={},
    )
    logger = loggers.MytralPrintLogger()

    # WHEN
    task = tabpfn_download.TabPFNDownloadTask(
        task_entity=task_entity,
        logger=logger,
        log_callback=lambda user_id, task_id, message: print(message),
    )

    # THEN
    with pytest.raises(RuntimeError, match="tabpfn package is not installed"):
        task.execute()
    print("DONE: TabPFNDownloadTask raises RuntimeError when package missing")


@pytest.mark.mytral
def test_tabpfn_download_task_skips_when_weights_cached(monkeypatch):
    """Test TabPFNDownloadTask completes early when weights already cached."""
    # GIVEN — tabpfn installed and weights already present
    monkeypatch.setattr(icl_manager, "is_tabpfn_installed", lambda: True)
    monkeypatch.setattr(icl_manager, "is_weights_cached", lambda: True)

    task_entity = tasks.TaskEntity(
        key=str(uuid.uuid4()),
        user_id="test_user",
        task_type=tabpfn_download.TabPFNDownloadTask.TASK_TYPE,
        status=tasks.TaskStatus.QUEUED,
        created_at=datetime.datetime.now(),
        started_at=None,
        completed_at=None,
        error_message=None,
        error_type=None,
        error_traceback=None,
        progress=0,
        parameters={},
    )
    logger = loggers.MytralPrintLogger()

    # WHEN
    task = tabpfn_download.TabPFNDownloadTask(
        task_entity=task_entity,
        logger=logger,
        log_callback=lambda user_id, task_id, message: print(message),
    )
    task.execute()

    # THEN — completes at 100% without error
    assert task_entity.progress == 100
    print("DONE: TabPFNDownloadTask exits early when weights already cached")


@pytest.mark.mytral
def test_is_weights_cached_false_when_snapshots_empty(
    tmp_path: pathlib.Path, monkeypatch
):
    """Test is_weights_cached() returns False when snapshots dir is empty."""
    # GIVEN — only clf dir exists with empty snapshots; reg dir absent
    weights_dir = tmp_path / icl_manager._HF_CACHE_DIR_CLF
    snapshots_dir = weights_dir / "snapshots"
    snapshots_dir.mkdir(parents=True)

    monkeypatch.setattr(icl_manager, "_hf_cache_root", lambda: tmp_path)

    # WHEN
    result = icl_manager.is_weights_cached()

    # THEN
    assert result is False
    print("DONE: is_weights_cached returns False when only one repo is present")


@pytest.mark.mytral
def test_is_weights_cached_true_when_snapshot_exists(
    tmp_path: pathlib.Path, monkeypatch
):
    """Test is_weights_cached() returns True when both snapshot dirs exist."""
    # GIVEN — create both clf and reg dirs with snapshot content
    for dir_name in (icl_manager._HF_CACHE_DIR_CLF, icl_manager._HF_CACHE_DIR_REG):
        snapshot_dir = tmp_path / dir_name / "snapshots" / "v1"
        snapshot_dir.mkdir(parents=True)
        (snapshot_dir / "model.bin").write_bytes(b"data")

    monkeypatch.setattr(icl_manager, "_hf_cache_root", lambda: tmp_path)

    # WHEN
    result = icl_manager.is_weights_cached()

    # THEN
    assert result is True
    print("DONE: is_weights_cached returns True when both snapshot dirs exist")
