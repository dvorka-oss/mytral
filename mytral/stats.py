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
import dataclasses
import datetime
import json
from typing import Self

from mytral import athlete_metrics as am_module
from mytral import cals
from mytral import commons
from mytral import loggers
from mytral import settings
from mytral.backends import entities
from mytral.integrations import icommons

# kCal to fat burnt: 9000 kCal == 1 kg ... x / CONST = result kg
KCAL_2_BURNT_FAT: float = 9_082
# kJ to fat burnt: 9000 kJ == 1 kg
KJ_2_BURNT_FAT: float = 38_000

# 1 kJ = 0.239 kCal: x * CONST = result kCal
KJ_2_KCAL = 0.232
# 1 kcal = 4.1841 kJ: x * CONST = result kJ
KCAL_2_KJ = 4.1841


# TODO to dataclasses


class UserProfileStats:
    THRESHOLD_BMI_MIN = 18.5  # lower healthy BMI threshold
    THRESHOLD_BMI_MAX = 25.0  # upper healthy BMI threshold

    # labels for resting_hr_source
    RHR_SOURCE_MEASURED = "measured"  # from activity min_hr
    RHR_SOURCE_ESTIMATED = "estimated"  # from age-based formula
    RHR_SOURCE_DEFAULT = "default"  # hardcoded fallback

    def __init__(self) -> None:
        self.weight: float = 0.0  # kg ... last weight from activities
        # Body Mass Index
        self.bmi: float = 0.0  # kg/m^2 ... weight / height^2
        # BMI ranking
        self.bmi_rank: str = "normal"
        # Base Metabolic Rate: base metabolism in kCal
        self.bmr: float = 0.0
        self.resting_hr: int = 0  # last Resting HR from activities
        self.resting_hr_source: str = ""  # measured | estimated | default

    @staticmethod
    def _estimate_resting_hr(age: int) -> int:
        """Estimate resting HR for a trained athlete based on age.

        There is no gold-standard formula — RHR reflects training adaptation,
        not a fixed mathematical output of age/weight.  This heuristic returns
        a value in the 40–60 bpm range typical of trained athletes, with a
        mild age correlation (older athletes tend to have slightly higher RHR).

        Parameters
        ----------
        age : int
            Athlete age in years.

        Returns
        -------
        int
            Estimated resting HR in BPM (clamped to 40–60).
        """
        # base 50 bpm at age 30, ±0.15 bpm per year of age
        estimated = round(50 + (age - 30) * 0.15)
        # clamp to the trained-athlete range
        if estimated < 40:
            return 40
        if estimated > 60:
            return 60
        return estimated

    @staticmethod
    def from_entity(
        user_profile: settings.UserProfile,
        activities: list[entities.ActivityEntity],
        logger: loggers.MytralLogger,
    ):
        user_profile_stats = UserProfileStats()

        # lookup last weight and resting HR - ensure activities are SORTED
        logger.info("LATEST weight/resting_hr lookup:")
        activities = sorted(activities, key=lambda aa: aa.when, reverse=False)
        for a in reversed(activities):
            if not user_profile_stats.weight and a.weight:
                logger.info(f"    USING {a.when}: weight {a.weight}")
                user_profile_stats.weight = a.weight
            if not user_profile_stats.resting_hr and a.min_hr:
                logger.info(f"    USING {a.when}: resting_hr {a.min_hr}")
                user_profile_stats.resting_hr = a.min_hr
                user_profile_stats.resting_hr_source = (
                    UserProfileStats.RHR_SOURCE_MEASURED
                )

            if user_profile_stats.weight and user_profile_stats.resting_hr:
                break

        # when no activity carries a measured resting HR, estimate from age
        if not user_profile_stats.resting_hr:
            age = user_profile.age or settings.UserProfile.DEFAULT_AGE
            user_profile_stats.resting_hr = UserProfileStats._estimate_resting_hr(age)
            user_profile_stats.resting_hr_source = UserProfileStats.RHR_SOURCE_ESTIMATED
            logger.info(
                f"    ESTIMATED resting_hr={user_profile_stats.resting_hr} "
                f"from age={age}"
            )

        if user_profile.height and user_profile_stats.weight:
            # BMI
            user_profile_stats.bmi = float(user_profile_stats.weight) / (
                float(user_profile.height) * float(user_profile.height)
            )
            if user_profile_stats.bmi < UserProfileStats.THRESHOLD_BMI_MIN:
                user_profile_stats.bmi_rank = "underweight"
            elif user_profile_stats.bmi > UserProfileStats.THRESHOLD_BMI_MAX:
                user_profile_stats.bmi_rank = "overweight"
            else:
                user_profile_stats.bmi_rank = "normal"
            logger.info(f"BMI rank set to: {user_profile_stats.bmi_rank}")

            # BMR
            user_profile_stats.bmr = (
                (10.0 * user_profile_stats.weight)
                + (6.25 * float(user_profile.height) * 100.0)
                - (5.0 * float(user_profile.age))
                + 5.0
            )
        else:
            user_profile_stats.bmi = 0.0
            user_profile_stats.bmi_rank = "unknown"

        am_module.resolve(
            athlete_metrics=user_profile.athlete_metrics,
            user_profile=user_profile,
            activities=activities,
            weight_kg=user_profile_stats.weight,
            rest_hr=user_profile_stats.resting_hr,
        )

        return user_profile_stats


