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

"""Strava user archive ZIP import plugin:

- User may request all data from Strava as a ZIP archive,
  typically it takes a few hours, but the archive contains anything
  and everything user created/uploaded at Strava
- Archive ZIP layout looks as follows:

  ZIP/
    activities/
      *.gpx
      *.tcx.gz     ... training center database
    clubs/
    media/
      *.jpg        ... photos (up to 2k)
    routes/
      *.gpx

    activities.csv ... activities
    ...
    bikes.csv      ... bikes w/o ID
    shoes.csv      ... shoes w/o ID
    ...
    comments.csv   ... list of comments w/o activity association (useless)
    components.csv ... basically bikes
    ...
    general_preferences.csv ... born, weight, height, FTP max HR, ...
    ...
    goals.csv      ... can be imported
    ...
    media.csv      ... photos descriptions
    ...
    profile.csv    ... athlete ID, email, display name, motto, gender, where, ...
    profile.jpg
    ...
    routes.csv     ... route name to GPX file


"""

import pathlib
import traceback
import uuid
from datetime import datetime

import pandas

from mytral import app_logger
from mytral import app_user_ds
from mytral import loggers
from mytral import persistences
from mytral import plugins
from mytral import settings
from mytral.backends import entities
from mytral.integrations import strava

STRAVA_ARCHIVE_DATA_DIR_KEY = "USE_TYPE_STRAVA_USR_BULK_EXPORT_DIR"


