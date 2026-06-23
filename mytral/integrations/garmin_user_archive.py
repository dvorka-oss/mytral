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

"""Garmin Connect user archive import plugin.

Parses Garmin Connect data export (extracted ZIP) to provide activity
metadata for the async import task.

Garmin Connect archive structure:
  garmin_archive/
    DI_CONNECT/
      DI-Connect-Fitness/
        *_summarizedActivities.json    # activity metadata (multiple batch files)
        *_gear.json                    # gear info (typically empty)
      DI-Connect-Uploaded-Files/
        UploadedFiles_*_Part*.zip      # FIT recordings (nested ZIPs)
      DI-Connect-User/
        user_profile.json
    customer_data/
      customer.json
"""

import bisect
import datetime
import json
import pathlib

from mytral import plugins
from mytral import settings as _settings
from mytral.backends import entities

SRC_GARMIN_CONNECT = "garmin_connect"
USE_TYPE_GARMIN_ARCHIVE_DIR = "USE_TYPE_GARMIN_ARCHIVE_DIR"

_FITNESS_SUBDIR = pathlib.Path("DI_CONNECT") / "DI-Connect-Fitness"
_UPLOADS_SUBDIR = pathlib.Path("DI_CONNECT") / "DI-Connect-Uploaded-Files"


def parse_activities_index(data_dir: pathlib.Path) -> dict[int, dict]:
    """Parse summarizedActivities JSON files and build a timestamp lookup index.

    Returns
    -------
    dict[int, dict]
        Mapping of ``start_ts_ms`` (int, Unix milliseconds UTC) to a metadata
        dict with keys: ``activityId``, ``name``, ``locationName``,
        ``activityType``.  Returns an empty dict when no JSON files are found.
    """
    fitness_dir = data_dir / _FITNESS_SUBDIR
    index: dict[int, dict] = {}

    if not fitness_dir.is_dir():
        return index

    json_files = sorted(fitness_dir.glob("*_summarizedActivities.json"))
    for json_file in json_files:
        try:
            with open(json_file, encoding="utf-8") as fh:
                outer = json.load(fh)
        except Exception:
            continue

        if not isinstance(outer, list):
            continue

        for batch in outer:
            if not isinstance(batch, dict):
                continue
            activities = batch.get("summarizedActivitiesExport", [])
            if not isinstance(activities, list):
                continue
            for act in activities:
                ts_raw = act.get("startTimeGmt")
                if ts_raw is None:
                    continue
                try:
                    ts_ms = int(float(ts_raw))
                except (TypeError, ValueError):
                    continue
                index[ts_ms] = {
                    "activityId": act.get("activityId"),
                    "name": act.get("name", ""),
                    "locationName": act.get("locationName", ""),
                    "activityType": (act.get("activityType") or "").lower(),
                }

    return index


def _build_sorted_index(index: dict[int, dict]) -> tuple[list[int], list[dict]]:
    """Return parallel sorted keys/values lists for bisect-based lookup."""
    keys = sorted(index.keys())
    values = [index[k] for k in keys]
    return keys, values


def find_fit_json_match(
    fit_when: datetime.datetime,
    index: dict[int, dict],
    tolerance_s: int = 60,
) -> dict | None:
    """Find JSON metadata whose ``startTimeGmt`` is within *tolerance_s* of *fit_when*.

    Uses binary search for O(log n) matching.

    Parameters
    ----------
    fit_when:
        UTC-aware datetime extracted from the FIT session message.
    index:
        Index returned by :func:`parse_activities_index`.
    tolerance_s:
        Maximum allowed time difference in seconds (default 60).

    Returns
    -------
    dict | None
        Matching metadata dict, or None when no match is within tolerance.
    """
    if not index or fit_when is None:
        return None

    fit_ts_ms = int(fit_when.timestamp() * 1000)
    tolerance_ms = tolerance_s * 1000

    keys, values = _build_sorted_index(index)
    pos = bisect.bisect_left(keys, fit_ts_ms)

    best: dict | None = None
    best_diff = tolerance_ms + 1

    for i in (pos - 1, pos):
        if 0 <= i < len(keys):
            diff = abs(keys[i] - fit_ts_ms)
            if diff <= tolerance_ms and diff < best_diff:
                best_diff = diff
                best = values[i]

    return best


class GarminArchivePlugin(plugins.ActivitiesImportPlugin):
    """Garmin Connect archive import plugin (registry entry).

    The heavy lifting is done by ``GarminArchiveImportTask``; this class
    exists to keep the plugin registry consistent with other importers.
    """

    NAME = "Garmin Connect archive import"
    DESCRIPTION = (
        "Imports activities and FIT recordings from a Garmin Connect "
        "user data export archive."
    )

    def __init__(self) -> None:
        plugins.ActivitiesImportPlugin.__init__(
            self,
            name=GarminArchivePlugin.NAME,
            description=GarminArchivePlugin.DESCRIPTION,
        )

    def import_activities(
        self,
        datasets: dict,
        user_profile: _settings.UserProfile,
        output_path: pathlib.Path | None = None,
        **kwargs,
    ) -> list[entities.ActivityEntity]:
        """Not used directly — Garmin import runs as an async task."""
        return []


plugins.registry.register(GarminArchivePlugin())
