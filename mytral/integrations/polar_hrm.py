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

"""Polar Precision Performance HRM/PDD import plugin.

Parses .hrm (single-exercise HR monitor export) and .pdd (daily exercise summary)
files produced by Polar Precision Performance software (Polar S720i, model 12).

"""

import concurrent.futures
import os
import pathlib
import statistics
import traceback
import uuid

from mytral import app_logger
from mytral import app_user_ds
from mytral import commons
from mytral import plugins
from mytral import settings
from mytral.backends import entities

#
# Constants
#

POLAR_HRM_IMPORT_SRC = "polar-hrm-import"
# key in the datasets dict that maps to the athlete's training data root directory
POLAR_HRM_DATA_DIR_KEY = "polar_hrm_data_dir"
# task type identifier used in TaskEntity
POLAR_HRM_TASK_TYPE = "polar_hrm_import"

_ENCODING = "windows-1250"

# binary-file magic prefix — skip these files without attempting text parsing
_BINARY_MAGIC = b"PolarData"

# TODO this is wrong - every user has their own sport index mapping;
#   need to read from each user's PDD files and cache the mapping per user
# Polar activity_type_key index → MyTraL activity_type_key string
_SPORT_MAP: dict[int, str] = {
    1: commons.AT_RUN,  # Running
    2: commons.AT_RIDE,  # Cycling (road)
    3: commons.AT_SWIM,  # Swimming
    4: commons.AT_GYM,  # Gym
    5: commons.AT_SKI_F,  # Nordic skiing (XC, free-style/skate default)
    6: commons.AT_RS_F,  # Roller skiing (free-style/skate default)
    7: commons.AT_GYM,  # Step aerobics
    8: commons.AT_GYM,  # Pilates/Strength
    9: commons.AT_RIDE_MOUNTAIN,  # Mountain bike
    10: commons.AT_SKATE_INLINE,  # Inline skating
}

#
# Low-level helpers
#


def _is_binary(path: pathlib.Path) -> bool:
    """Return True when *path* starts with the Polar binary magic prefix."""
    try:
        with open(path, "rb") as fh:
            return fh.read(9) == _BINARY_MAGIC
    except OSError:
        return False


def _parse_duration(s: str) -> tuple[int, int, int]:
    """Parse a Polar duration string ``H:MM:SS.d`` into ``(hours, minutes, seconds)``.

    Parameters
    ----------
    s : str
        Duration string, e.g. ``"0:18:32.0"`` or ``"2:01:23.5"``.

    Returns
    -------
    tuple[int, int, int]
        ``(hours, minutes, seconds)`` truncated to whole seconds.
    """
    try:
        # strip optional decimal part
        s = s.split(".")[0]
        parts = s.split(":")
        if len(parts) == 3:
            return int(parts[0]), int(parts[1]), int(parts[2])
        if len(parts) == 2:
            return 0, int(parts[0]), int(parts[1])
    except (ValueError, IndexError):
        pass
    return 0, 0, 0


def _parse_start_time(s: str) -> tuple[int, int, int]:
    """Parse a Polar start-time string ``H:MM:SS.d`` into ``(hour, minute, second)``.

    Identical to :func:`_parse_duration` but named separately for clarity.
    """
    return _parse_duration(s)


def _parse_date(s: str) -> tuple[int, int, int]:
    """Parse a Polar date integer ``YYYYMMDD`` into ``(year, month, day)``."""
    try:
        d = int(str(s).strip())
        return d // 10000, (d % 10000) // 100, d % 100
    except (ValueError, TypeError):
        return 0, 1, 1


#
# Public parser functions
#


def parse_smode(smode: str) -> tuple[bool, bool, bool, bool, bool]:
    """Parse the SMode 8-character binary string from a .hrm [Params] section.

    The leftmost character is bit 0 (least significant):

    - bit 0: speed column present
    - bit 1: cadence column present
    - bit 2: altitude column present
    - bit 3: power column present
    - bit 7: speed in mph (True) or km/h (False)

    Parameters
    ----------
    smode : str
        8-character string of ``'0'`` and ``'1'`` characters.

    Returns
    -------
    tuple[bool, bool, bool, bool, bool]
        ``(has_speed, has_cadence, has_altitude, has_power, mph)``
    """
    if len(smode) < 8:
        smode = smode.ljust(8, "0")
    has_speed = smode[0] == "1"
    has_cadence = smode[1] == "1"
    has_altitude = smode[2] == "1"
    has_power = smode[3] == "1"
    mph = smode[7] == "1"
    return has_speed, has_cadence, has_altitude, has_power, mph