@dataclasses.dataclass
class UserInventoryStats:
    """Statistics about the user's dataset (counts and storage size).

    Attributes
    ----------
    activities_count : int
        Total number of activities in the dataset.
    gear_count : int
        Total number of gear items.
    goals_count : int
        Total number of goals.
    exercises_count : int
        Total number of exercise definitions.
    laps_count : int
        Total number of lap definitions.
    symptoms_count : int
        Total number of symptom definitions.
    outfits_count : int
        Total number of outfit definitions.
    activity_types_count : int
        Total number of custom activity types.
    dataset_size_mb : float
        Total size, in megabytes, of files stored directly in the user data
        directory root (non-recursive; files in subdirectories are not included).

    """

    activities_count: int = 0
    gear_count: int = 0
    goals_count: int = 0
    exercises_count: int = 0
    laps_count: int = 0
    symptoms_count: int = 0
    outfits_count: int = 0
    activity_types_count: int = 0
    dataset_size_mb: float = 0.0


@dataclasses.dataclass
class ActivityTypeStats:
    # how many times user did that activity type
    count: int = 0
    total_distance: int = 0
    total_duration: int = 0


class UserActivityTypesStats:
    def __init__(self):
        self._stats: dict[str, ActivityTypeStats] = {}

    def stats(self, activity_type_key: str) -> ActivityTypeStats | None:
        return self._stats.get(activity_type_key, None)

    def add_stats(self, activity_type_key: str, stats: ActivityTypeStats):
        self._stats[activity_type_key] = stats


@dataclasses.dataclass
class GearStats:
    stat_use: int = 0
    stat_from: str = ""
    stat_to: str = ""
    stat_meters: int = 0
    stat_km_str: str = ""
    stat_seconds: int = 0
    stat_duration_str: str = ""


class UserGearStats:
    def __init__(self):
        self._stats: dict[str, GearStats] = {}

    def stats(self, gear_key: str) -> GearStats | None:
        return self._stats.get(gear_key, None)

    def add_stats(self, gear_key: str, stats: GearStats):
        self._stats[gear_key] = stats


class ActivityStats:
    @staticmethod
    def from_entity(entity: entities.ActivityEntity):
        raise NotImplementedError


