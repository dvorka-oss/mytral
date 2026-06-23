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

"""GoldenCheetah OSF athlete archive import plugin.

Reads a single athlete ZIP produced by the GoldenCheetah Open Science
Framework dataset.  Each ZIP contains:

  {uuid}.json  — ATHLETE metadata + RIDES array with pre-computed METRICS
  YYYY_MM_DD_HH_MM_SS.csv — 1-second time-series (secs, km, power, hr, cad, alt)

Only the JSON index is used for import.  The CSV time-series files are
intentionally skipped: they are summary-only imports of the pre-computed
METRICS (avg HR, avg power, distance, …).  The CSV files contain no GPS
coordinates (lat/lon), so no map or route data is available anyway.

Metric value quirks in the JSON:
  - scalar  : numeric string "4010.00000"
  - weighted: list ["avg_str", "weight_str"]  (e.g. average_hr, average_power)
  - absent  : key not present in the METRICS dict
All are handled by _metric_float().

Note: JSON dates are stored in UTC; CSV filenames use the athlete's local
time.  src_key is derived from the UTC date, which is consistent across
re-imports of the same archive.

"""

import datetime
import json
import pathlib
import zipfile

from mytral import app_logger
from mytral import app_user_ds
from mytral import commons
from mytral import plugins
from mytral import settings
from mytral.backends import entities

#
# Constants
#

GC_OSF_SRC = "golden_cheetah_osf"
GC_OSF_DATE_FMT = "%Y/%m/%d %H:%M:%S UTC"
GC_OSF_ZIP_PATH_KEY = "zip_path"

# GoldenCheetah sport string → MyTraL activity type key
_SPORT_MAP: dict[str, str] = {
    "Bike": commons.AT_RIDE,
    "VirtualRide": commons.AT_RIDE_VIRTUAL,
    "Run": commons.AT_RUN,
    "Swim": commons.AT_SWIM,
    "Walk": commons.AT_WALK,
    "Hike": commons.AT_HIKE,
    "WeightTraining": commons.AT_GYM,
    "NordicSki": commons.AT_SKI_DP,
    "StandUpPaddling": commons.AT_PADDLE,
    "Canoeing": commons.AT_CANOEING,
    "Other": commons.AT_WORKOUT,
    "": commons.AT_RIDE,  # dataset default: cycling
}


def _metric_float(metrics: dict, key: str, default: float = 0.0) -> float:
    """Extract a float from a GoldenCheetah METRICS dict entry.

    Handles three value shapes produced by GoldenCheetah:
    - None       → default
    - float/str  → float(value)
    - list       → float(value[0])  (weighted average; first element is the avg)
    """
    value = metrics.get(key)
    if value is None:
        return default
    if isinstance(value, list):
        value = value[0]
    try:
        return float(value)
    except (ValueError, TypeError):
        return default


def _ride_to_activity(
    ride: dict,
    athlete_uuid: str,
) -> entities.ActivityEntity | None:
    """Map a single GoldenCheetah RIDES entry to an ActivityEntity.

    Returns None for entries with a missing or unparseable date so the
    caller can skip them without crashing.
    """
    date_str = ride.get("date", "")
    if not date_str:
        return None

    try:
        when = datetime.datetime.strptime(date_str, GC_OSF_DATE_FMT)
    except ValueError:
        app_logger.warning(
            "golden_cheetah_osf: unparseable date, skipping ride",
            date=date_str,
            athlete=athlete_uuid,
        )
        return None

    metrics = ride.get("METRICS", {})
    sport = ride.get("sport", "")

    at_key = _SPORT_MAP.get(sport, commons.AT_RIDE)

    # duration: workout_time is total elapsed seconds
    total_secs = int(_metric_float(metrics, "workout_time"))
    hours = total_secs // 3600
    minutes = (total_secs % 3600) // 60
    seconds = total_secs % 60

    # distance: GoldenCheetah stores km; ActivityEntity wants metres (int)
    distance_m = int(_metric_float(metrics, "total_distance") * 1000)

    # src_key matches the CSV filename stem for this ride
    src_key = f"{athlete_uuid}/{when.strftime('%Y_%m_%d_%H_%M_%S')}"

    display_sport = sport if sport else "Ride"
    name = f"GC {display_sport} {when.strftime('%Y-%m-%d')}"

    a = entities.ActivityEntity(
        when_year=when.year,
        when_month=when.month,
        when_day=when.day,
        when_hour=when.hour,
        when_minute=when.minute,
        when_second=when.second,
        name=name,
        activity_type_key=at_key,
        hours=hours,
        minutes=minutes,
        seconds=seconds,
        distance=distance_m,
        avg_hr=_metric_float(metrics, "average_hr"),
        max_hr=_metric_float(metrics, "max_heartrate"),
        avg_watts=_metric_float(metrics, "average_power"),
        max_watts=_metric_float(metrics, "max_power"),
        avg_cadence=_metric_float(metrics, "average_cad"),
        max_cadence=_metric_float(metrics, "max_cadence"),
        max_speed=_metric_float(metrics, "max_speed"),
        elevation_gain=int(_metric_float(metrics, "elevation_gain")),
        kcal=int(_metric_float(metrics, "total_kcalories")),
        src=GC_OSF_SRC,
        src_key=src_key,
    )
    a.key = app_user_ds.create_key()
    return a


