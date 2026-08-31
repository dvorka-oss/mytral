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

"""Parser for the Polar Flow GDPR "Download your data" export.

The account.polar.com "Download your data" export is a ZIP of per-training JSON files
(``training-session-*.json``). This module normalizes each training session into the
same shape as a Polar AccessLink exercise summary so that the single
``PolarFlowActivitiesImportPlugin`` mapping is reused for both channels (DRY).

The historical export is the authoritative source of data recorded BEFORE the AccessLink
API was authorized (the API cannot backfill history). See ``POLAR_FLOW.md``.
"""

import collections
import concurrent.futures
import functools
import json
import multiprocessing
import os
import pathlib
import zipfile

from mytral import app_logger
from mytral.integrations import icommons

# training-session file name marker inside the export ZIP
_SESSION_FILE_MARKER = "training-session"

# parse ZIP entries across processes only above this many session files; below it
# the process-startup overhead outweighs the gain and serial parsing is used
_PARALLEL_MIN_FILES = 100


def _first(source: dict, *keys, default=None):
    """Return the first present, non-empty value among *keys* in *source*."""
    for key in keys:
        if key in source and source[key] not in (None, ""):
            return source[key]
    return default


def _millis_to_iso_duration(millis) -> str:
    """Convert integer milliseconds into an ISO-8601 duration like ``PT1H2M3S``."""
    try:
        total_seconds = int(millis) // 1000
    except (TypeError, ValueError):
        return ""
    if total_seconds <= 0:
        return ""
    hours, remainder = divmod(total_seconds, 3600)
    minutes, seconds = divmod(remainder, 60)
    return f"PT{hours}H{minutes}M{seconds}S"


def _identifier(source: dict) -> str:
    """Return the Polar ``identifier.id`` (GDPR export) as a string, or ``""``."""
    identifier = source.get("identifier")
    if isinstance(identifier, dict):
        return str(identifier.get("id", "") or "")
    return str(_first(source, "id", default="") or "")


def _normalize_exercise(exercise: dict, session: dict) -> dict | None:
    """Normalize one export exercise/session dict into an AccessLink-summary shape.

    The GDPR export uses camelCase millisecond/meter fields and a numeric ``sport``
    id, so this maps them onto the same summary keys the AccessLink API produces:
    an ISO-8601 ``duration``, integer ``distance`` metres, ``heart-rate`` averages,
    and a ``detailed-sport-info`` name resolved via ``icommons.polar_flow_sport_name``.
    """
    start_time = _first(exercise, "startTime", "start-time", default="") or _first(
        session, "startTime", "start-time", default=""
    )
    # sport lives at both exercise and session level as {"id": ...}; resolve to a name
    sport = icommons.polar_flow_sport_name(
        _first(exercise, "sport", default=None)
        or _first(session, "sport", default=None)
    )
    if not start_time and not sport:
        return None

    # HR summary is carried at the session level (hrAvg/hrMax), 0 meaning "no sensor"
    hr_avg = _first(session, "hrAvg", default=0) or 0
    hr_max = _first(session, "hrMax", default=0) or 0

    # duration/distance/calories: exercise value first, session as fallback
    duration_millis = _first(exercise, "durationMillis", default=None) or _first(
        session, "durationMillis", default=None
    )
    distance_m = _first(exercise, "distanceMeters", default=None)
    if distance_m is None:
        distance_m = _first(session, "distanceMeters", default=0) or 0
    calories = _first(exercise, "calories", "kiloCalories", default=None)
    if calories is None:
        calories = _first(session, "calories", default=0) or 0

    # ascent (elevation gain) is only at the exercise level
    ascent_m = _first(exercise, "ascentMeters", default=0) or 0

    # normalize the start time to seconds precision (drop any milliseconds/offset)
    start_time_norm = str(start_time)[:19]

    # src_key: prefer the Polar identifier, else a stable key derived from start time
    src_id = _identifier(exercise) or _identifier(session)
    if not src_id:
        src_id = "".join(ch for ch in start_time_norm if ch.isdigit())

    return {
        "id": src_id,
        "name": _first(session, "name", default="") or "",
        "start-time": start_time_norm,
        "duration": _millis_to_iso_duration(duration_millis),
        "distance": int(distance_m or 0),
        "calories": int(calories or 0),
        "heart-rate": {"average": int(hr_avg or 0), "maximum": int(hr_max or 0)},
        "sport": sport,
        "detailed-sport-info": sport,
        "elevation-gain": int(ascent_m or 0),
    }