def compute_max_speed_kmh(rows: list[dict], has_speed: bool) -> float:
    """Compute max speed (km/h) from the HRData time series.

    The Polar HRM ``[Trip]`` section's ``max_speed`` is unreliable for S720i
    exports (often too low, e.g. when GPS lock is lost). The per-row
    ``speed_01kmh`` values in the ``[HRData]`` section are the source of
    truth. ``speed_01kmh`` is in 0.1 km/h units per the format spec.

    Parameters
    ----------
    rows : list[dict]
        The ``rows`` list returned by :func:`parse_hrdata`. Each row is a
        dict that may contain ``"speed_01kmh"`` (int in 0.1 km/h) when
        ``has_speed`` is True.
    has_speed : bool
        Whether the speed column is present in the source HRM file
        (SMode bit 0).

    Returns
    -------
    float
        Max speed in km/h. Returns ``0.0`` if the speed column is absent
        or no row contains a non-zero speed sample.
    """
    if not has_speed or not rows:
        return 0.0
    max_speed_tenths = 0
    for row in rows:
        s = row.get("speed_01kmh", 0)
        if s > max_speed_tenths:
            max_speed_tenths = s
    return max_speed_tenths / 10.0


def compute_elevation_gain(rows: list[dict], has_altitude: bool) -> int:
    """Compute cumulative positive elevation gain (m) from the HRData time series.

    The Polar HRM ``[Trip]`` section's ``elevation_gain`` is broken for S720i
    exports (consistently reports ~3 000 m regardless of the actual ride
    profile). The per-row ``altitude_m`` values in ``[HRData]`` are the
    source of truth. Returns the sum of all positive altitude deltas
    between consecutive samples.

    Parameters
    ----------
    rows : list[dict]
        The ``rows`` list returned by :func:`parse_hrdata`. Each row is a
        dict that may contain ``"altitude_m"`` (int in metres) when
        ``has_altitude`` is True.
    has_altitude : bool
        Whether the altitude column is present in the source HRM file
        (SMode bit 2).

    Returns
    -------
    int
        Cumulative positive elevation gain in metres. Returns ``0`` if
        the altitude column is absent or fewer than two altitude samples
        are available.
    """
    if not has_altitude or not rows:
        return 0
    gain = 0
    previous: int | None = None
    for row in rows:
        alt = row.get("altitude_m")
        if alt is None:
            continue
        if previous is not None:
            delta = alt - previous
            if delta > 0:
                gain += delta
        previous = alt
    return gain


def parse_hrdata(
    lines: list[str],
    has_speed: bool,
    has_cadence: bool,
    has_altitude: bool,
) -> dict:
    """Parse the [HRData] section lines and compute aggregate statistics.

    Parameters
    ----------
    lines : list[str]
        Non-empty data lines from the [HRData] section (no section header).
    has_speed : bool
        Whether the speed column is present (SMode bit 0).
    has_cadence : bool
        Whether the cadence column is present (SMode bit 1).
    has_altitude : bool
        Whether the altitude column is present (SMode bit 2).
    Returns
    -------
    dict
        Keys: ``rows`` (list of dicts with ``hr``, optionally ``speed_01kmh``,
        ``cadence_rpm``, ``altitude_m``), ``avg_hr``, ``max_hr``, ``min_hr``,
        ``elevation_min``, ``elevation_max``.
    """
    rows: list[dict] = []
    hr_values: list[int] = []
    altitude_values: list[int] = []

    for line in lines:
        line = line.strip()
        if not line:
            continue
        parts = line.split()
        if not parts:
            continue
        try:
            hr = int(parts[0])
        except (ValueError, IndexError):
            continue

        row: dict = {"hr": hr}
        col = 1

        if has_speed and col < len(parts):
            try:
                row["speed_01kmh"] = int(parts[col])
            except ValueError:
                pass  # omit key - let downstream treat it as absent
            col += 1

        if has_cadence and col < len(parts):
            try:
                row["cadence_rpm"] = int(parts[col])
            except ValueError:
                pass  # omit key - let downstream treat it as absent
            col += 1

        if has_altitude and col < len(parts):
            try:
                row["altitude_m"] = int(parts[col])
                altitude_values.append(row["altitude_m"])
            except ValueError:
                pass  # omit key - compute_elevation_gain skips None alt
            col += 1

        rows.append(row)
        if hr > 0:
            hr_values.append(hr)

    avg_hr = int(statistics.mean(hr_values)) if hr_values else 0
    max_hr = max(hr_values) if hr_values else 0
    min_hr = min(hr_values) if hr_values else 0
    elevation_min = min(altitude_values) if altitude_values else 0
    elevation_max = max(altitude_values) if altitude_values else 0

    return {
        "rows": rows,
        "avg_hr": avg_hr,
        "max_hr": max_hr,
        "min_hr": min_hr,
        "elevation_min": elevation_min,
        "elevation_max": elevation_max,
    }