def find_csv_stem(when_utc: datetime.datetime, csv_stems: set[str]) -> str | None:
    """Find the CSV filename stem matching a ride's UTC start time.

    GoldenCheetah stores JSON dates in UTC but names CSV files after the
    athlete's local time.  This function searches UTC offsets -14..+14 h
    until it finds a matching stem in the given set.

    Parameters
    ----------
    when_utc : datetime.datetime
        Ride start time in UTC.
    csv_stems : set[str]
        Set of CSV filename stems (without .csv) from the ZIP.

    Returns
    -------
    str or None
        Matching CSV stem, or None if not found.
    """
    for h in range(-14, 15):
        candidate = (when_utc + datetime.timedelta(hours=h)).strftime(
            "%Y_%m_%d_%H_%M_%S"
        )
        if candidate in csv_stems:
            return candidate
    return None


class GoldenCheetahOsfImportPlugin(plugins.ActivitiesImportPlugin):
    """Import activities from a GoldenCheetah OSF athlete ZIP archive."""

    NAME = "golden_cheetah_osf"
    DESCRIPTION = (
        "Imports cycling (and other sport) activities from a GoldenCheetah "
        "Open Science Framework athlete ZIP archive."
    )

    def __init__(self):
        super().__init__(name=self.NAME, description=self.DESCRIPTION)

    def import_activities(
        self,
        datasets: dict,
        user_profile: settings.UserProfile,
        output_path: pathlib.Path | None = None,
        **kwargs,
    ) -> list[entities.ActivityEntity]:
        """Parse the GoldenCheetah OSF ZIP and return ActivityEntity objects.

        Parameters
        ----------
        datasets : dict
            Must contain key GC_OSF_ZIP_PATH_KEY mapping to the ZIP path.
        user_profile : settings.UserProfile
            Used to validate that imported activity types exist for the user.
        """
        zip_src = datasets[GC_OSF_ZIP_PATH_KEY]
        # accept either a path (str / Path) or a file-like object (e.g. BytesIO)
        zip_arg = (
            pathlib.Path(zip_src)
            if isinstance(zip_src, (str, pathlib.Path))
            else zip_src
        )

        with zipfile.ZipFile(zip_arg) as zf:
            json_name = next((n for n in zf.namelist() if n.endswith(".json")), None)
            if not json_name:
                raise ValueError("No JSON index file found in the GoldenCheetah ZIP")

            # strip surrounding braces: "{uuid}.json" → "uuid"
            athlete_uuid = json_name.removesuffix(".json").strip("{}")

            with zf.open(json_name) as fh:
                index = json.load(fh)

        rides = index.get("RIDES", [])

        result = []
        for ride in rides:
            activity = _ride_to_activity(ride, athlete_uuid)
            if activity is not None:
                result.append(activity)

        zip_label = zip_arg.name if isinstance(zip_arg, pathlib.Path) else repr(zip_arg)
        app_logger.info(
            "golden_cheetah_osf: parsed rides",
            zip=zip_label,
            athlete=athlete_uuid,
            total=len(rides),
            imported=len(result),
        )
        return result


plugins.registry.register(GoldenCheetahOsfImportPlugin())
