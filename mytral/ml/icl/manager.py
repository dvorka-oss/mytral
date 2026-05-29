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
"""TabPFN model lifecycle management: download, status tracking, deletion."""

import pathlib
import shutil
import threading

import structlog

from mytral.ml.icl import settings as icl_settings

_logger = structlog.get_logger()

# HuggingFace repo IDs for TabPFN v2 (Apache 2.0 weights)
_HF_REPO_CLF = "Prior-Labs/TabPFN-v2-clf"
_HF_REPO_REG = "Prior-Labs/TabPFN-v2-reg"
# corresponding HF hub cache directory names
_HF_CACHE_DIR_CLF = "models--Prior-Labs--TabPFN-v2-clf"
_HF_CACHE_DIR_REG = "models--Prior-Labs--TabPFN-v2-reg"

# module-level download state (updated by the TabPFNDownloadTask)
_status_lock = threading.Lock()
_is_downloading: bool = False
_download_failed: bool = False
_download_error: str = ""


def _hf_cache_root() -> pathlib.Path:
    """Return the HuggingFace hub cache root directory.

    Returns
    -------
    pathlib.Path
        Path to HuggingFace hub cache directory.
    """
    import os

    hf_home = os.environ.get("HF_HOME", "")
    if hf_home:
        return pathlib.Path(hf_home) / "hub"
    return pathlib.Path.home() / ".cache" / "huggingface" / "hub"


def is_tabpfn_installed() -> bool:
    """Return True if tabpfn and all required dependencies are importable.

    Verifies both ``tabpfn`` and ``sklearn`` (scikit-learn) are importable.
    A common failure mode is the server being started before
    ``uv sync --group ml`` completes, leaving tabpfn's spec visible but
    sklearn absent.

    Returns
    -------
    bool
        True when all ML dependencies are available in the current environment.
    """
    try:
        import importlib

        if importlib.util.find_spec("tabpfn") is None:
            return False
        if importlib.util.find_spec("sklearn") is None:
            return False
        return True
    except Exception:
        return False


def is_weights_cached() -> bool:
    """Return True if both TabPFN v2 classifier and regressor weights are cached.

    Returns
    -------
    bool
        True when both weight directories contain at least one snapshot.
    """
    cache_root = _hf_cache_root()
    for dir_name in (_HF_CACHE_DIR_CLF, _HF_CACHE_DIR_REG):
        weights_dir = cache_root / dir_name
        if not weights_dir.is_dir():
            return False
        snapshots = weights_dir / "snapshots"
        if not snapshots.is_dir() or not any(snapshots.iterdir()):
            return False
    return True


def get_status() -> str:
    """Return the current model status as a status constant.

    Status is computed from filesystem state and in-memory download flags.
    Possible values are the ``MODEL_STATUS_*`` constants from
    ``mytral.ml.icl.settings``.

    Returns
    -------
    str
        One of: not_installed, not_downloaded, downloading, downloaded, failed.
    """
    global _is_downloading, _download_failed

    if not is_tabpfn_installed():
        return icl_settings.MODEL_STATUS_NOT_INSTALLED

    with _status_lock:
        if _is_downloading:
            return icl_settings.MODEL_STATUS_DOWNLOADING
        if _download_failed:
            return icl_settings.MODEL_STATUS_FAILED

    if is_weights_cached():
        return icl_settings.MODEL_STATUS_DOWNLOADED

    return icl_settings.MODEL_STATUS_NOT_DOWNLOADED


def get_last_error() -> str:
    """Return the last download error message, or empty string.

    Returns
    -------
    str
        Last error message or empty string.
    """
    return _download_error


def is_download_in_progress() -> bool:
    """Return True if a weight download is currently in progress.

    Returns
    -------
    bool
        True when a download task is actively running.
    """
    with _status_lock:
        return _is_downloading


def set_downloading(value: bool) -> None:
    """Set the downloading flag (called by TabPFNDownloadTask).

    Parameters
    ----------
    value : bool
        True when download starts; False when it finishes.
    """
    global _is_downloading, _download_failed, _download_error

    with _status_lock:
        _is_downloading = value
        if value:
            # clear any previous failure when a new download begins
            _download_failed = False
            _download_error = ""


def set_failed(error: str) -> None:
    """Mark download as failed (called by TabPFNDownloadTask on exception).

    Parameters
    ----------
    error : str
        Human-readable error description.
    """
    global _is_downloading, _download_failed, _download_error

    with _status_lock:
        _is_downloading = False
        _download_failed = True
        _download_error = error
        _logger.error("tabpfn: model weight download failed", error=error)


def storage_info() -> dict:
    """Return storage usage information for the cached weights.

    Returns
    -------
    dict
        Dictionary with keys: ``cached`` (bool), ``path`` (str),
        ``size_mb`` (float).
    """
    cache_root = _hf_cache_root()
    total_bytes = 0
    paths = []
    for dir_name in (_HF_CACHE_DIR_CLF, _HF_CACHE_DIR_REG):
        weights_dir = cache_root / dir_name
        paths.append(str(weights_dir))
        if weights_dir.is_dir():
            total_bytes += sum(
                f.stat().st_size for f in weights_dir.rglob("*") if f.is_file()
            )
    cached = is_weights_cached()
    return {
        "cached": cached,
        "path": str(cache_root),
        "size_mb": round(total_bytes / (1024 * 1024), 1),
    }


def delete_weights() -> bool:
    """Delete locally cached TabPFN v2 model weights.

    Returns
    -------
    bool
        True if at least one weights directory was deleted, False otherwise.
    """
    cache_root = _hf_cache_root()
    deleted_any = False
    for dir_name in (_HF_CACHE_DIR_CLF, _HF_CACHE_DIR_REG):
        weights_dir = cache_root / dir_name
        if weights_dir.is_dir():
            shutil.rmtree(weights_dir)
            _logger.info("tabpfn: cached weights deleted", path=str(weights_dir))
            deleted_any = True
    return deleted_any