class ActivitiesStats:
    def __init__(self, activities: list[entities.ActivityEntity]) -> None:
        self.activities = activities

    def get_month_totals(
        self,
        aspect: commons.StatsAspect,
        activity_types: settings.UserActivityTypes,
        cumulative: bool = True,
    ) -> dict:
        totals = {i: 0.0 for i in range(1, 32)}

        if commons.StatsAspect.DISTANCE == aspect:
            for a in self.activities:
                if activity_types.is_sport(a.activity_type_key):
                    totals[a.when_day] += a.distance
        elif commons.StatsAspect.DURATION == aspect:
            for a in self.activities:
                if activity_types.is_sport(a.activity_type_key):
                    totals[a.when_day] += a.duration_seconds
        elif commons.StatsAspect.KGS == aspect:
            for a in self.activities:
                if activity_types.is_sport(a.activity_type_key):
                    totals[a.when_day] += a.exercise_kgs
        elif commons.StatsAspect.ELEVATION == aspect:
            for a in self.activities:
                if activity_types.is_sport(a.activity_type_key):
                    totals[a.when_day] += a.elevation_gain
        else:
            # aspect: activities count
            for a in self.activities:
                if activity_types.is_sport(a.activity_type_key):
                    totals[a.when_day] += 1

        if cumulative:
            c_sum: float = 0.0
            for k in range(1, 32):
                c_sum += totals[k]
                totals[k] = c_sum

        return totals

    def get_year_totals(
        self,
        aspect: commons.StatsAspect,
        activity_types: settings.UserActivityTypes,
        cumulative: bool = True,
    ) -> dict:
        # map: month [1, 12] -> total meters/seconds/kgs/activities
        totals = {i: 0.0 for i in range(1, 13)}
        if commons.StatsAspect.DISTANCE == aspect:
            for a in self.activities:
                if activity_types.is_sport(a.activity_type_key):
                    totals[a.when_month] += a.distance
        elif commons.StatsAspect.DURATION == aspect:
            for a in self.activities:
                if activity_types.is_sport(a.activity_type_key):
                    totals[a.when_month] += a.duration_seconds
        elif commons.StatsAspect.KGS == aspect:
            for a in self.activities:
                if activity_types.is_sport(a.activity_type_key):
                    totals[a.when_month] += a.exercise_kgs
        elif commons.StatsAspect.ELEVATION == aspect:
            for a in self.activities:
                if activity_types.is_sport(a.activity_type_key):
                    totals[a.when_month] += a.elevation_gain
        else:
            # aspect: activities count
            for a in self.activities:
                if activity_types.is_sport(a.activity_type_key):
                    totals[a.when_month] += 1

        if cumulative:
            c_sum = 0.0
            for k in range(1, 13):
                c_sum += totals[k]
                totals[k] = c_sum

        return totals


@dataclasses.dataclass
class ExerciseStats:
    count: int = 0
    total_volume: float = 0.0
    total_repetitions: int = 0
    max_weight: float = 0.0


class UserExercisesStats:
    def __init__(self):
        self._stats: dict[str, ExerciseStats] = {}

    def stats(self, exercise_key: str) -> ExerciseStats | None:
        return self._stats.get(exercise_key, None)

    def add_stats(self, exercise_key: str, stats: ExerciseStats):
        self._stats[exercise_key] = stats


@dataclasses.dataclass
class SymptomStats:
    count: int = 0
    total_health: int = 0
    avg_health: float = 0.0


class UserSymptomsStats:
    def __init__(self):
        self._stats: dict[str, SymptomStats] = {}

    def stats(self, symptom_key: str) -> SymptomStats | None:
        return self._stats.get(symptom_key, None)

    def add_stats(self, symptom_key: str, stats: SymptomStats):
        self._stats[symptom_key] = stats


@dataclasses.dataclass
class LapStats:
    count: int = 0
    total_distance: int = 0
    total_duration: int = 0


class UserLapsStats:
    def __init__(self):
        self._stats: dict[str, LapStats] = {}

    def stats(self, lap_name: str) -> LapStats | None:
        return self._stats.get(lap_name, None)

    def add_stats(self, lap_name: str, stats: LapStats):
        self._stats[lap_name] = stats


@dataclasses.dataclass
class OutfitStats:
    count: int = 0
    total_distance: int = 0
    total_duration: int = 0