def _normalize_session_json(data: dict) -> list[dict]:
    """Normalize one training-session JSON document into exercise summaries."""
    if not isinstance(data, dict):
        return []
    exercises = data.get("exercises")
    if isinstance(exercises, list) and exercises:
        normalized = [
            _normalize_exercise(exercise=ex, session=data) for ex in exercises
        ]
    else:
        # some exports carry the session itself as the exercise
        normalized = [_normalize_exercise(exercise=data, session=data)]
    return [item for item in normalized if item]


def _is_session_file(name: str) -> bool:
    """Return True for a training-session JSON file inside the export."""
    lowered = name.lower()
    return _SESSION_FILE_MARKER in lowered and lowered.endswith(".json")


def _raw_sport_id(session: dict) -> str:
    """Return the raw Polar sport id from a session dict, for coverage reporting."""
    sport = session.get("sport") if isinstance(session, dict) else None
    if isinstance(sport, dict):
        return str(sport.get("id", "") or "")
    return str(sport or "")


def _normalize_docs(docs) -> tuple[list[dict], collections.Counter]:
    """Normalize an iterable of session docs into (summaries, sport-id histogram)."""
    summaries: list[dict] = []
    sport_ids: collections.Counter = collections.Counter()
    for data in docs:
        raw_id = _raw_sport_id(data)
        if raw_id:
            sport_ids[raw_id] += 1
        summaries.extend(_normalize_session_json(data))
    return summaries, sport_ids


def _iter_zip_docs(zip_path: str, names: list[str]):
    """Yield parsed JSON docs for the given entry *names* of a ZIP archive."""
    with zipfile.ZipFile(zip_path) as archive:
        for name in names:
            try:
                with archive.open(name) as handle:
                    yield json.load(handle)
            except (json.JSONDecodeError, OSError):
                continue


def _iter_dir_docs(path: pathlib.Path):
    """Yield parsed training-session JSON docs from an extracted export directory."""
    for json_path in sorted(path.rglob("*.json")):
        if not _is_session_file(json_path.name):
            continue
        try:
            yield json.loads(json_path.read_text(encoding="utf-8"))
        except (json.JSONDecodeError, OSError):
            continue


def _parse_zip_entries(
    zip_path: str, names: list[str]
) -> tuple[list[dict], collections.Counter]:
    """Parse a subset of ZIP entries - the picklable unit of parallel work."""
    return _normalize_docs(_iter_zip_docs(zip_path, names))


def _session_entry_names(zip_path: pathlib.Path) -> list[str]:
    """Return the training-session entry names inside a ZIP archive."""
    with zipfile.ZipFile(zip_path) as archive:
        return [name for name in archive.namelist() if _is_session_file(name)]


def _chunk(items: list, num_chunks: int) -> list[list]:
    """Split *items* round-robin into at most *num_chunks* non-empty buckets."""
    if num_chunks <= 1 or len(items) <= 1:
        return [items]
    buckets = [items[i::num_chunks] for i in range(num_chunks)]
    return [bucket for bucket in buckets if bucket]