def parse_hrm(path: pathlib.Path) -> dict:
    """Parse a single .hrm file and return extracted fields.

    Parameters
    ----------
    path : pathlib.Path
        Path to the .hrm file (Windows-1250 encoded).

    Returns
    -------
    dict
        Keys: ``date`` (YYYYMMDD int), ``start_time`` (H:MM:SS.d str),
        ``start_hour``, ``start_minute``, ``start_second``,
        ``hours``, ``minutes``, ``seconds``,
        ``interval_s`` (int), ``max_hr_param`` (int), ``weight`` (int),
        ``note`` (str), ``avg_hr``, ``max_hr``, ``min_hr``,
        ``kcal`` (int), ``avg_speed_kmh`` (float), ``max_speed_kmh`` (float),
        ``elevation_gain`` (int), ``elevation_max`` (int),
        ``elevation_min`` (int),
        ``has_speed``, ``has_cadence``, ``has_altitude``,
        ``rows`` (list of HRData row dicts), ``interval_s`` (int).
        Returns an empty dict on parse failure.
    """
    result: dict = {}
    try:
        text = path.read_text(encoding=_ENCODING, errors="replace")
    except OSError as exc:
        app_logger.error(
            f"[HRM parser] cannot read {path}: {exc}\n{traceback.format_exc()}",
            error=str(exc),
            traceback=traceback.format_exc(),
        )
        return result

    try:
        lines = text.splitlines()
        current_section = ""
        section_lines: dict[str, list[str]] = {}

        for line in lines:
            stripped = line.strip()
            if stripped.startswith("[") and stripped.endswith("]"):
                current_section = stripped[1:-1]
                section_lines[current_section] = []
            elif current_section:
                section_lines.setdefault(current_section, []).append(line)

        # ---- [Params] ----
        params: dict[str, str] = {}
        for line in section_lines.get("Params", []):
            if "=" in line:
                k, _, v = line.partition("=")
                params[k.strip()] = v.strip()

        date_int = int(params.get("Date", "0") or "0")
        start_time_str = params.get("StartTime", "0:00:00.0")
        length_str = params.get("Length", "0:00:00.0")
        interval_s = int(params.get("Interval", "5") or "5")
        smode = params.get("SMode", "00000000")
        max_hr_param = int(params.get("MaxHR", "0") or "0")
        weight = int(params.get("Weight", "0") or "0")

        h, mi, s = _parse_start_time(start_time_str)
        result["date"] = date_int
        result["start_time"] = start_time_str
        result["start_hour"] = h
        result["start_minute"] = mi
        result["start_second"] = s
        result["hours"], result["minutes"], result["seconds"] = _parse_duration(
            length_str
        )
        result["interval_s"] = interval_s
        result["max_hr_param"] = max_hr_param
        result["weight"] = weight

        has_speed, has_cadence, has_altitude, _has_power, _mph = parse_smode(smode)
        result["has_speed"] = has_speed
        result["has_cadence"] = has_cadence
        result["has_altitude"] = has_altitude

        # ---- [Note] ----
        note_lines = [
            line.strip() for line in section_lines.get("Note", []) if line.strip()
        ]
        result["note"] = "\n".join(note_lines)

        # ---- [Summary-TH] — kcal ----
        summary_th_lines = [
            line for line in section_lines.get("Summary-TH", []) if line.strip()
        ]
        kcal = 0
        if summary_th_lines:
            last_parts = summary_th_lines[-1].split()
            if len(last_parts) >= 2:
                try:
                    kcal = int(last_parts[-1])
                except ValueError:
                    kcal = 0
        result["kcal"] = kcal

        # ---- [Trip] — speed / elevation ----
        trip_lines = [
            line.strip() for line in section_lines.get("Trip", []) if line.strip()
        ]
        avg_speed_kmh = 0.0
        max_speed_kmh = 0.0
        elevation_gain = 0
        elevation_max_trip = 0
        if len(trip_lines) >= 4:
            try:
                avg_speed_kmh = int(trip_lines[1]) / 10.0
            except (ValueError, IndexError):
                pass
            try:
                max_speed_kmh = int(trip_lines[3]) / 10.0
            except (ValueError, IndexError):
                pass
            if len(trip_lines) >= 5:
                try:
                    elevation_max_trip = int(trip_lines[4])
                except (ValueError, IndexError):
                    pass
            if len(trip_lines) >= 6:
                try:
                    elevation_gain = int(trip_lines[5])
                except (ValueError, IndexError):
                    pass

        result["avg_speed_kmh"] = avg_speed_kmh
        result["max_speed_kmh"] = max_speed_kmh
        result["elevation_gain"] = elevation_gain
        result["elevation_max_trip"] = elevation_max_trip

        # ---- [HRData] ----
        hrdata_raw = section_lines.get("HRData", [])
        hr_dict = parse_hrdata(hrdata_raw, has_speed, has_cadence, has_altitude)
        result["rows"] = hr_dict["rows"]
        result["avg_hr"] = hr_dict["avg_hr"]
        result["max_hr"] = hr_dict["max_hr"]
        result["min_hr"] = hr_dict["min_hr"]
        result["elevation_min"] = hr_dict["elevation_min"]
        # prefer HRData max altitude (always meters); fall back to Trip max
        # (Trip elevation may be in cm for some devices → 100× inflation)
        result["elevation_max"] = hr_dict["elevation_max"] or elevation_max_trip
        # HRData-derived speed/elevation: the [Trip] section values for
        # ``max_speed_kmh`` and ``elevation_gain`` are unreliable for S720i
        # exports, so derive these from the per-row HRData time series.
        # The raw Trip values (``max_speed_kmh``, ``elevation_gain``) are
        # kept above — they are still used by the cm-detection heuristic in
        # ``_build_activity`` (gradient check needs the raw Trip elevation_gain
        # to detect 100× cm inflation).  Consumers should use the ``*_hrdata``
        # fields for display and validation.
        # preserve HRData elevation max for cross-reference (always meters)
        result["elevation_max_hrmdata"] = hr_dict["elevation_max"]
        result["max_speed_kmh_hrdata"] = compute_max_speed_kmh(
            hr_dict["rows"], has_speed
        )
        result["elevation_gain_hrdata"] = compute_elevation_gain(
            hr_dict["rows"], has_altitude
        )
    except Exception as ex:
        app_logger.error(
            f"[HRM parser] unable to parse {path}: {ex}\n{traceback.format_exc()}",
            error=str(ex),
            traceback=traceback.format_exc(),
        )

    return result


