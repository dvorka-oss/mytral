# MyTraL: my trailing log
#
# Copyright (C) 2022-2026 Martin Dvorak <martin.dvorak@mindforger.com>
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
import re
import uuid
from math import isnan

import pandas

from mytral import app_logger
from mytral import app_user_ds
from mytral import cals
from mytral import commons
from mytral import loggers
from mytral import persistences
from mytral import plugins
from mytral import settings
from mytral.backends import entities
from mytral.integrations import strava

"""
TODO to be implemented:

- CODE: split strava.py module to strava/_plugin.py _service.py
- FEAT: week summary
- ENH: strava conversion "Rotoped 20'" to cycling
- ENH: year cal view - smaller cell padding
- BUG: weight, 2023 - as last week weight is shown the 1st week weight
- BUG: average weight in UI/Me/Weight uses 0s in average, which is wrong
- BUG: Concept2 not imported
- BUG: gear import
- BUG: weight not in week summary
- BUG: missing LBURSA in 2nd week - WRONG week - is always +1, move it to right week
- BUG: missing "biceps 4x20"
- BUG: process gym w/ MartinB & my to exercises w/ kg
- ENH: extract weekly summary comment to "WS comment" convention

"""


class GoogleSheetsActivitiesImportPlugin(plugins.ActivitiesImportPlugin):
    """Google Sheets - proprietary training log - activities import plugin."""

    NAME = "Google Sheets year activities import"
    DESCRIPTION = (
        "Imports activities from the proprietary MyTraL Google Sheets training "
        "log. In order to import activities for the particular year provide"
        "path to the CSV export for that year and optionally include also "
        "file with strava.com activities for that year in MyTraL activities "
        "JSON format."
    )

    USE_TYPE_GSHEETS_CSV = "USE_TYPE_GSHEETS_CSV"
    USE_TYPE_STRAVA_JSON = "USE_TYPE_STRAVA_JSON"

    def __init__(
        self,
        logger: loggers.MytralLogger | None = None,
    ):
        """Constructor."""
        plugins.ActivitiesImportPlugin.__init__(
            self,
            name=GoogleSheetsActivitiesImportPlugin.NAME,
            description=GoogleSheetsActivitiesImportPlugin.DESCRIPTION,
        )

        self.log_name = f"[{self.name}]"
        self.logger = logger or app_logger

    @staticmethod
    def _week_to_date(year: int, week: int, week_day: int) -> datetime.datetime:
        """Convert week date to date.

        Week number:

        - `datetime` counts weeks from 0 to 53.
        - UI: weeks are numbered from 1 to 54.
        - The first and the last week in the year may be incomplete,
          therefore there can be up to 54 weeks in years where e.g. the first
          week starts on Wednesday and the last week ends on Wednesday.

        Day number:

        - `datetime` counts days from 0 to 6.

        Parameters
        ----------
        year : int
            Year.
        week : int
            Week number within the year.
        week_day : int
            Week day - Monday is 0, Sunday is 6.

        Returns
        -------
        datetime.datetime
            Date.

        """
        if week_day == 6:
            week_day = 0
        else:
            week_day += 1
        return datetime.datetime.strptime(f"{year}-W{week}-{week_day}", "%Y-W%W-%w")

    def _ds_extract_year(self, ds: pandas.DataFrame) -> int:
        if ds.shape[0]:
            year_cell = ds.iloc[0, 0]
            if not isinstance(year_cell, str):
                raise ValueError(
                    f"{self.log_name}: year cell is undefined or has unexpected "
                    f"content: '{year_cell}'"
                )
            year = 0
            try:
                year = int(year_cell.split(" ")[0])
            except ValueError:
                print(year_cell)
            if not year or not (1900 < year < 3000):
                raise ValueError(
                    f"{self.log_name}: unable to get valid year from the cell: {year} "
                )

            return year

        raise ValueError(
            f"{self.log_name}: Unable to extract year from dataset as it is empty"
        )

    def _week_summary_2_activity(
        self,
        weight_cell_str: str,
        summary_cell: str | float,
        year: int,
        month: int,
        day: int,
        activity_types_by_name: dict,
    ) -> entities.ActivityEntity | None:
        self.logger.debug(
            f"    WEIGHT to week activity: weight='{weight_cell_str}"
            f"' week_summary='{summary_cell}'"
        )

        summary_cell_str = (
            summary_cell
            if isinstance(summary_cell, str)
            else (
                ""
                if isinstance(summary_cell, float) and isnan(summary_cell)
                else str(summary_cell)
            )
        )

        if weight_cell_str or summary_cell_str:
            a = entities.ActivityEntity()
            a.key = app_user_ds.create_key()
            a.name = "WS"  # week summary
            a.description = summary_cell_str or ""
            a.activity_type_key = activity_types_by_name["Comment"].key
            a.when_year = year
            a.when_month = month
            a.when_day = day
            a.when_hour = 0
            a.when_minute = 30
            a.when_second = 0
            a.weight = float(weight_cell_str) if weight_cell_str else 0.0

            return a

        return None

    def _str_cell_2_activities(
        self,
        cell_str: str,
        year: int,
        month: int,
        day: int,
        activity_types_by_name: dict,
        user_profile: settings.UserProfile,
        symptoms_by_name: dict,
        key: int,
    ) -> tuple[list[entities.ActivityEntity], int]:
        self.logger.debug(f"    String to activities: '{cell_str}'")
        activities = []

        if not cell_str:
            return activities, key

        # 2024 regexps
        prefixes_fyzio = ["fyzio:", "f:"]
        infixes_gym = [" cisty", " bic", "biceps", "fitko"]
        infixes_sick = [
            "ACHYL",
            "BURSA",
            "RYMA",
            "KASEL",
            "PODBRICH",
            "RAMENO",
            "LCESKA",
            "LPSOAR",
            "LPALEC",
            "KOLENA",
            "PRAMENOPTRISLO",
            "COVID feeling",
        ]
        suffixes_sick = ["--", "---", "----", "-1", "-2", "-3", "-4", "-5"]
        infixes_sauna = ["sauna", "saunia"]
        infixes_steam = ["para"]
        infixes_comment = [
            "Logr pub",
            "chill",
            "jezevec",
            "@ office",
            "RPV syndrom",
            "vanocni",
            "busy day",
            "pub miran & stop",
            "rain",
            "Sri visit",
            "besidka",
            "pha",
            "Prg",
            "RPV",
            "aldrov",
            "besidka",
            "erik",
            "h2o pub",
            "hard work",
            "ivanoffice",
            "pha",
            "prace",
            "relax",
            "roxy",
            "unava",
            "unava",
            "velka unava",
            "zZZzzZ",
            "RAMSAU",
        ]

        t_self = GoogleSheetsActivitiesImportPlugin

        parts = cell_str.split("\n")
        for s in parts:
            if not s:
                continue

            a = entities.ActivityEntity()
            a.key = app_user_ds.create_key()
            a.name = ""

            # DETECT activity type
            if any(phrase in s for phrase in prefixes_fyzio):
                app_logger.debug(f"FYZIO: '{s}'")
                a.name = s
                a.activity_type_key = activity_types_by_name["Physiotherapy"].key
                a.minutes = 20
                t_self._str_to_exercise(cell_str=s, activity=a)
            elif any(phrase in s for phrase in infixes_gym):
                app_logger.debug(f"EXERCISE: '{s}'")
                a.name = s
                a.activity_type_key = activity_types_by_name["Exercise"].key
                a.minutes = 30
                t_self._str_to_exercise(cell_str=s, activity=a)
            elif any(phrase in s for phrase in infixes_sick) or any(
                s.endswith(phrase) for phrase in suffixes_sick
            ):
                app_logger.debug(f"SICK    : '{s}'")
                a.name = s
                a.activity_type_key = activity_types_by_name["Sick"].key
                t_self._str_to_symptom(
                    cell_str=s,
                    activity=a,
                    activity_types_by_name=activity_types_by_name,
                    symptoms_by_name=symptoms_by_name,
                )
            elif any(phrase in s for phrase in infixes_sauna):
                app_logger.debug(f"SAUNA   : '{s}'")
                a.name = s
                a.activity_type_key = activity_types_by_name["Sauna"].key
                a.hours = 1
                t_self._str_to_sauna(cell_str=s, activity=a)
            elif any(phrase in s for phrase in infixes_steam):
                app_logger.debug(f"STEAM   : '{s}'")
                a.name = s
                a.activity_type_key = activity_types_by_name["Steam"].key
                a.hours = 1
                t_self._str_to_sauna(cell_str=s, activity=a, sauna_or_steam="para")
            elif any(phrase in s for phrase in infixes_comment):
                app_logger.debug(f"COMMENT : '{s}'")
                a.name = s
                a.activity_type_key = activity_types_by_name["Comment"].key

            # finish activity only if defined
            if a.name:
                workout_order = 1
                a.src = "gdocs-log-import"

                # reset
                a.minutes = 0

                a.when_year = year
                a.when_month = month
                a.when_day = day
                a.when_hour = 12 + workout_order
                a.when_minute = 0
                a.when_second = 0

                try:
                    app_logger.debug(
                        f"{year=} {month=} {day=} "
                        f"{a.when_hour=} {a.when_minute=} {a.when_second=}"
                    )
                    a.when = datetime.datetime(
                        year=year,
                        month=month,
                        day=day,
                        hour=a.when_hour,
                        minute=a.when_minute,
                        second=a.when_second,
                    ).isoformat()
                except ValueError as x:
                    raise ValueError(
                        f"Error: {x}\n"
                        f"  {year=} {month=} {day=}\n"
                        f"  {a.when_hour=} {a.when_minute=} {a.when_second=}"
                    )

                a.workout_sort_code = workout_order
                workout_order += 1

                entities.evaluate_activity(entity=a, user_profile=user_profile)

                activities.append(a)

        return activities, key

    def _import_csv(
        self,
        gsheet_csv_path: pathlib.Path,
        user_profile: settings.UserProfile,
        jan_1st_name: str = "",
        jan_1st_description: str = "",
        correlation_id: str = "",
    ) -> tuple[int, list[entities.ActivityEntity]]:
        this = GoogleSheetsActivitiesImportPlugin

        # LOAD CSV: avoid using 1st row as column name + ensure 1st col is not index
        ds = pandas.read_csv(gsheet_csv_path, header=None, index_col=None)
        self.logger.debug(f"CSV shape: {ds.shape}")
        year = self._ds_extract_year(ds)
        self.logger.debug(f"Importing year: {year}")

        # INDICES: prepare MyTraL indices
        symptoms_by_name = app_user_ds.list_symptoms(
            user_id=user_profile.user_id
        ).symptoms_by_name
        activity_types_by_name = app_user_ds.list_activity_types(
            user_id=user_profile.user_id
        ).activity_types_by_name

        # DO NOT EDIT! hint
        do_not_edit_a = entities.ActivityEntity()
        do_not_edit_a.key = app_user_ds.create_key()
        do_not_edit_a.name = jan_1st_name if jan_1st_name else "🔴DO NOT EDIT: imported"
        do_not_edit_a.description = jan_1st_description
        do_not_edit_a.when_year = year
        do_not_edit_a.when_month = 1
        do_not_edit_a.when_day = 1
        do_not_edit_a.when_hour = 1
        do_not_edit_a.description = (
            f"DO NOT EDIT! This year activities were imported by the "
            f"{GoogleSheetsActivitiesImportPlugin.__name__} plugin."
        )
        do_not_edit_a.activity_type_key = activity_types_by_name["Comment"].key
        do_not_edit_a.src_descriptor = correlation_id
        entities.evaluate_activity(entity=do_not_edit_a, user_profile=user_profile)

        normalized_dict: dict[str, entities.ActivityEntity] = {
            do_not_edit_a.key: do_not_edit_a
        }
        skip = True
        key = 0
        for row in range(ds.shape[0]):
            # SEEK to TABLE w/ training data
            self.logger.debug(f"  Week # cell: {ds.iloc[row, 1]}")
            if ds.iloc[row, 1] == "Week":
                skip = False
                # calibration
                self.logger.debug("Year data HEADER detected - check:")
                self.logger.debug(f"  Week: {ds.iloc[row, 1]}")
                self.logger.debug(f"  Date: {ds.iloc[row, 2]}")
                self.logger.debug(f"  Mon : {ds.iloc[row, 3]}")
                self.logger.debug(f"  Tue : {ds.iloc[row, 4]}")
                self.logger.debug(f"  Wed : {ds.iloc[row, 5]}")
                self.logger.debug(f"  Thu : {ds.iloc[row, 6]}")
                self.logger.debug(f"  Fri : {ds.iloc[row, 7]}")
                self.logger.debug(f"  Sat : {ds.iloc[row, 8]}")
                self.logger.debug(f"  Sun : {ds.iloc[row, 9]}")
                self.logger.debug(f"  W km: {ds.iloc[row, 10]}")
                self.logger.debug(f"  kg  : {ds.iloc[row, 11]}")
                self.logger.debug(f"  D kg: {ds.iloc[row, 12]}")
                continue
            elif not skip and (
                ds.iloc[row, 2] == "Legenda" or pandas.isna(ds.iloc[row, 1])
            ):
                skip = True
                continue
            elif skip:
                continue

            # EXTRACT data from the TABLE w/ year data
            self.logger.debug(f"# EXTRACT row {row} ##################################")
            self.logger.debug(f"  Week: {ds.iloc[row, 1]}")
            # self.logger.debug(f"  Date: {ds[i, 2]}")
            # self.logger.debug(f"  Mon : {ds[i, 3]}")
            # self.logger.debug(f"  Tue : {ds[i, 4]}")
            # self.logger.debug(f"  Wed : {ds[i, 5]}")
            # self.logger.debug(f"  Thu : {ds[i, 6]}")
            # self.logger.debug(f"  Fri : {ds[i, 7]}")
            # self.logger.debug(f"  Sat : {ds[i, 8]}")
            # self.logger.debug(f"  Sun : {ds[i, 9]}")
            # self.logger.debug(f"  w km: {ds[i, 10]}")
            # self.logger.debug(f"  kg  : {ds[i, 11]}")
            # self.logger.debug(f"  delt: {ds[i, 12]}")
            # self.logger.debug(f"  w c : {ds[i, 13]}")

            if not ds.iloc[row, 1]:
                # TODO this is incomplete week - the FIRST or LAST in the year - TBD
                continue
            week = int(ds.iloc[row, 1]) - 1  # -1 added for 2023
            for d in range(3, 10):
                a_date: datetime.datetime = this._week_to_date(
                    year=year, week=week, week_day=d - 3
                )
                cell_str = ds.iloc[row, d]
                self.logger.debug(f"  Cell[{row},{d}]: '{cell_str}' ({type(cell_str)})")
                if not isinstance(cell_str, str):
                    if not cell_str or (
                        isinstance(cell_str, (int, float)) and math.isnan(cell_str)
                    ):
                        continue
                    cell_str = str(cell_str)

                activities, key = self._str_cell_2_activities(
                    cell_str=cell_str,
                    year=a_date.year,
                    month=a_date.month,
                    day=a_date.day,
                    user_profile=user_profile,
                    activity_types_by_name=activity_types_by_name,
                    symptoms_by_name=symptoms_by_name,
                    key=key,
                )
                for a in activities:
                    if a.key not in normalized_dict:
                        a.src_descriptor = correlation_id
                        normalized_dict[a.key] = a
                    else:
                        raise RuntimeError(
                            f"{self.log_name}: key conflict - activity '{a.key}' "
                            f"already exists in imported entities when importing "
                            f"Google Sheets cell [{row},{d}]: '{cell_str}' "
                            f"({type(cell_str)})"
                        )

            # WEEK SUMMARY w/ weight
            a_date = this._week_to_date(year=year, week=week, week_day=6)
            if year > a_date.year:
                a_date = datetime.datetime(year, 12, 31)
            a_ws = self._week_summary_2_activity(
                weight_cell_str=ds.iloc[row, 11],
                summary_cell=ds.iloc[row, 13],
                year=a_date.year,
                month=a_date.month,
                day=a_date.day,
                activity_types_by_name=activity_types_by_name,
            )
            if a_ws:
                normalized_dict[a_ws.key] = a_ws

        return year, list(normalized_dict.values())

    def import_activities(
        self,
        datasets: dict[str, list[pathlib.Path] | pathlib.Path | str],
        user_profile: settings.UserProfile,
        output_path: pathlib.Path | None = None,
        **kwargs,
    ) -> list[entities.ActivityEntity]:
        """Import activities from the Google Sheets CSV file.

        Extra parameters:

        january_1st_msg: str
            Message to insert to YYYY/1/1 - typically used to share an information like
            "Generated - do NOT edit", "Automatically generated", or "WIP".

        """
        correlation_id: str = kwargs.get("correlation_id", str(uuid.uuid4()))

        gsheets_csv_path = datasets.get(self.USE_TYPE_GSHEETS_CSV)
        if not gsheets_csv_path:
            raise ValueError(
                f"{self.log_name} Google Sheets CSV file is required, but was not "
                f"provided. "
            )
        if not gsheets_csv_path.exists():
            raise FileNotFoundError(
                f"{self.log_name} Unable to find Google Sheets CSV file: "
                f"{gsheets_csv_path}"
            )
        strava_json_path = datasets.get(self.USE_TYPE_STRAVA_JSON)
        if not strava_json_path:
            self.logger.warning(
                f"{self.log_name} strava.com activities JSON file is not provided "
                f"- Strava activities will NOT be merged"
            )
        elif not pathlib.Path(strava_json_path).exists():
            self.logger.warning(
                f"{self.log_name} WARNING: unable to find strava.com activities "
                f"JSON file: {strava_json_path} - will NOT be used"
            )
            strava_json_path = None

        # IMPORT activities from Google Sheets CSV
        year, normalized_list = self._import_csv(
            gsheet_csv_path=gsheets_csv_path,
            user_profile=user_profile,
            jan_1st_name=kwargs.get("january_1st_name", ""),
            jan_1st_description=kwargs.get("january_1st_description", ""),
            correlation_id=correlation_id,
        )

        # IMPORT add activities from the Strava for this year to have complete data
        if strava_json_path:
            strava_import_plugin = plugins.registry.get_plugin(
                strava.StravaActivitiesImportPlugin.NAME
            )
            strava_activities = strava_import_plugin.import_activities(
                datasets={
                    strava_import_plugin.USE_TYPE_STRAVA_JSON: strava_json_path,
                },
                user_profile=user_profile,
                year=year,
            )
            if strava_activities:
                for a in strava_activities:
                    a.src_descriptor = correlation_id
                    normalized_list.append(a)

        if output_path:
            persistences.save_json(
                file_path=output_path, data_dict=[a.to_dict() for a in normalized_list]
            )

        return normalized_list

    @staticmethod
    def _str_suffix_to_pct(cell_str: str) -> int:
        """Extract percentage from the given string suffix.

        Returns
        -------
        Optional[int] :
            Percentage of the health - 100% is healthy, 0% is totally sick.
            ``None`` if the string suffix does not contain percentage.

        """
        if not cell_str:
            return 0

        # count minuses at the end of string
        minuses = 0
        for c in reversed(cell_str):
            if c == "-":
                minuses += 1
            else:
                break
        pct = 100 - (minuses * 20)
        return max(0, pct) if pct < 100 else 90

    @staticmethod
    def _str_prefix_to_l_r(cell_str: str) -> str:
        return (
            entities.SS_SIDE_LEFT
            if cell_str.lower().startswith("l")
            else (entities.SS_SIDE_RIGHT if cell_str.lower().startswith("r") else "")
        )

    @staticmethod
    def _str_to_symptom(
        cell_str: str,
        activity: entities.ActivityEntity,
        activity_types_by_name: dict,
        symptoms_by_name: dict,
    ) -> None:
        """Extract sick/injury symptom from the given string and add it to given
        activity.xs

        """
        if not cell_str:
            return

        t_self = GoogleSheetsActivitiesImportPlugin

        activity.sickness_symptoms = activity.sickness_symptoms or []

        # note: intentionally fail fast if symptom is not known / does not exit
        if "BURSA" in cell_str or "ACHYL" in cell_str:
            symptom = entities.SicknessSymptomEntity(
                activity_key=activity.key,
                symptom=symptoms_by_name["bolest levé achylovy šlachy"].key,
                side=t_self._str_prefix_to_l_r(cell_str),
                body_part="bursa",
                health=t_self._str_suffix_to_pct(cell_str),
            )
            activity.sickness_symptoms.append(symptom)
            activity.activity_type_key = activity_types_by_name["Injured"].key

        if "RYMA" in cell_str:
            symptom = entities.SicknessSymptomEntity(
                activity_key=activity.key,
                symptom=symptoms_by_name["rýma"].key,
                side="",
                body_part="",
                health=t_self._str_suffix_to_pct(cell_str),
            )
            activity.sickness_symptoms.append(symptom)

        if "KASEL" in cell_str:
            symptom = entities.SicknessSymptomEntity(
                activity_key=activity.key,
                symptom=symptoms_by_name["kašel"].key,
                side="",
                body_part="",
                health=t_self._str_suffix_to_pct(cell_str),
            )
            activity.sickness_symptoms.append(symptom)

        if "RAMENO" in cell_str:
            side = (
                entities.SS_SIDE_LEFT
                if "LRAMENO" in cell_str
                else entities.SS_SIDE_RIGHT
            )
            symptom = entities.SicknessSymptomEntity(
                activity_key=activity.key,
                symptom=symptoms_by_name[
                    "zmrzlé pravé rameno"
                    if side == entities.SS_SIDE_RIGHT
                    else "zmrzlé levé rameno"
                ].key,
                side=side,
                body_part="shoulder",
                health=t_self._str_suffix_to_pct(cell_str),
            )
            activity.sickness_symptoms.append(symptom)

        if "PODBRICH" in cell_str:
            symptom = entities.SicknessSymptomEntity(
                activity_key=activity.key,
                symptom=symptoms_by_name["bolest"].key,
                side=t_self._str_prefix_to_l_r(cell_str),
                body_part="abdominal",
                health=t_self._str_suffix_to_pct(cell_str),
            )
            activity.sickness_symptoms.append(symptom)

        if "CESKA" in cell_str:
            symptom = entities.SicknessSymptomEntity(
                activity_key=activity.key,
                symptom=symptoms_by_name["bolest"].key,
                side=t_self._str_prefix_to_l_r(cell_str),
                body_part="knee-cap",
                health=t_self._str_suffix_to_pct(cell_str),
            )
            activity.sickness_symptoms.append(symptom)
            activity.activity_type_key = activity_types_by_name["Injured"].key

        if "KOLEN" in cell_str:
            symptom = entities.SicknessSymptomEntity(
                activity_key=activity.key,
                symptom=symptoms_by_name["bolest"].key,
                body_part="knees",
                health=t_self._str_suffix_to_pct(cell_str),
            )
            activity.sickness_symptoms.append(symptom)
            activity.activity_type_key = activity_types_by_name["Injured"].key

        if "PSOAR" in cell_str:
            symptom = entities.SicknessSymptomEntity(
                activity_key=activity.key,
                symptom=symptoms_by_name["bolest"].key,
                body_part="bedra",
                health=t_self._str_suffix_to_pct(cell_str),
            )
            activity.sickness_symptoms.append(symptom)
            activity.activity_type_key = activity_types_by_name["Injured"].key

        if "PALEC" in cell_str:
            symptom = entities.SicknessSymptomEntity(
                activity_key=activity.key,
                symptom=symptoms_by_name["bolest"].key,
                body_part="palec",
                health=t_self._str_suffix_to_pct(cell_str),
            )
            activity.sickness_symptoms.append(symptom)
            activity.activity_type_key = activity_types_by_name["Injured"].key

        if "TROMB" in cell_str:
            symptom = entities.SicknessSymptomEntity(
                activity_key=activity.key,
                symptom=symptoms_by_name["trombóza"].key,
                side="",
                body_part="",
                health=t_self._str_suffix_to_pct(cell_str),
            )
            activity.sickness_symptoms.append(symptom)

        # summary
        if activity.sickness_symptoms:
            for s in activity.sickness_symptoms:
                app_logger.debug(
                    f"  SYMPTOM: {s.symptom} {s.side} {s.body_part} {s.health}%"
                )

    @staticmethod
    def _str_to_exercise(cell_str: str, activity: entities.ActivityEntity) -> None:
        """Extract exercise from the cell string and add it as exercise to the activity,
        for example:

        - 5x20 7kg biceps

        """
        if not cell_str:
            return

        # parse string using the regular expression
        pattern = "^(\\d+)x(\\d+) (\\d+)kg (.+)$"

        m = re.match(pattern, cell_str)
        if m:
            series = int(m.group(1))
            repetitions = int(m.group(2))
            weight = int(m.group(3))

            titles = []
            if "cisty" in cell_str:
                titles.append("čistý ruce")
            if "bic" in cell_str:
                titles.append("biceps")
            activity.exercises = activity.exercises or []
            for t in titles:
                e = entities.ExerciseEntity(
                    activity_key=activity.key,
                    name=f"{series}x{repetitions} {weight}kg {t}",
                    weight=weight,
                    series=series,
                    repetitions=repetitions,
                    # duration / rest unused
                )
                activity.exercises.append(e)

    @staticmethod
    def _str_to_sauna(
        cell_str: str, activity: entities.ActivityEntity, sauna_or_steam: str = "sauna"
    ) -> None:
        if not cell_str:
            return

        # split by space
        formula = ""
        whos = []
        rounds = 0
        parts = cell_str.split(" ")
        for p in parts:
            if p.endswith("x") and len(p) == 2:
                formula = p
                rounds = int(p.replace("x", ""))
            elif p == sauna_or_steam:
                continue
            else:
                if "k" in p:
                    whos.append("Kuba")
                if "m" in p:
                    whos.append("Miky")

        title_with = f" w/ {' and '.join(whos)}" if whos else ""

        activity.name = f"{rounds}x sauna{title_with}"
        activity.description = "🧍" * len(whos)
        activity.formula = formula


