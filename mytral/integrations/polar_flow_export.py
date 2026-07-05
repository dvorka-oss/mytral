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

import json
import pathlib
import zipfile

# training-session file name marker inside the export ZIP
_SESSION_FILE_MARKER = "training-session"


def _first(source: dict, *keys, default=None):
    """Return the first present, non-empty value among *keys* in *source*."""
    for key in keys:
        if key in source and source[key] not in (None, ""):
            return source[key]
    return default


def _normalize_exercise(exercise: dict, session: dict) -> dict | None:
    """Normalize one export exercise/session dict into an AccessLink-summary shape."""
    start_time = _first(exercise, "startTime", "start-time", default="") or _first(
        session, "startTime", "start-time", default=""
    )
    sport = _first(
        exercise,
        "detailedSportInfo",
        "detailed-sport-info",
        "sport",
        default="",
    )
    if not start_time and not sport:
        return None

    heart_rate = exercise.get("heartRate") or exercise.get("heart-rate") or {}
    hr_avg = _first(heart_rate, "average", "avg", default=0)
    hr_max = _first(heart_rate, "maximum", "max", default=0)

    # normalize the start time to seconds precision (drop any milliseconds/offset)
    start_time_norm = str(start_time)[:19]

    # src_key: prefer an explicit id, else a stable key derived from the start time
    src_id = _first(exercise, "id", default="")
    if not src_id:
        src_id = "".join(ch for ch in start_time_norm if ch.isdigit())

    return {
        "id": src_id,
        "name": _first(session, "name", default="") or "",
        "start-time": start_time_norm,
        "duration": _first(exercise, "duration", default="") or "",
        "distance": _first(exercise, "distance", default=0) or 0,
        "calories": _first(exercise, "kiloCalories", "calories", default=0) or 0,
        "heart-rate": {"average": hr_avg, "maximum": hr_max},
        "sport": _first(exercise, "sport", default="") or "",
        "detailed-sport-info": sport,
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


def parse_export(source: str | pathlib.Path) -> list[dict]:
    """Parse a Polar Flow GDPR export into a list of normalized exercise summaries.

    Parameters
    ----------
    source : str | pathlib.Path
        Path to the export ``.zip`` file OR to an already-extracted directory.

    Returns
    -------
    list[dict]
        Exercise summaries in AccessLink shape, ready for
        ``PolarFlowActivitiesImportPlugin``.
    """
    path = pathlib.Path(source)
    summaries: list[dict] = []

    if path.is_file() and zipfile.is_zipfile(path):
        with zipfile.ZipFile(path) as archive:
            for name in archive.namelist():
                if not _is_session_file(name):
                    continue
                try:
                    with archive.open(name) as handle:
                        data = json.load(handle)
                except (json.JSONDecodeError, OSError):
                    continue
                summaries.extend(_normalize_session_json(data))
    elif path.is_dir():
        for json_path in sorted(path.rglob("*.json")):
            if not _is_session_file(json_path.name):
                continue
            try:
                data = json.loads(json_path.read_text(encoding="utf-8"))
            except (json.JSONDecodeError, OSError):
                continue
            summaries.extend(_normalize_session_json(data))
    else:
        raise ValueError(
            f"Polar Flow export not found or not a ZIP/directory: {source}"
        )

    return summaries