def parse_pdd(path: pathlib.Path) -> list[dict]:
    """Parse a single .pdd file and return one dict per ExerciseInfo block.

    Parameters
    ----------
    path : pathlib.Path
        Path to the .pdd file (Windows-1250 encoded).

    Returns
    -------
    list[dict]
        Each dict contains: ``date`` (YYYYMMDD int), ``sport_index`` (int),
        ``start_time_s`` (int), ``duration_s`` (int), ``distance_m`` (int),
        ``avg_speed_01kmh`` (int), ``avg_hr`` (int), ``max_hr`` (int),
        ``kcal`` (int), ``note`` (str), ``hrm_filename`` (str).
    """
    try:
        text = path.read_text(encoding=_ENCODING, errors="replace")
    except OSError as exc:
        app_logger.warning(f"polar_hrm: cannot read {path}: {exc}")
        return []

    lines = text.splitlines()

    # split into named sections
    sections: dict[str, list[str]] = {}
    current = ""
    for line in lines:
        stripped = line.strip()
        if stripped.startswith("[") and stripped.endswith("]"):
            current = stripped[1:-1]
            sections[current] = []
        elif current:
            sections.setdefault(current, []).append(line)

    # ---- [DayInfo] — date ----
    day_date = 0
    day_lines = [line for line in sections.get("DayInfo", []) if line.strip()]
    # skip header line (first line); second line has date
    if len(day_lines) >= 2:
        parts = day_lines[1].split()
        if parts:
            try:
                day_date = int(parts[0])
            except ValueError:
                pass

    # ---- [ExerciseInfoN] sections ----
    results: list[dict] = []
    n = 1
    while True:
        key = f"ExerciseInfo{n}"
        if key not in sections:
            break
        ex_lines = sections[key]
        data_lines = [line for line in ex_lines if line.strip() and "\t" in line]
        text_lines = [
            line.strip() for line in ex_lines if line.strip() and "\t" not in line
        ]

        all_rows: list[list[int]] = []
        for dl in data_lines:
            try:
                row_vals = [int(v) for v in dl.split("\t")]
                all_rows.append(row_vals)
            except ValueError:
                # skip lines with non-integer values
                pass

        # first tab-row is a block header (version, 1, num_rows, num_cols, type, flags)
        # the 12 actual data rows follow — index them as rows[0..11]
        rows = all_rows[1:] if len(all_rows) > 1 else []

        # extract fields (design doc table, spec row N → rows[N] after header skip)
        start_time_s = rows[0][4] if len(rows) > 0 and len(rows[0]) > 4 else 0
        duration_s = rows[0][5] if len(rows) > 0 and len(rows[0]) > 5 else 0
        sport_index = rows[1][0] if len(rows) > 1 and len(rows[1]) > 0 else 0
        kcal = rows[1][5] if len(rows) > 1 and len(rows[1]) > 5 else 0
        distance_m = rows[2][0] if len(rows) > 2 and len(rows[2]) > 0 else 0
        avg_speed_01kmh = rows[2][5] if len(rows) > 2 and len(rows[2]) > 5 else 0
        avg_hr = rows[8][0] if len(rows) > 8 and len(rows[8]) > 0 else 0
        max_hr = rows[8][1] if len(rows) > 8 and len(rows[8]) > 1 else 0

        # parse text lines: note + hrm filename reference
        hrm_filename = ""
        note_parts: list[str] = []
        for tl in text_lines:
            if tl.lower().endswith(".hrm"):
                hrm_filename = tl
            else:
                note_parts.append(tl)
        note = "\n".join(note_parts)

        results.append(
            {
                "date": day_date,
                "sport_index": sport_index,
                "start_time_s": start_time_s,
                "duration_s": duration_s,
                "distance_m": distance_m,
                "avg_speed_01kmh": avg_speed_01kmh,
                "avg_hr": avg_hr,
                "max_hr": max_hr,
                "kcal": kcal,
                "note": note,
                "hrm_filename": hrm_filename,
            }
        )
        n += 1

    return results


