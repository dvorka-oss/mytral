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
import math
import pathlib
import uuid

import pandas

from mytral import app_logger
from mytral import app_user_ds
from mytral import commons
from mytral import loggers
from mytral import persistences
from mytral import plugins
from mytral import settings
from mytral.backends import entities

# URL prefix for a Concept2 online log activity
_URL_CONCEPT2_ACTIVITY = "https://log.concept2.com/profile/log/"


def _safe_str(value) -> str:
    """Return a stripped string from value or empty string for NaN / None."""
    if value is None:
        return ""
    if isinstance(value, float) and math.isnan(value):
        return ""
    return str(value).strip()


def _build_description(row: pandas.Series) -> str:
    """Build the activity description from supplementary Concept2 CSV columns.

    The description is assembled from:

    - ``Stroke Rate/Cadence`` - appended as ``@{cadence}``
    - ``Pace`` - appended as ``{pace}/500m``
    - ``Drag Factor`` - appended as ``DF{drag}``
    - ``Comments`` - appended wrapped in parentheses

    Parameters
    ----------
    row : pandas.Series
        A single row from the Concept2 CSV.

    Returns
    -------
    str
        Human-readable description string (may be empty).

    """
    parts: list[str] = []

    cadence = _safe_str(row.get("Stroke Rate/Cadence", ""))
    if cadence:
        parts.append(f"@{cadence}")

    pace = _safe_str(row.get("Pace", ""))
    if pace:
        parts.append(f"{pace}/500m")

    drag = _safe_str(row.get("Drag Factor", ""))
    if drag:
        parts.append(f"DF{drag}")

    comment = _safe_str(row.get("Comments", ""))
    if comment:
        parts.append(f"({comment})")

    return " ".join(parts)


def _seconds_to_hms(total_seconds: float) -> tuple[int, int, int]:
    """Convert total seconds (possibly fractional) to (hours, minutes, seconds).

    Parameters
    ----------
    total_seconds : float
        Total duration in seconds.

    Returns
    -------
    tuple[int, int, int]
        A tuple of ``(hours, minutes, seconds)`` as integers (truncated).

    """
    total_int = int(total_seconds)
    hours = total_int // 3_600
    minutes = (total_int % 3_600) // 60
    seconds = total_int % 60
    return hours, minutes, seconds