def _default_workers() -> int:
    """Worker process count: half the cores (min 1), leaving room for the OS."""
    return max(1, (os.cpu_count() or 1) // 2)


def _parse_zip(
    zip_path: pathlib.Path, workers: int | None
) -> tuple[list[dict], collections.Counter]:
    """Parse a Polar export ZIP, fanning entries across processes when it pays off."""
    names = _session_entry_names(zip_path)
    worker_count = workers if workers is not None else _default_workers()
    if worker_count <= 1 or len(names) < _PARALLEL_MIN_FILES:
        return _parse_zip_entries(str(zip_path), names)

    chunks = _chunk(names, worker_count)
    try:
        # match bulldozer: fork so workers inherit the loaded app without re-import
        context = multiprocessing.get_context("fork")
        with concurrent.futures.ProcessPoolExecutor(
            max_workers=len(chunks), mp_context=context
        ) as pool:
            results = list(
                pool.map(functools.partial(_parse_zip_entries, str(zip_path)), chunks)
            )
    except Exception as exc:
        # any pool/platform failure (e.g. no fork on Windows) - fall back to serial
        app_logger.warning(
            "Polar export: parallel parse unavailable, using serial",
            error=str(exc),
        )
        return _parse_zip_entries(str(zip_path), names)

    summaries: list[dict] = []
    sport_ids: collections.Counter = collections.Counter()
    for chunk_summaries, chunk_ids in results:
        summaries.extend(chunk_summaries)
        sport_ids.update(chunk_ids)
    return summaries, sport_ids


def iter_sessions(source: str | pathlib.Path):
    """Yield raw training-session JSON documents from a ZIP file or directory.

    Used by the recording phase to re-read each session's per-second samples and
    GPS track (which the lightweight summaries deliberately drop).
    """
    path = pathlib.Path(source)
    if path.is_file() and zipfile.is_zipfile(path):
        yield from _iter_zip_docs(str(path), _session_entry_names(path))
    elif path.is_dir():
        yield from _iter_dir_docs(path)
    else:
        raise ValueError(
            f"Polar Flow export not found or not a ZIP/directory: {source}"
        )


def normalize_session(session: dict) -> list[dict]:
    """Normalize one raw training-session dict into summary dict(s) (public API)."""
    return _normalize_session_json(session)


def _log_sport_coverage(sport_ids: collections.Counter, sessions: int) -> None:
    """Log the sport-id histogram and warn about ids that fell back to the default."""
    if not sport_ids:
        return
    app_logger.info(
        "Polar export parsed",
        sessions=sessions,
        sport_ids=dict(sport_ids),
    )
    unmapped = {
        sid: count
        for sid, count in sport_ids.items()
        if icommons.polar_flow_sport_name(sid) == ""
    }
    if unmapped:
        app_logger.warning(
            "Polar export: unmapped sport ids imported as the default activity type "
            "- extend icommons.POLAR_FLOW_SPORT_ID_TO_NAME to classify them",
            unmapped=unmapped,
        )


def parse_export(source: str | pathlib.Path, workers: int | None = None) -> list[dict]:
    """Parse a Polar Flow GDPR export into a list of normalized exercise summaries.

    Parameters
    ----------
    source : str | pathlib.Path
        Path to the export ``.zip`` file OR to an already-extracted directory.
    workers : int | None
        Worker process count for ZIP parsing. ``None`` picks a default from the CPU
        count; ``1`` forces serial parsing (used by tests and small archives).

    Returns
    -------
    list[dict]
        Exercise summaries in AccessLink shape, ready for
        ``PolarFlowActivitiesImportPlugin``.
    """
    path = pathlib.Path(source)
    if path.is_file() and zipfile.is_zipfile(path):
        summaries, sport_ids = _parse_zip(path, workers)
    elif path.is_dir():
        summaries, sport_ids = _normalize_docs(_iter_dir_docs(path))
    else:
        raise ValueError(
            f"Polar Flow export not found or not a ZIP/directory: {source}"
        )

    _log_sport_coverage(sport_ids, len(summaries))
    return summaries