class UserOutfitsStats:
    def __init__(self):
        self._stats: dict[str, OutfitStats] = {}

    def stats(self, outfit_key: str) -> OutfitStats | None:
        return self._stats.get(outfit_key, None)

    def add_stats(self, outfit_key: str, stats: OutfitStats):
        self._stats[outfit_key] = stats


class PerYearUserDatasetStats:
    def __init__(self, year: int) -> None:
        self.year = year
        self.activity_types: list = []

        # meters per-activity_type_key: activity_type_key -> meters
        self.total_m_per_activity_type: dict[str, int] = {}
        # km per-activity_type_key: activity_type_key -> km
        self.total_km_per_activity_type: dict[str, int] = {}
        # seconds per-activity_type_key: activity_type_key -> seconds
        self.total_seconds_per_activity_type: dict[str, int] = {}
        # time (h:m:s) per-activity_type_key: activity_type_key -> str
        self.total_time_per_activity_type: dict[str, str] = {}
        # activities count
        self.activities_count = 0
        # total universal km
        self.ukm = 0.0
        # total universal seconds
        self.us = 0
        # total universal time
        self.utime = ""

    def to_dict(self) -> dict:
        return {
            "year": self.year,
            "activity_types": self.activity_types,
            "total_m_per_activity_type": self.total_m_per_activity_type,
            "total_km_per_activity_type": self.total_km_per_activity_type,
            "total_seconds_per_activity_type": self.total_seconds_per_activity_type,
            "total_time_per_activity_type": self.total_time_per_activity_type,
            "activities_count": self.activities_count,
            "ukm": self.ukm,
            "us": self.us,
            "utime": self.utime,
        }

    def update(
        self,
        activity_types: settings.UserActivityTypes,
        activities: list[entities.ActivityEntity] | None = None,
        include_meta: bool = False,  # whether to include meta activities 2 count
    ):
        activities = activities or []
        self.activities_count = 0

        self.activity_types = []
        self.total_m_per_activity_type = {}
        self.total_km_per_activity_type = {}
        self.total_seconds_per_activity_type = {}
        self.total_time_per_activity_type = {}

        for activity in activities:
            if self.year == activity.when_year:
                if not include_meta and activity_types.is_meta(
                    activity.activity_type_key
                ):
                    continue

                self.activity_types.append(activity.activity_type_key)
                self.activities_count += 1

                if activity_types.is_distance(activity.activity_type_key):
                    mytral_sport = icommons.STRAVA_TO_MYTRAL_AT.get(
                        activity.activity_type_key, activity.activity_type_key
                    )

                    meters = activity.distance
                    if mytral_sport in self.total_m_per_activity_type:
                        self.total_m_per_activity_type[mytral_sport] += meters
                        self.total_seconds_per_activity_type[mytral_sport] += (
                            activity.duration_seconds
                        )
                    else:
                        self.total_m_per_activity_type[mytral_sport] = meters
                        self.total_seconds_per_activity_type[mytral_sport] = (
                            activity.duration_seconds
                        )
                    self.total_time_per_activity_type[mytral_sport] = (
                        cals.seconds_to_str_time(
                            self.total_seconds_per_activity_type[mytral_sport]
                        )
                    )

                    ukm_coefficient = commons.UKM_COEFFICIENTS.get(mytral_sport, 1.0)
                    self.ukm += float(meters) / 1000.0 * ukm_coefficient
                    self.us += activity.duration_seconds
                    self.utime = cals.seconds_to_str_time(self.us)

        self.activity_types = list(set(self.activity_types))
        self.activity_types.sort(reverse=True)

        for s in self.total_m_per_activity_type:
            self.total_km_per_activity_type[s] = int(
                self.total_m_per_activity_type[s] / 1000.0
            )