class Concept2ActivitiesImportPlugin(plugins.ActivitiesImportPlugin):
    """Concept2 training log - activities import plugin.

    Imports workouts from a CSV file exported from the Concept2 online training
    log (https://log.concept2.com).  Each CSV row represents a single indoor
    rower (ergometer) session and is converted to an
    ``entities.ActivityEntity`` with activity_type_key ``commons.AT_ROW_ERG``.

    CSV columns description
    -----------------------
    "ID"
        [src_key] ``concept2:<ID>``
    "Date"
        [when_year, when_month, when_day, when_hour, when_minute, when_second]
    "Description"
        [name]
    "Work Time (Formatted)"
        human-readable duration string - not used directly
    "Work Time (Seconds)"
        [hours, minutes, seconds] - fractional secs are truncated, e.g. ``int(1194.3)``
    "Rest Time (Formatted)"
        not imported
    "Rest Time (Seconds)"
        not imported
    "Work Distance"
        [distance] meters
    "Rest Distance"
        not imported
    "Stroke Rate/Cadence"
        [description] if present: ``@24``
    "Stroke Count"
        not imported
    "Pace"
        [description] if present: ``1:59/500m``
    "Avg Watts"
        [avg_watts]
    "Cal/Hour"
        not imported
    "Total Cal"
        [kcal]
    "Avg Heart Rate"
        [avg_hr]
    "Drag Factor"
        [description] if present: ``DF122``
    "Age"
        not imported
    "Weight"
        not imported
    "Type"
        not imported (always "Indoor Rower" in exported data)
    "Ranked"
        [ranked, intensity] ``Yes`` → ``ranked=True``, ``intensity="race"``
    "Comments"
        [description] if present: ``(...)``

    """

    NAME = "Concept2 activities import"
    DESCRIPTION = (
        "Imports activities from the Concept2 training log. "
        "In order to import activities provide path to the CSV exported from "
        "the Concept2 training log."
    )

    USE_TYPE_CONCEPT2_CSV = "USE_TYPE_CONCEPT2_CSV"

    def __init__(
        self,
        logger: loggers.MytralLogger | None = None,
    ):
        """Constructor."""
        plugins.ActivitiesImportPlugin.__init__(
            self,
            name=Concept2ActivitiesImportPlugin.NAME,
            description=Concept2ActivitiesImportPlugin.DESCRIPTION,
        )

        self.log_name = f"[{self.name}]"
        self.logger = logger or app_logger

    def _row_to_activity(
        self,
        row: pandas.Series,
        user_profile: settings.UserProfile,
    ) -> entities.ActivityEntity:
        """Convert a single Concept2 CSV row to an ActivityEntity.

        Parameters
        ----------
        row : pandas.Series
            A single row from the Concept2 CSV DataFrame.
        user_profile : settings.UserProfile
            The user profile used for BMI calculation in
            ``entities.evaluate_activity``.

        Returns
        -------
        entities.ActivityEntity
            The converted activity.

        """
        # DATE / TIME
        # "2008-12-11 00:00:00" - time part is always 00:00:00 in Concept2 export
        date_str = _safe_str(row.get("Date", ""))
        try:
            dt = datetime.datetime.strptime(date_str, "%Y-%m-%d %H:%M:%S")
        except ValueError:
            dt = datetime.datetime.now()
            self.logger.warning(
                f"{self.log_name} Could not parse date '{date_str}'; "
                f"using current time instead."
            )

        # DURATION
        work_time_seconds: float = 0.0
        raw_time = row.get("Work Time (Seconds)", 0)
        if raw_time and not (isinstance(raw_time, float) and math.isnan(raw_time)):
            try:
                work_time_seconds = float(raw_time)
            except (ValueError, TypeError):
                self.logger.warning(
                    f"{self.log_name} Could not parse 'Work Time (Seconds)': "
                    f"'{raw_time}'"
                )
        hours, minutes, seconds = _seconds_to_hms(work_time_seconds)

        # DISTANCE
        distance_meters: int = 0
        raw_dist = row.get("Work Distance", 0)
        if raw_dist and not (isinstance(raw_dist, float) and math.isnan(raw_dist)):
            try:
                distance_meters = int(raw_dist)
            except (ValueError, TypeError):
                self.logger.warning(
                    f"{self.log_name} Could not parse 'Work Distance': '{raw_dist}'"
                )

        # RANKED / INTENSITY
        ranked_str = _safe_str(row.get("Ranked", "")).lower()
        is_ranked = ranked_str == "yes"
        intensity = commons.INTENSITY_RACE if is_ranked else commons.INTENSITY_EASY

        # WATTS
        avg_watts: float = 0.0
        raw_watts = row.get("Avg Watts", None)
        if raw_watts and not (isinstance(raw_watts, float) and math.isnan(raw_watts)):
            try:
                avg_watts = float(raw_watts)
            except (ValueError, TypeError):
                pass

        # KCAL
        kcal: int = 0
        raw_kcal = row.get("Total Cal", None)
        if raw_kcal and not (isinstance(raw_kcal, float) and math.isnan(raw_kcal)):
            try:
                kcal = int(raw_kcal)
            except (ValueError, TypeError):
                pass

        # HEART RATE
        avg_hr: int = 0
        raw_hr = row.get("Avg Heart Rate", None)
        if raw_hr and not (isinstance(raw_hr, float) and math.isnan(raw_hr)):
            try:
                avg_hr = int(raw_hr)
            except (ValueError, TypeError):
                pass

        # CADENCE
        avg_cadence: int = 0
        raw_cadence = row.get("Stroke Rate/Cadence", None)
        if raw_cadence and not (
            isinstance(raw_cadence, float) and math.isnan(raw_cadence)
        ):
            try:
                avg_cadence = int(float(raw_cadence))
            except (ValueError, TypeError):
                pass

        # SOURCE
        concept2_id = _safe_str(row.get("ID", ""))
        src_key = f"concept2:{concept2_id}" if concept2_id else ""
        src_url = f"{_URL_CONCEPT2_ACTIVITY}{concept2_id}" if concept2_id else ""

        # BUILD ENTITY
        a = entities.ActivityEntity()
        a.key = app_user_ds.create_key()
        a.name = _safe_str(row.get("Description", "")) or "Concept2 row"
        a.description = _build_description(row)
        a.activity_type_key = commons.AT_ROW_ERG

        a.when_year = dt.year
        a.when_month = dt.month
        a.when_day = dt.day
        a.when_hour = dt.hour
        a.when_minute = dt.minute
        a.when_second = dt.second

        a.hours = hours
        a.minutes = minutes
        a.seconds = seconds

        a.distance = distance_meters

        a.ranked = is_ranked
        a.intensity = intensity

        a.avg_watts = avg_watts
        a.kcal = kcal
        a.avg_hr = avg_hr
        a.avg_cadence = avg_cadence

        a.src = "concept2-import"
        a.src_key = src_key
        a.src_url = src_url

        entities.evaluate_activity(entity=a, user_profile=user_profile)

        return a

    def import_activities(
        self,
        datasets: dict[str, list[pathlib.Path] | pathlib.Path | str | list[dict]],
        user_profile: settings.UserProfile,
        output_path: pathlib.Path | None = None,
        **kwargs,
    ) -> list[entities.ActivityEntity]:
        """Import activities from a Concept2 CSV export.

        Parameters
        ----------
        datasets : dict
            Must contain the key ``USE_TYPE_CONCEPT2_CSV`` mapping to a
            :class:`pathlib.Path` pointing at the exported CSV file.
        user_profile : settings.UserProfile
            Profile of the user the activities will be imported for.
        output_path : pathlib.Path or None
            When provided the converted activities are also persisted as a JSON
            file at this path.
        **kwargs
            Additional keyword arguments (ignored).

        Returns
        -------
        list[entities.ActivityEntity]
            List of converted activities, one per CSV row.

        Raises
        ------
        ValueError
            When the required CSV dataset path is missing.
        FileNotFoundError
            When the CSV file does not exist.

        """
        correlation_id: str = kwargs.get("correlation_id", str(uuid.uuid4()))

        csv_path = datasets.get(self.USE_TYPE_CONCEPT2_CSV)
        if not csv_path:
            raise ValueError(
                f"{self.log_name} Concept2 CSV file is required but was not provided."
            )
        csv_path = pathlib.Path(csv_path)
        if not csv_path.exists():
            raise FileNotFoundError(
                f"{self.log_name} Concept2 CSV file not found: {csv_path}"
            )

        self.logger.info(
            f"{self.log_name} Loading Concept2 CSV",
            csv_path=str(csv_path),
        )

        df: pandas.DataFrame = pandas.read_csv(csv_path)
        self.logger.info(
            f"{self.log_name} CSV loaded",
            rows=df.shape[0],
            columns=df.shape[1],
        )

        activities: list[entities.ActivityEntity] = []
        for _, row in df.iterrows():
            try:
                activity = self._row_to_activity(row=row, user_profile=user_profile)
                activity.src_descriptor = correlation_id
                activities.append(activity)
            except Exception as e:
                self.logger.error(
                    f"{self.log_name} Failed to convert row to activity",
                    error=str(e),
                    row_id=_safe_str(row.get("ID", "unknown")),
                )

        self.logger.info(
            f"{self.log_name} Imported activities",
            count=len(activities),
        )

        if output_path:
            persistences.save_json(
                file_path=output_path,
                data_dict=[a.to_dict() for a in activities],
            )

        return activities


# PLUGINS REGISTRY: register Concept2 plugin
plugins.registry.register(Concept2ActivitiesImportPlugin())