class StravaUserArchiveActivitiesImportPlugin(plugins.ActivitiesImportPlugin):
    NAME = "Strava user archive activities import"
    DESCRIPTION = (
        "Imports activities, photos and GPX recordings from proprietary Strava user "
        "archive bulk export"
    )

    # activities.csv columns
    _COL_A_CSV_ID = "Activity ID"  # 0
    _COL_A_CSV_DATE = "Activity Date"  # 1
    _COL_A_CSV_NAME = "Activity Name"  # 2
    _COL_A_CSV_TYPE = "Activity Type"  # 3
    _COL_A_CSV_DESCRIPTION = "Activity Description"  # 4
    _COL_A_CSV_ELAPSED_TIME = "Elapsed Time"  # 5
    _COL_A_CSV_DISTANCE = "Distance"  # 7: km > DUPLICATED - really? :-Z
    _COL_A_CSV_MAX_HR = "Max Heart Rate"  # 8" float
    _COL_A_CSV_REL_EFFORT = "Relative Effort"  # 9
    _COL_A_CSV_COMMUTE = "Commute"  # 10: bool
    _COL_A_CSV_PRIVATE_NOTE = "Activity Private Note"  # 10: bool
    _COL_A_CSV_GEAR = "Activity Gear"  # 11: display name :-Z
    _COL_A_CSV_GPX = "Filename"  # 12: activities/*.gpx
    _COL_A_CSV_WEIGHT = "Athlete Weight"  # 13: kg / int
    _COL_A_CSV_BIKE_WEIGHT = "Bike Weight"  # 13: kg / int
    # _COL_A_CSV_ELAPSED_TIME = "Elapsed Time" # ?: m > DUPLICATED - really? :-Z
    _COL_A_CSV_MOVING_TIME = "Moving Time"  # ?: s / int
    # _COL_A_CSV_DISTANCE = "Distance" # 14: m / float > DUPLICATED - really? :-Z
    _COL_A_MAX_SPEED = "Max Speed"  # ?: km/h / float
    _COL_A_AVG_SPEED = "Average Speed"  # ?: km/h / float
    _COL_A_ELEVATION_GAIN = "Elevation Gain"  # ?: m / float
    _COL_A_ELEVATION_LOSS = "Elevation Loss"  # ?: m / float
    _COL_A_ELEVATION_LOW = "Elevation Low"  # ?: m / float
    _COL_A_ELEVATION_HIGH = "Elevation High"  # ?: m / float
    _COL_A_MAX_GRADE = "Max Grade"  # ?: float
    _COL_A_AVG_GRADE = "Average Grade"  # ?: float (+/-)
    _COL_A_AVG_POS_GRADE = "Average Positive Grade"  # ?: float (+/-) :-Z is negative
    _COL_A_AVG_NEG_GRADE = "Average Negative Grade"  # ?: float
    _COL_A_AVG_CADENCE = "Average Cadence"  # ?
    _COL_A_MAX_HR = "Max Heart Rate"
    _COL_A_AVG = "Average Heart Rate"
    _COL_A_MAX_WATTS = "Max Watts"
    _COL_A_AVG_WATTS = "Average Watts"  # ?: int
    _COL_A_CALORIES = "Calories"  # ?: int
    _COL_A_MAX_TEMPERATURE = "Max Temperature"  # ? strange units
    _COL_A_AVG_TEMPERATURE = "Average Temperature"  # ? strange units
    # TODO ...
    _COL_A_CSV_BIKE = "Bike"  # actual gear ID
    _COL_A_CSV_GEAR = "Gear"  # DUPLICATED col w/ actual gear ID - ONLY if ^ not spec.
    # TODO ...
    _COL_A_CSV_MEDIA = "Media"  # | separated list of photo paths

    _COLS_A_CSV = [
        _COL_A_CSV_ID,
        _COL_A_CSV_DATE,
        _COL_A_CSV_NAME,
        _COL_A_CSV_TYPE,
        _COL_A_CSV_DESCRIPTION,
        _COL_A_CSV_ELAPSED_TIME,
        _COL_A_CSV_DISTANCE,
        _COL_A_CSV_MAX_HR,
        _COL_A_CSV_REL_EFFORT,
        _COL_A_CSV_COMMUTE,
        _COL_A_CSV_PRIVATE_NOTE,
        _COL_A_CSV_GEAR,
        _COL_A_CSV_GPX,
        _COL_A_CSV_WEIGHT,
        _COL_A_CSV_BIKE_WEIGHT,
        _COL_A_CSV_MOVING_TIME,
        _COL_A_MAX_SPEED,
        _COL_A_AVG_SPEED,
        _COL_A_ELEVATION_GAIN,
        _COL_A_ELEVATION_LOSS,
        _COL_A_ELEVATION_LOW,
        _COL_A_ELEVATION_HIGH,
        _COL_A_MAX_GRADE,
        _COL_A_AVG_GRADE,
        _COL_A_AVG_POS_GRADE,
        _COL_A_AVG_NEG_GRADE,
        _COL_A_AVG_CADENCE,
        _COL_A_MAX_HR,
        _COL_A_AVG,
        _COL_A_MAX_WATTS,
        _COL_A_AVG_WATTS,
        _COL_A_CALORIES,
        _COL_A_MAX_TEMPERATURE,
        _COL_A_AVG_TEMPERATURE,
        _COL_A_CSV_BIKE,
        _COL_A_CSV_GEAR,
        _COL_A_CSV_MEDIA,
    ]

    # param use type: Strava directory w/ extracted user bulk export archive
    USE_TYPE_STRAVA_USR_BULK_EXPORT_DIR = "USE_TYPE_STRAVA_USR_BULK_EXPORT_DIR"

    def __init__(
        self,
        logger: loggers.MytralLogger | None = None,
    ):
        """Constructor."""
        plugins.ActivitiesImportPlugin.__init__(
            self,
            name=StravaUserArchiveActivitiesImportPlugin.NAME,
            description=StravaUserArchiveActivitiesImportPlugin.DESCRIPTION,
        )

        self.log_name = f"[{self.name}]"
        self.logger = logger or app_logger

        self._api_a_plugin = strava.StravaActivityImportPlugin(logger=self.logger)

    def _import_a_csv_parse_date(self, data_str: str) -> tuple:
        """Parses a timestamp string like 'Aug 31, 2013, 4:55:18 AM'

        and returns a tuple of (year, month, day, hour, minute, second).
        """
        if not data_str:
            return None, None, None, None, None, None

        # Format breakdown:
        # %b = Abbreviated month name (e.g., Aug)
        # %d = Day of the month as a zero-padded decimal (e.g., 31)
        # %Y = Year with century as a decimal number (e.g., 2013)
        # %I = Hour (12-hour clock) as a zero-padded decimal (e.g., 04 or 4)
        # %M = Minute as a zero-padded decimal (e.g., 55)
        # %S = Second as a zero-padded decimal (e.g., 18)
        # %p = Locale’s equivalent of either AM or PM.
        dt_format = "%b %d, %Y, %I:%M:%S %p"

        try:
            # Strip any accidental leading/trailing whitespace
            dt = datetime.strptime(data_str.strip(), dt_format)
            return dt.year, dt.month, dt.day, dt.hour, dt.minute, dt.second
        except ValueError as e:
            # Handle cases where the string doesn't match the expected format
            self.logger.error(
                f"Error parsing timestamp '{data_str}': {e}",
                error=str(e),
                traceback=traceback.format_exc(),
            )
            return None, None, None, None, None, None

    def _import_activities_csv(
        self,
        strava_archive_dir: pathlib.Path,
        user_profile: settings.UserProfile,
        correlation_id: str,
        output_path: pathlib.Path | None = None,
    ) -> list[entities.ActivityEntity]:
        this = StravaUserArchiveActivitiesImportPlugin

        activities: list[entities.ActivityEntity] = []
        raw_activities_csv_path = strava_archive_dir / "activities.csv"

        # LOAD CSV w/ activities
        df = pandas.read_csv(raw_activities_csv_path, index_col=None)
        self.logger.info(f"Activities CSV shape: {df.shape}")
        self.logger.info("Activities CSV columns:")
        df_col2idx: dict[str, int] = {}
        for e, c in enumerate(df.columns):
            self.logger.info(f"  Column #{e}: '{c}'")
            df_col2idx[c] = e

        missing = []  # missing columns ~ attributes
        col2idx: dict[str, int] = {}
        for col2import_name in this._COLS_A_CSV:
            idx = df_col2idx.get(col2import_name, None)
            if idx is None:
                missing.append(this._COL_A_CSV_NAME)
                app_logger.error(
                    f"{self.log_name} unable to find activities dataset column "
                    f"'{this._COL_A_CSV_NAME}'"
                )
            else:
                col2idx[col2import_name] = idx

        for _, row in df.iterrows():  # row: pandas.Series
            a = entities.ActivityEntity()
            a.key = app_user_ds.create_key()
            a.src = strava.SRC_STRAVA
            a.src_key = row[0]
            a.src_url = f"{strava.SRC_STRAVA_BASE_URL}{a.src_key}"
            a.src_descriptor = f"archive:{correlation_id}"

            p = this._COL_A_CSV_NAME
            a.name = (row[col2idx[p]] or "Activity") if p not in missing else "Activity"

            p = this._COL_A_CSV_DESCRIPTION
            value = row[col2idx[p]] if p not in missing else ""
            a.description = value if isinstance(value, str) else ""

            # Aug 31, 2013, 4:55:18 AM
            p = this._COL_A_CSV_DATE
            data_str = row[col2idx[p]] if p not in missing else ""
            if data_str:
                (
                    a.when_year,
                    a.when_month,
                    a.when_day,
                    a.when_hour,
                    a.when_minute,
                    a.when_second,
                ) = self._import_a_csv_parse_date(data_str)
            else:
                raise ValueError(
                    f"{self.log_name} unable to parse activity date from'{data_str}'"
                )

            p = this._COL_A_CSV_MEDIA
            data_str = row[col2idx[p]] if p not in missing else ""
            photo_paths = []
            if data_str and not pandas.isna(data_str):
                photo_paths = data_str.split("|")
            self.logger.info(f"Photo paths of activity '{a.name}': {photo_paths}")

            # TODO
            # TODO photos
            # TODO

            entities.evaluate_activity(entity=a, user_profile=user_profile)

            activities.append(a)

        # # activity types: Strava -> MyTraL mapping - LIST
        # valid_activity_type_ids = list(
        #     app_user_ds.list_activity_types(
        #         user_id=user_profile.user_id
        #     ).activity_types_by_key.keys()
        # )
        #
        # # gear: Strava -> MyTraL mapping - map: strava ID -> MyTraL ID
        # strava_gear_dict = app_user_ds.list_gear(
        #     user_id=user_profile.user_id
        # ).to_dict_by_strava_key()

        # self.logger.info(
        #     f"{self.log_name} importing {len(raw_activities)} Strava activities..."
        # )
        # activities = []
        # for e, strava_item in enumerate(raw_activities):
        #    if year_str and not strava_item.get("start_date", "").startswith(year_str):
        #         self.logger.info(
        #             f"{self.log_name} SKIPPING Strava activity (year filter) #{e}"
        #         )
        #         continue
        #
        #     self.logger.info(f"{self.log_name} importing Strava activity #{e}")
        #     activity_entity = self.activity_import_plugin.import_activity(
        #         dataset_item=strava_item,
        #         user_profile=user_profile,
        #         valid_activity_type_ids=valid_activity_type_ids,
        #         strava_gear_dict=strava_gear_dict,
        #         correlation_id=correlation_id,
        #     )
        #
        #     activities.append(activity_entity)

        if output_path:
            activities_json_path = pathlib.Path(output_path) / "activities.json"
            persistences.save_json(
                file_path=activities_json_path,
                data_dict=[a.to_dict() for a in activities],
            )
            self.logger.info(
                f"{self.log_name} saved activities to file://{activities_json_path}"
            )

        return activities

    def import_activities(
        self,
        datasets: dict[str, pathlib.Path | str | list],
        user_profile: settings.UserProfile,
        output_path: pathlib.Path | None = None,
        **kwargs,
    ) -> list[entities.ActivityEntity]:
        """Import Strava activities.

        Parameters
        ----------
        datasets: dict[str, list[pathlib.Path | pathlib.Path | str | list[dict]]]
            Dataset might be:
            - dict[str, Path] ... use type to dir specified as Path
            - dict[str, str] ... use type to dir specified as string
        user_profile: settings.UserProfile
            User profile.
        output_path: pathlib.Path | None
            Optional path where to write imported MyTraL JSON activities.
        kwargs: dict
            Extra parameters:
              correlation_id: str ... UUID to be used to mark imported activities

        """
        self.logger.info(
            f"{self.log_name} importing activities from the Strava user archive..."
        )

        this = StravaUserArchiveActivitiesImportPlugin
        correlation_id: str = kwargs.get("correlation_id", str(uuid.uuid4()))

        strava_archive_dir = datasets.get(self.USE_TYPE_STRAVA_USR_BULK_EXPORT_DIR)
        if not strava_archive_dir:
            raise ValueError(
                f"{self.log_name} raw Strava user archive directory not provided "
                f"as dataset with use type {this.USE_TYPE_STRAVA_USR_BULK_EXPORT_DIR}"
            )
        elif not pathlib.Path(strava_archive_dir).exists():
            raise ValueError(
                f"{self.log_name} unable to find Strava archive archive directory: "
                f"'{strava_archive_dir}'"
            )

        # archive PATHS
        strava_archive_dir = pathlib.Path(strava_archive_dir)

        # IMPORT: activities
        activities = self._import_activities_csv(
            strava_archive_dir=strava_archive_dir,
            user_profile=user_profile,
            correlation_id=correlation_id,
            output_path=output_path,
        )

        return activities


# PLUGINS REGISTRY: register strava.com activities import plugin
plugins.registry.register(StravaUserArchiveActivitiesImportPlugin())