class UserDatasetStats:
    @property
    def year_min(self) -> int:
        return min(self.years) if self.years else 0

    @property
    def year_max(self) -> int:
        return max(self.years) if self.years else 0

    def __init__(self) -> None:
        self.years: list = []
        # per-year ml
        self.year: dict[int, PerYearUserDatasetStats] = {}
        self.activity_types: list = []

        # total m per-activity_type_key: activity_type_key -> meters
        self.total_m_per_activity_type: dict[str, int] = {}
        # total km per-activity_type_key: activity_type_key -> km
        self.total_km_per_activity_type: dict[str, int] = {}
        # total seconds per-activity_type_key: activity_type_key -> seconds
        self.total_seconds_per_activity_type: dict[str, int] = {}
        # total time per-activity_type_key: activity_type_key -> str
        self.total_time_per_activity_type: dict[str, str] = {}

        # gear count: gear -> count
        self.gear_count: dict[str, int] = {}
        # total m per gear: gear -> meters
        self.total_m_per_gear: dict[str, int] = {}
        # total seconds per gear: gear -> seconds
        self.total_seconds_per_gear: dict[str, int] = {}
        # gear used from: gear -> (year, month, day)
        self.gear_used_from: dict[str, tuple[int, int, int]] = {}
        # gear used to: gear -> (year, month, day)
        self.gear_used_to: dict[str, tuple[int, int, int]] = {}

        this_year = datetime.datetime.now().year
        # this year ml
        self.this_year: PerYearUserDatasetStats = self.year.get(
            this_year, PerYearUserDatasetStats(this_year)
        )
        # number of activities
        self.activities_count = 0

        self.ukm = 0.0
        self.us = 0
        self.utime = ""

        # max/min
        self.ts_max = 0  # max activity timestamp
        self.ts_min = 0  # min activity timestamp

    def __str__(self):
        return json.dumps(self.to_dict(), indent=2)

    def to_dict(self) -> dict:
        return {
            "years": self.years,
            "activity_types": self.activity_types,
            "total_m_per_activity_type": self.total_m_per_activity_type,
            "total_km_per_activity_type": self.total_km_per_activity_type,
            "total_seconds_per_activity_type": self.total_seconds_per_activity_type,
            "total_time_per_activity_type": self.total_time_per_activity_type,
            "gear_count": self.gear_count,
            "gear_used_from": self.gear_used_from,
            "gear_used_to": self.gear_used_to,
            "total_m_per_gear": self.total_m_per_gear,
            "total_seconds_per_gear": self.total_seconds_per_gear,
            "year": [self.year[y].to_dict() for y in self.year],
            "activities_count": self.activities_count,
            "ukm": self.ukm,
            "us": self.us,
            "utime": self.utime,
        }

    def update(
        self,
        activity_types: settings.UserActivityTypes,
        logger: loggers.MytralLogger,
        activities: list[entities.ActivityEntity] | None = None,
        include_meta: bool = False,  # whether to include meta activities 2 count
    ) -> Self:
        logger.info(f"[Stats] updating stats for {len(activities or [])} activities...")

        activities = activities or []

        self.years = []
        self.year = {}
        self.activity_types = []
        self.total_m_per_activity_type = {}
        self.total_km_per_activity_type = {}
        self.total_seconds_per_activity_type = {}
        self.total_time_per_activity_type = {}
        self.gear_count = {}
        self.gear_used_from = {}
        self.gear_used_to = {}
        self.total_m_per_gear = {}
        self.total_seconds_per_gear = {}
        self.ts_max = 0
        self.ts_min = 0

        self.activities_count = 0

        if activities:
            all_years = []
            all_sports = []
            for activity in activities:
                if not include_meta and activity_types.is_meta(
                    activity.activity_type_key
                ):
                    continue

                self.activities_count += 1

                # integrity check
                if (
                    activity.when_year is None
                    or activity.when_month is None
                    or activity.when_day is None
                    or activity.when_hour is None
                    or activity.when_minute is None
                    or activity.when_second is None
                ):
                    err_msg = (
                        f"[Stats] invalid activity - has a None when_* entry: "
                        f"{activity.to_dict()}"
                    )
                    logger.error(err_msg)
                    raise ValueError(err_msg)
                try:
                    when = int(
                        datetime.datetime(
                            year=activity.when_year,
                            month=activity.when_month,
                            day=activity.when_day,
                            hour=activity.when_hour,
                            minute=activity.when_minute,
                            second=activity.when_second,
                        ).timestamp()
                    )
                except ValueError as e:
                    logger.error(
                        f"[Stats] invalid activity date for {activity.to_dict()} "
                        f"=-> {activity.to_sparse_dict()})"
                    )
                    raise e
                if not self.ts_min or when < self.ts_min:
                    self.ts_min = when
                if not self.ts_max or when > self.ts_max:
                    self.ts_max = when

                all_years.append(activity.when_year)
                all_sports.append(activity.activity_type_key)

                if activity_types.is_distance(activity.activity_type_key):
                    mytral_sport = icommons.STRAVA_TO_MYTRAL_AT.get(
                        activity.activity_type_key, activity.activity_type_key
                    )

                    meters = activity.distance
                    seconds = activity.duration_seconds

                    # distance & time per activity_type_key
                    if mytral_sport in self.total_m_per_activity_type:
                        self.total_m_per_activity_type[mytral_sport] += meters
                        self.total_seconds_per_activity_type[mytral_sport] += seconds
                    else:
                        self.total_m_per_activity_type[mytral_sport] = meters
                        self.total_seconds_per_activity_type[mytral_sport] = seconds
                    self.total_time_per_activity_type[mytral_sport] = (
                        cals.seconds_to_str_time(
                            self.total_seconds_per_activity_type[mytral_sport]
                        )
                    )

                    # distance & time per gear
                    activity_gears = (
                        activity.gears
                        if hasattr(activity, "gears")
                        else ([activity.gear] if activity.gear else [])
                    )
                    for gear_key in activity_gears:
                        if gear_key:
                            ts = (
                                activity.when_year,
                                activity.when_month,
                                activity.when_day,
                            )
                            if gear_key in self.gear_used_from:
                                if ts < self.gear_used_from[gear_key]:
                                    self.gear_used_from[gear_key] = ts
                            else:
                                self.gear_used_from[gear_key] = ts
                            if gear_key in self.gear_used_to:
                                if ts > self.gear_used_to[gear_key]:
                                    self.gear_used_to[gear_key] = ts
                            else:
                                self.gear_used_to[gear_key] = ts

                            if gear_key in self.gear_count:
                                self.gear_count[gear_key] += 1
                            else:
                                self.gear_count[gear_key] = 1

                            if gear_key in self.total_m_per_gear:
                                self.total_m_per_gear[gear_key] += meters
                            else:
                                self.total_m_per_gear[gear_key] = meters
                            if gear_key in self.total_seconds_per_gear:
                                self.total_seconds_per_gear[gear_key] += seconds
                            else:
                                self.total_seconds_per_gear[gear_key] = seconds

                # else:
                #     logger.error(
                #       f"UKM skipping unknown activity type:
                #       {activity.activity_type_key}"
                #     )

            self.ts_max = self.ts_max or 0
            self.ts_min = self.ts_min or 0

            self.years = list(set(all_years))
            self.years.sort(reverse=True)

            self.activity_types = list(set(all_sports))
            self.activity_types.sort(reverse=True)

            for s in self.total_m_per_activity_type:
                self.total_km_per_activity_type[s] = int(
                    self.total_m_per_activity_type[s] / 1000.0
                )

            self.ukm = 0.0
            self.us = 0
            self.year = {}
            for y in self.years:
                self.year[y] = PerYearUserDatasetStats(y)
                self.year[y].update(
                    activities=activities, activity_types=activity_types
                )
                self.ukm += self.year[y].ukm
                self.us += self.year[y].us
                self.utime = cals.seconds_to_str_time(self.us)

        logger.info(f"[Stats] DONE update for {len(activities or [])} activities")

        return self