# PLUGINS REGISTRY: register Google Sheets plugin
plugins.registry.register(GoogleSheetsActivitiesImportPlugin())


class GoogleSheetsRacesImportPlugin(plugins.ActivitiesImportPlugin):
    """Google Sheets - proprietary training log - activities import plugin."""

    NAME = "Google Sheets races import"
    DESCRIPTION = (
        "Imports race activities from the proprietary MyTraL Google Sheets "
        "training log. Activities will be added to year activity file datasets "
        "with unique source key and descriptor for subsequent management."
    )

    USE_TYPE_GSHEETS_CSV = "USE_TYPE_GSHEETS_CSV"

    def __init__(
        self,
        logger: loggers.MytralLogger | None = None,
    ):
        """Constructor."""
        plugins.ActivitiesImportPlugin.__init__(
            self,
            name=GoogleSheetsRacesImportPlugin.NAME,
            description=GoogleSheetsActivitiesImportPlugin.DESCRIPTION,
        )

        self.log_name = f"[{self.name}]"
        self.logger = logger or app_logger

    def import_activities(
        self,
        datasets: dict[str, list[pathlib.Path] | pathlib.Path | str],
        user_profile: settings.UserProfile,
        output_path: pathlib.Path | None = None,
        **kwargs,
    ) -> list[entities.ActivityEntity]:
        """Convert from CSV to running activities."""
        correlation_id: str = kwargs.get("correlation_id", str(uuid.uuid4()))

        self.logger.info(
            f"{self.log_name} Importing RACE activities from Google Sheets CSV file "
            f"...",
            correlation_id=correlation_id,
        )

        gsheets_csv_path = datasets.get(self.USE_TYPE_GSHEETS_CSV)
        if not gsheets_csv_path:
            raise ValueError(
                f"{self.log_name} Google Sheets CSV file is required, but was not "
                f"provided"
            )
        if not gsheets_csv_path.exists():
            raise FileNotFoundError(
                f"{self.log_name} Unable to find Google Sheets CSV file: "
                f"{gsheets_csv_path}"
            )

        # IMPORT activities from Google Sheets CSV
        normalized_list = self._import_csv(
            gsheet_csv_path=gsheets_csv_path, correlation_id=correlation_id
        )

        if output_path:
            persistences.save_json(
                file_path=output_path,
                data_dict=[a.to_dict() for a in normalized_list],
            )

        return normalized_list

    def _import_csv(
        self, gsheet_csv_path: pathlib.Path, correlation_id: str
    ) -> list[entities.ActivityEntity]:
        races_csv = gsheet_csv_path

        ds = pandas.read_csv(races_csv, header=None, index_col=None)
        self.logger.info(
            f"{self.log_name} Google Sheets CSV file shape: {ds.shape}",
            correlation_id=correlation_id,
        )

        ds[2] = pandas.to_timedelta(
            ds[2]
        ).dt.total_seconds()  # convert str duration to s

        # type / name / time h:mm:ss / date m/d/yyyy / km xx,xxx / speed / pace / notes
        activities_list = []
        for i in range(ds.shape[0]):
            a = entities.ActivityEntity()
            a.key = str(uuid.uuid4())

            a.race = True

            a.name = ds.iloc[i, 1]
            self.logger.debug(
                f"{self.log_name} importing Google Sheets CSV activity: '{a.name}'",
                correlation_id=correlation_id,
            )

            a.duration_seconds = int(ds.iloc[i, 2])
            a.duration = cals.seconds_to_str_time(a.duration_seconds)

            a.hours, a.minutes, a.seconds = cals.seconds_to_tuple(a.duration_seconds)

            when_m, when_d, when_y = ds.iloc[i, 3].split("/")
            a.when_year = int(when_y)
            a.when_month = int(when_m)
            a.when_day = int(when_d)
            a.when_hour = 9
            a.when_minute = 0
            a.when_second = 0

            a.distance = int(ds.iloc[i, 4].replace(",", ""))

            a = entities.evaluate_activity(a)

            # inject unique src identifier for purging / filtering / mgmt
            a.src = self.key()
            a.src_key = ""  # no 3rd party key
            a.src_descriptor = correlation_id
            # bind URL to proprietary Google Sheets training log
            a.src_url = "https://docs.google.com/spreadsheets/1QW...2a8"

            activities_list.append(a)

        self.logger.info(
            f"{self.log_name} converted {len(activities_list)} activities from Google "
            f"Sheets CSV",
            correlation_id=correlation_id,
        )

        return activities_list