def map_activity_type_index(index: int) -> str:
    """Map a Polar activity_type_key index to a MyTraL activity_type_key string.

    Parameters
    ----------
    index : int
        Polar activity_type_key index from [ExerciseInfoN] row 1, col 0.

    Returns
    -------
    str
        MyTraL activity_type_key string (e.g. ``"ride"``, ``"run"``).
    """
    return _SPORT_MAP.get(index, commons.AT_GYM)


#
# Plugin class
#


class PolarHrmImportPlugin(plugins.ActivitiesImportPlugin):
    """Import training data from Polar Precision Performance (.hrm + .pdd) files.

    Supports data exported from Polar S720i (monitor model 12) and compatible
    Polar heart-rate monitors.  Reads the directory tree produced by Polar
    Precision Performance software: one YYYYMMDD.pdd per day under annual
    subdirectories, one YYMMDDNN.hrm per exercise.

    Parsed HRM time-series data (HR, speed, cadence, altitude) is cached in
    ``_hrm_data_cache`` (keyed by ``src_key`` = HRM filename).  The caller
    (task or route) reads this cache to generate FIT blobs after persistence —
    the plugin itself does NOT write to the blobstore.
    """

    NAME = "Polar HRM Import"
    DESCRIPTION = "Import from Polar Precision Performance (.hrm + .pdd) files."

    # activity's parsed raw .hrm/.pdd data
    KEY_POLAR_ROW_DATA = "polar_raw_data"
    KEY_HRM_PATH = "hrm_path"

    def __init__(self) -> None:
        """Constructor."""
        plugins.ActivitiesImportPlugin.__init__(
            self,
            name=PolarHrmImportPlugin.NAME,
            description=PolarHrmImportPlugin.DESCRIPTION,
        )
        self._hrm_data_cache: dict[str, dict] = {}
        self._log_name = "[Polar HRM import plugin]"

    def import_activities(
        self,
        datasets: dict[str, list[pathlib.Path] | pathlib.Path | str | list[dict]],
        user_profile: settings.UserProfile,
        output_path: pathlib.Path | None = None,
        **kwargs,
    ) -> list[entities.ActivityEntity]:
        """Parse all .pdd + .hrm files in the given directory tree.

        Parameters
        ----------
        datasets : dict
            Must contain key ``POLAR_HRM_DATA_DIR_KEY`` pointing to the root
            of the athlete's training data directory (e.g. ``.../John/``).
        user_profile : settings.UserProfile
            Profile of the importing user (used for activity evaluation).
        output_path : pathlib.Path or None
            Optional path to write the converted activities as JSON.
        **kwargs
            Accepts ``correlation_id`` (str) for dedup tracing.

        Returns
        -------
        list[entities.ActivityEntity]
            Parsed activities ordered by date ascending.

        Raises
        ------
        ValueError
            When the data directory key is missing.
        FileNotFoundError
            When the data directory does not exist.
        """
        correlation_id: str = kwargs.get("correlation_id", str(uuid.uuid4()))

        data_dir_raw = datasets.get(POLAR_HRM_DATA_DIR_KEY)
        if not data_dir_raw:
            raise ValueError(
                f"{self._log_name} '{POLAR_HRM_DATA_DIR_KEY}' key is required."
            )
        data_dir = pathlib.Path(str(data_dir_raw))
        if not data_dir.is_dir():
            raise FileNotFoundError(
                f"{self._log_name} data directory not found: {data_dir}"
            )

        app_logger.info(
            "{self._log_name} starting import",
            data_dir=str(data_dir),
            correlation_id=correlation_id,
        )

        # reset cache for this import run
        self._hrm_data_cache = {}

        # discover all .pdd files recursively
        pdd_files = sorted(data_dir.rglob("*.pdd"))
        app_logger.info(
            f"{self._log_name} discovered PDD files",
            count=len(pdd_files),
        )

        # PASS 1: parse all PDD files, collect (year_dir, exercise) pairs
        all_exercises: list[tuple[pathlib.Path, dict]] = []
        for pdd_path in pdd_files:
            if _is_binary(pdd_path):
                continue
            try:
                exercises = parse_pdd(pdd_path)
            except Exception as exc:
                app_logger.warning(
                    f"{self._log_name} failed to parse PDD: {exc}\n"
                    f"{traceback.format_exc()}",
                    path=str(pdd_path),
                    error=str(exc),
                    traceback=traceback.format_exc(),
                )
                continue
            year_dir = pdd_path.parent
            for exercise in exercises:
                all_exercises.append((year_dir, exercise))

        # PASS 2: parallel-parse HRM files into cache (I/O-bound)
        self._parallel_parse_hrm_files(all_exercises)

        # PASS 3: build ActivityEntity objects using pre-populated cache
        activities: list[entities.ActivityEntity] = []
        for year_dir, exercise in all_exercises:
            try:
                activity = self._build_activity(
                    exercise=exercise,
                    year_dir=year_dir,
                    user_profile=user_profile,
                    correlation_id=correlation_id,
                )
                if activity is not None:
                    activities.append(activity)
            except Exception as exc:
                app_logger.warning(
                    f"{self._log_name} failed to build activity",
                    pdd_dir=str(year_dir),
                    hrm=exercise.get("hrm_filename", ""),
                    error=str(exc),
                )

        # sort by date ascending
        activities.sort(key=lambda a: (a.when_year, a.when_month, a.when_day))

        app_logger.info(
            "{self._log_name} import complete",
            total=len(activities),
            correlation_id=correlation_id,
        )

        return activities

    def _parallel_parse_hrm_files(
        self,
        all_exercises: list[tuple[pathlib.Path, dict]],
    ) -> None:
        """Pre-parse all referenced HRM files in parallel using threads.

        Populates ``_hrm_data_cache`` so that :meth:`_build_activity` reads
        parsed data from memory instead of re-reading files from disk.
        Uses a ``ThreadPoolExecutor`` because HRM parsing is I/O-bound.

        Parameters
        ----------
        all_exercises : list[tuple[pathlib.Path, dict]]
            Pairs of ``(year_dir, exercise_dict)`` collected from PDD files.
        """
        # collect unique HRM file jobs: (filename, path, sport_index)
        jobs: list[tuple[str, pathlib.Path, int]] = []
        seen: set[str] = set()
        for year_dir, ex in all_exercises:
            hrm_filename = ex.get("hrm_filename", "")
            if not hrm_filename or hrm_filename in seen:
                continue
            hrm_path = year_dir / hrm_filename
            if hrm_path.exists() and not _is_binary(hrm_path):
                jobs.append((hrm_filename, hrm_path, ex.get("sport_index", 0)))
                seen.add(hrm_filename)

        if not jobs:
            return

        def _parse_one(job: tuple[str, pathlib.Path, int]) -> tuple[str, dict]:
            filename, path, sport_index = job
            try:
                data = parse_hrm(path)
                data["sport_index"] = sport_index
                return filename, data
            except Exception as exc:
                app_logger.warning(
                    f"{self._log_name} HRM parse failed in parallel phase",
                    hrm=filename,
                    error=str(exc),
                )
                return filename, {}

        workers = max(1, (os.cpu_count() or 2) // 2)
        with concurrent.futures.ThreadPoolExecutor(max_workers=workers) as pool:
            for filename, data in pool.map(_parse_one, jobs):
                if data:
                    self._hrm_data_cache[filename] = data

        app_logger.info(
            f"{self._log_name} HRM files parsed",
            total=len(jobs),
            cached=len(self._hrm_data_cache),
            workers=workers,
        )

    def _build_activity(
        self,
        exercise: dict,
        year_dir: pathlib.Path,
        user_profile: settings.UserProfile,
        correlation_id: str,
    ) -> entities.ActivityEntity | None:
        """Build one ActivityEntity from a PDD exercise dict, enriched with HRM data.

        Parameters
        ----------
        ex : dict
            Exercise dict from :func:`parse_pdd`.
        year_dir : pathlib.Path
            Directory containing the annual .hrm files (same directory as the .pdd).
        user_profile : settings.UserProfile
            User profile for activity evaluation.
        correlation_id : str
            Import run identifier set on every produced activity.

        Returns
        -------
        entities.ActivityEntity or None
            Built activity, or None when parsing produced no usable data.
        """
        # date from PDD
        year, month, day = _parse_date(exercise["date"])
        if year == 0:
            return None

        # start time from PDD (fallback)
        sts = exercise.get("start_time_s", 0)
        pdd_hour = sts // 3600
        pdd_minute = (sts % 3600) // 60
        pdd_second = sts % 60

        # duration from PDD (fallback)
        dur_s = exercise.get("duration_s", 0)
        pdd_hours = dur_s // 3600
        pdd_minutes = (dur_s % 3600) // 60
        pdd_seconds = dur_s % 60

        # HRM enrichment
        hrm_filename = exercise.get("hrm_filename", "")
        hrm: dict = {}
        if hrm_filename:
            hrm_path = year_dir / hrm_filename
            exercise[PolarHrmImportPlugin.KEY_HRM_PATH] = hrm_path
            # use pre-populated cache from parallel parse phase
            hrm = self._hrm_data_cache.get(hrm_filename, {})
            if not hrm:
                # fallback: parse on-demand if not in cache (e.g. binary-skipped)
                if hrm_path.exists() and not _is_binary(hrm_path):
                    try:
                        hrm = parse_hrm(hrm_path)
                        hrm["sport_index"] = exercise.get("sport_index", 0)
                        self._hrm_data_cache[hrm_filename] = hrm
                    except Exception as exc:
                        app_logger.info(
                            f"{self._log_name} HRM parse failed, using PDD data only",
                            hrm=hrm_filename,
                            error=str(exc),
                        )
                else:
                    app_logger.info(
                        "{self._log_name} HRM file not found, using PDD data only",
                        hrm=hrm_filename,
                    )

        # merge: HRM takes precedence over PDD
        if hrm:
            h_date = hrm.get("date", 0)
            if h_date:
                year, month, day = _parse_date(h_date)
            start_hour = hrm.get("start_hour", pdd_hour)
            start_minute = hrm.get("start_minute", pdd_minute)
            start_second = hrm.get("start_second", pdd_second)
            act_hours = hrm.get("hours", pdd_hours)
            act_minutes = hrm.get("minutes", pdd_minutes)
            act_seconds = hrm.get("seconds", pdd_seconds)
            note = hrm.get("note", "") or exercise.get("note", "")
            avg_hr = hrm.get("avg_hr", 0) or exercise.get("avg_hr", 0)
            max_hr = hrm.get("max_hr", 0) or exercise.get("max_hr", 0)
            kcal = hrm.get("kcal", 0) or exercise.get("kcal", 0)
            # max_speed and elevation_gain come from the HRData time series
            # (``*_hrdata``) because the ``[Trip]`` section values in S720i
            # exports are unreliable (e.g. elevation_gain is always ~3000 m).
            max_speed_kmh = hrm.get("max_speed_kmh_hrdata", 0.0)
            elevation_gain = hrm.get("elevation_gain_hrdata", 0)
            elevation_min = hrm.get("elevation_min", 0)
            elevation_max = hrm.get("elevation_max", 0)
            weight = hrm.get("weight", 0)
        else:
            start_hour = pdd_hour
            start_minute = pdd_minute
            start_second = pdd_second
            act_hours = pdd_hours
            act_minutes = pdd_minutes
            act_seconds = pdd_seconds
            note = exercise.get("note", "")
            avg_hr = exercise.get("avg_hr", 0)
            max_hr = exercise.get("max_hr", 0)
            kcal = exercise.get("kcal", 0)
            max_speed_kmh = 0.0
            elevation_gain = 0
            elevation_min = 0
            elevation_max = 0
            weight = 0

        # note: first line as name, full note as description
        note_lines = note.splitlines() if note else []
        name = note_lines[0].strip() if note_lines else ""
        description = note

        # distance always from PDD (HRM does not carry it)
        distance_m = exercise.get("distance_m", 0)

        # detect elevation values stored in cm (some Polar devices store Trip
        # elevation in cm instead of meters → 100× inflation)
        if elevation_gain > 0 and distance_m > 0:
            gradient_m_per_km = elevation_gain / (distance_m / 1000)
            if gradient_m_per_km > 150:
                # cross-check: HRData altitude is always in meters
                hrmdata_elev_max = hrm.get("elevation_max_hrmdata", 0) if hrm else 0
                if hrmdata_elev_max > 0 and elevation_max > hrmdata_elev_max * 50:
                    elevation_gain = elevation_gain // 100
                    elevation_max = elevation_max // 100
                    elevation_min = elevation_min // 100

        sport_str = map_activity_type_index(exercise.get("sport_index", 0))

        # auto-reclassify when the declared activity type contradicts the
        # measured speed/distance data (user may have forgotten to switch
        # sport profile on the watch, or the Polar sport index is unknown).
        duration_s = act_hours * 3600 + act_minutes * 60 + act_seconds
        if duration_s > 0 and distance_m > 0:
            prelim_avg_speed = (distance_m / duration_s) * 3.6
            if sport_str == commons.AT_RUN and prelim_avg_speed > 25.0:
                # running at > 25 km/h is world-record pace — this is a ride
                sport_str = commons.guess_activity_type(prelim_avg_speed)
            elif sport_str == commons.AT_GYM and prelim_avg_speed > 0:
                # "exercise" with distance/time/speed data — guess real type
                sport_str = commons.guess_activity_type(prelim_avg_speed)

        # determine src_key — prefer hrm filename; fall back to synthetic key
        src_key = (
            hrm_filename
            if hrm_filename
            else f"pdd-{exercise['date']}-{exercise.get('sport_index', 0)}"
        )

        a = entities.ActivityEntity()
        a.key = app_user_ds.create_key()
        a.name = name
        a.description = description
        a.activity_type_key = sport_str

        a.when_year = year
        a.when_month = month
        a.when_day = day
        a.when_hour = start_hour
        a.when_minute = start_minute
        a.when_second = start_second

        a.hours = act_hours
        a.minutes = act_minutes
        a.seconds = act_seconds

        a.distance = distance_m
        a.avg_hr = avg_hr
        a.max_hr = max_hr
        # min_hr is a day-level metric (resting HR), not an in-activity
        # minimum; do not set it from per-activity HRData.
        a.kcal = kcal
        a.max_speed = max_speed_kmh
        a.elevation_gain = elevation_gain
        a.elevation_min = elevation_min
        a.elevation_max = elevation_max
        if weight:
            a.weight = float(weight)

        a.src = POLAR_HRM_IMPORT_SRC
        a.src_key = src_key
        a.src_url = ""
        a.src_descriptor = correlation_id

        # inject raw data to context for efficient processing
        a.transient_fields = a.transient_fields or {}
        a.transient_fields[PolarHrmImportPlugin.KEY_POLAR_ROW_DATA] = exercise

        entities.evaluate_activity(entity=a, user_profile=user_profile)

        # cap avg_speed when it exceeds max_speed (PDD distance/duration vs HRM
        # max_speed may disagree due to different measurement sources)
        if a.max_speed > 0 and a.avg_speed > a.max_speed:
            a.avg_speed = a.max_speed
            a.pace = entities.kmh_to_pace(a.avg_speed)

        return a


#
# Plugin registration
#

plugins.registry.register(PolarHrmImportPlugin())