# PLUGINS REGISTRY: register races Google Sheets plugin
plugins.registry.register(GoogleSheetsRacesImportPlugin())


class GoogleSheetsAllYearsImportPlugin(plugins.ActivitiesImportPlugin):
    """Google Sheets "All years" summary CSV - activities import plugin.

    Imports one activity per activity_type_key per year from the proprietary MyTraL
    Google Sheets yearly summary CSV.  Each row represents a full calendar
    year; each activity_type_key column is converted to a single ``ActivityEntity``
    placed on January 1st of that year.

    CSV columns description
    -----------------------
    "Year"
        Calendar year used as the row index.
    "Universal km"
        [distance, summary] total universal kilometres across all activity_types.
    "Running"
        [distance] total running kilometres for the year.
    "Rowing"
        [distance] total rowing kilometres for the year.
    "Bike"
        [distance] total cycling kilometres for the year.
    "Ski"
        [distance] total cross-country skiing kilometres for the year.
    "Swim h:m:s"
        [hours, minutes, seconds] total swimming time in HH:MM:SS format;
        distance is estimated at a 2:30/100m pace.

    Time estimation
    ---------------
    Running  : pace  3:09/km  (3.15 s/m)
    Rowing   : pace  3:20/km  (3.33 s/m)
    Bike     : speed 18 km/h  (distance / 5 m/s)
    Ski      : pace  3:20/km  (3.33 s/m)
    Swimming : distance estimated from time (800 m per 1200 s)

    """

    NAME = "Google Sheets all years import"
    DESCRIPTION = (
        "Imports yearly activity summaries from the proprietary MyTraL "
        "Google Sheets 'All years' CSV export. Creates one activity per "
        "activity_type_key per year placed on January 1st of that year."
    )

    USE_TYPE_GSHEETS_ALL_YEARS_CSV = "USE_TYPE_GSHEETS_ALL_YEARS_CSV"

    # CSV column names
    _COL_YEAR = "Year"
    _COL_UKM = "Universal km"
    _COL_RUNNING = "Running"
    _COL_ROWING = "Rowing"
    _COL_BIKE = "Bike"
    _COL_SKI = "Ski"
    _COL_SWIM = "Swim h:m:s"

    def __init__(
        self,
        logger: loggers.MytralLogger | None = None,
    ):
        """Constructor."""
        plugins.ActivitiesImportPlugin.__init__(
            self,
            name=GoogleSheetsAllYearsImportPlugin.NAME,
            description=GoogleSheetsActivitiesImportPlugin.DESCRIPTION,
        )

        self.log_name = f"[{self.name}]"
        self.logger = logger or app_logger

    @staticmethod
    def _km_to_meters(value) -> int:
        """Convert a CSV km value (possibly with comma separators) to meters."""
        return int(cals.str_time_to_seconds(value) * 1_000)

    @staticmethod
    def _swim_seconds_and_meters(value) -> tuple[int, int]:
        """Return (seconds, meters) for the swimming HH:MM:SS cell value."""
        swim_seconds = cals.str_time_to_seconds(value)
        swim_meters = int(swim_seconds / 1_200 * 800)
        return swim_seconds, swim_meters

    def _year_row_to_activities(
        self,
        year: int,
        row_values: list,
        user_profile: settings.UserProfile,
        seq: int,
        correlation_id: str,
    ) -> tuple[list[entities.ActivityEntity], int]:
        """Convert one all-years CSV row to a list of ActivityEntity objects.

        Parameters
        ----------
        year : int
            Calendar year for this row.
        row_values : list
            Remaining column values after the Year index, in CSV order:
            [Universal km, Running, Rowing, Bike, Ski, Swim h:m:s].
        user_profile : settings.UserProfile
            User profile for BMI calculation.
        seq : int
            Current sequence counter used to generate deterministic keys.
        correlation_id : str
            ID to identify activities imported in the same batch for subsequent
            management.

        Returns
        -------
        tuple[list[entities.ActivityEntity], int]
            Converted activities and updated sequence counter.

        """
        ds_values = [cals.str_time_to_seconds(v) for v in row_values]

        # distance in meters per activity_type_key
        running_m = int(ds_values[1] * 1_000)
        rowing_m = int(ds_values[2] * 1_000)
        bike_m = int(ds_values[3] * 1_000)
        ski_m = int(ds_values[4] * 1_000)
        swim_s, swim_m = self._swim_seconds_and_meters(row_values[5])
        ukm_m = int(ds_values[0] * 1_000)

        # time in seconds per activity_type_key (estimated from distance or measured)
        running_s = int(running_m * 3.15)  # ~3:09/km
        rowing_s = int(rowing_m * 3.33)  # ~3:20/km
        bike_s = int(bike_m / 5.0)  # 18 km/h = 5 m/s
        ski_s = int(ski_m * 3.33)  # ~3:20/km

        # total time for ukm summary activity
        total_s = running_s + rowing_s + bike_s + ski_s + swim_s

        sport_data: list[tuple[str, int, int]] = [
            (commons.AT_RUN, running_m, running_s),
            (commons.AT_ROW, rowing_m, rowing_s),
            (commons.AT_RIDE, bike_m, bike_s),
            (commons.AT_SKI_F, ski_m, ski_s),
            (commons.AT_SWIM, swim_m, swim_s),
            ("ukm", ukm_m, total_s),
        ]
        # skip activity_types with no distance
        sport_data = [(sp, m, s) for sp, m, s in sport_data if m > 0]

        activities: list[entities.ActivityEntity] = []
        for sport, dist_m, time_s in sport_data:
            seq += 1
            h, m_min, m_sec = cals.seconds_to_tuple(time_s)
            a = entities.ActivityEntity(
                key=f"seq-{seq}",
                when_year=int(year),
                when_month=1,
                when_day=1,
                when_hour=1,
                when_minute=0,
                when_second=0,
                name=f"Yearly {sport}",
                description=f"Sum of all {sport} activities in {year}.",
                activity_type_key=sport,
                hours=int(h),
                minutes=int(m_min),
                seconds=int(m_sec),
                distance=int(dist_m),
                src="gdocs-log-import-SUMMARY",
                src_descriptor=correlation_id,
            )
            entities.evaluate_activity(a, user_profile=user_profile)
            activities.append(a)

        return activities, seq

    def import_activities(
        self,
        datasets: dict[str, list[pathlib.Path] | pathlib.Path | str | list[dict]],
        user_profile: settings.UserProfile,
        output_path: pathlib.Path | None = None,
        **kwargs,
    ) -> list[entities.ActivityEntity]:
        """Import yearly summary activities from the Google Sheets all-years CSV.

        Parameters
        ----------
        datasets : dict
            Must contain the key ``USE_TYPE_GSHEETS_ALL_YEARS_CSV`` mapping to a
            :class:`pathlib.Path` pointing at the exported CSV file.
        user_profile : settings.UserProfile
            Profile of the user the activities will be imported for.
        output_path : pathlib.Path or None
            When provided, the converted activities are also persisted as a JSON
            file at this path.
        **kwargs
            Additional keyword arguments (ignored).

        Returns
        -------
        list[entities.ActivityEntity]
            List of converted activities (one per activity_type_key per year row).

        Raises
        ------
        ValueError
            When the required CSV dataset path is missing.
        FileNotFoundError
            When the CSV file does not exist.

        """
        correlation_id: str = kwargs.get("correlation_id", str(uuid.uuid4()))

        csv_path = datasets.get(self.USE_TYPE_GSHEETS_ALL_YEARS_CSV)
        if not csv_path:
            raise ValueError(
                f"{self.log_name} Google Sheets all-years CSV file is required "
                f"but was not provided."
            )
        csv_path = pathlib.Path(csv_path)
        if not csv_path.exists():
            raise FileNotFoundError(
                f"{self.log_name} Google Sheets all-years CSV file not found: "
                f"{csv_path}"
            )

        self.logger.info(
            f"{self.log_name} Loading Google Sheets all-years CSV",
            csv_path=str(csv_path),
        )

        df: pandas.DataFrame = pandas.read_csv(csv_path, index_col=self._COL_YEAR)
        self.logger.info(
            f"{self.log_name} CSV loaded",
            rows=df.shape[0],
            columns=df.shape[1],
        )

        activities: list[entities.ActivityEntity] = []
        seq = 0
        for year in df.index.values:
            try:
                row_values = df.loc[year].tolist()
                year_activities, seq = self._year_row_to_activities(
                    year=int(year),
                    row_values=row_values,
                    user_profile=user_profile,
                    seq=seq,
                    correlation_id=correlation_id,
                )
                activities.extend(year_activities)
            except Exception as e:
                self.logger.error(
                    f"{self.log_name} Failed to convert year row",
                    error=str(e),
                    year=year,
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


# PLUGINS REGISTRY: register all-years Google Sheets plugin
plugins.registry.register(GoogleSheetsAllYearsImportPlugin())
