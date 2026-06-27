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
import json

from mytral import cals
from mytral import commons
from mytral import settings
from mytral.backends import entities

#
# data for MyTraL views: heatmaps, tables, charts
#


class CalendarHeatmap:
    """Calendar centric data structure for activities which builds the following
    dictionary for a given date range:

    - map: year -> week number -> cell with stats for each day

    """

    class Cell:
        """Calendar heatmap cell w/ YYYY, MM, DD and activities for that day."""

        @property
        def count(self) -> int:
            return len(self.activities)

        @property
        def count_activities(self) -> int:
            return (
                0
                if not self.activities
                else len(
                    [
                        a
                        for a in self.activities
                        if not self.activity_types.is_meta(a.activity_type_key)
                    ]
                )
            )

        @property
        def slash_date(self) -> str:
            return f"{self.year}/{self.month}/{self.day}"

        @property
        def is_active_sick(self):
            return self.is_active and self.is_sick

        @property
        def has_comment(self) -> bool:
            """Check if there are any comment activities for this day."""
            return any(
                a.activity_type_key == commons.AT_COMMENT for a in self.activities
            )

        @property
        def title(self) -> str:
            suffix = (
                (
                    f": {self.count_activities} "
                    f"{'activities' if self.count_activities != 1 else 'activity'}"
                    f"{' (sick)' if self.is_sick and not self.is_active else ''}"
                    f"{' (active but injured/sick)' if self.is_active_sick else ''}"
                    f"{' + comment' if self.has_comment else ''}"
                )
                if self.count_activities
                else (": comment" if self.has_comment else "")
            )
            return f"{self.slash_date}{suffix if self.count > 0 else ''}"

        def __init__(
            self,
            year: int,
            month: int,
            day: int,
            activity_types: settings.UserActivityTypes,
            activities: list[entities.ActivityEntity] | None = None,
        ) -> None:
            self.year = year
            self.month = month
            self.day = day

            self.activity_types = activity_types

            self.activities = activities or []

            self.is_sick = False
            self.is_active = False

        def add_activity(self, activity: entities.ActivityEntity):
            self.activities.append(entities.evaluate_activity(entity=activity))
            self.activities = sorted(
                self.activities,
                key=lambda a: a.when_hour * 100.0 + a.when_minute,
                reverse=False,
            )

            if activity.activity_type_key in [commons.AT_SICK, commons.AT_INJURED]:
                self.is_sick = True
            elif not self.is_active:
                self.is_active = (
                    False
                    if self.activity_types.is_meta(activity.activity_type_key)
                    else True
                )

        def to_dict(self):
            return {
                "year": self.year,
                "month": self.month,
                "day": self.day,
                "activities": [a.to_dict() for a in self.activities],
                "is_sick": self.is_sick,
                "count": self.count,
                "count_activities": self.count_activities,
            }

    KEY_WEIGHT = "weight"  # ... min weight that week in kg
    KEY_M = "meters"  # m ... distance in meters
    KEY_SECONDS = "seconds"  # ... time in seconds
    KEY_KG = "kgs"  # m ... distance in meters
    KEY_ELEVATION = "elevation"  # m ... elevation gain in meters
    KEY_TIME = "time"  # ... time as formatted string
    KEY_WEEK_DATE = "week_date"  # ... date of the first day in the week

    def __init__(
        self,
        user_profile: settings.UserProfile,
        from_year: int,
        to_year: int,
        activity_types: settings.UserActivityTypes,
        logger,
    ) -> None:
        self.user_profile = user_profile
        self.from_year = from_year
        self.to_year = to_year
        self.start_date = datetime.date(year=from_year, month=1, day=1)
        self.end_date = datetime.date(year=to_year, month=12, day=31)
        self.activity_types = activity_types
        self.logger = logger

        # activities withing the given ^ range
        self.activities = []

        # map:
        #   year
        #     -> week number
        #       -> week_day (0=Monday, 6=Sunday)
        #         -> None
        #              or
        #            CalendarHeatmap.Cell(date, activities)
        self.heatmap = {}
        # map:
        #   year
        #     -> week number
        #       -> "km" -> distance
        #       -> "time" -> time
        #       -> ...
        self.week_stats = {}

    def get_timeseries(self, quantity: str, year: int):
        """Get timeseries for the given quantity."""
        if not self.week_stats or year not in self.week_stats:
            raise ValueError(f"Year {year} not in week stats.")

        timeseries = []
        for week_number in self.week_stats[year]:
            timeseries.append(
                {
                    "week_number": week_number,
                    "value": self.week_stats[year][week_number].get(quantity, 0),
                }
            )
        return timeseries

    def build_activity_type_heatmap(
        self,
        activities: list[entities.ActivityEntity],
    ):
        """(Re)build activity_type_key calendar heatmap."""

        self.logger.info("Building activity_type_key heatmap...")
        start_time = datetime.datetime.now()

        # sparse heatmap of actual activities
        sparse_heatmap = {}
        cells = []
        for a in activities:
            if self.from_year <= a.when_year <= self.to_year:
                self.activities.append(a)

            current_date = datetime.date(
                year=a.when_year,
                month=a.when_month,
                day=a.when_day,
            )

            year = current_date.year
            week_number = current_date.isocalendar()[1]
            week_day = current_date.weekday()

            # week numbers start from 52/53 in previous year, change it to 0
            if week_number >= 52 and current_date.month == 1:
                week_number = 0
            if week_number == 1 and current_date.month == 12:
                week_number = 53

            if year not in sparse_heatmap:
                sparse_heatmap[year] = {}
            if year not in self.week_stats:
                self.week_stats[year] = {}

            if week_number not in sparse_heatmap[year]:
                sparse_heatmap[year][week_number] = {}

            kgs = entities.evaluate_exercise_kgs(a)
            duration_seconds = a.hours * 3600 + a.minutes * 60 + a.seconds
            if week_number not in self.week_stats[year]:
                self.week_stats[year][week_number] = {
                    CalendarHeatmap.KEY_WEIGHT: a.weight,
                    CalendarHeatmap.KEY_M: a.distance,
                    CalendarHeatmap.KEY_KG: kgs,
                    CalendarHeatmap.KEY_ELEVATION: a.elevation_gain,
                    CalendarHeatmap.KEY_SECONDS: duration_seconds,
                    CalendarHeatmap.KEY_TIME: "{:0>8}".format(
                        str(datetime.timedelta(seconds=duration_seconds))
                    ),
                    CalendarHeatmap.KEY_WEEK_DATE: "",
                }
            else:
                # min weight of the week
                weight = self.week_stats[year][week_number][CalendarHeatmap.KEY_WEIGHT]
                if weight:
                    if a.weight:
                        self.week_stats[year][week_number][
                            CalendarHeatmap.KEY_WEIGHT
                        ] = min(a.weight, weight)
                elif a.weight:
                    self.week_stats[year][week_number][CalendarHeatmap.KEY_WEIGHT] = (
                        a.weight
                    )

                self.week_stats[year][week_number][CalendarHeatmap.KEY_SECONDS] += (
                    duration_seconds
                )
                self.week_stats[year][week_number][CalendarHeatmap.KEY_KG] += kgs
                self.week_stats[year][week_number][CalendarHeatmap.KEY_M] += a.distance
                self.week_stats[year][week_number][CalendarHeatmap.KEY_ELEVATION] += (
                    a.elevation_gain
                )
                self.week_stats[year][week_number][CalendarHeatmap.KEY_TIME] = (
                    "{:0>8}"
                ).format(
                    str(
                        datetime.timedelta(
                            seconds=self.week_stats[year][week_number][
                                CalendarHeatmap.KEY_SECONDS
                            ]
                        )
                    )
                )

            if week_day not in sparse_heatmap[year][week_number]:
                sparse_heatmap[year][week_number][week_day] = None

            if sparse_heatmap[year][week_number][week_day] is None:
                sparse_heatmap[year][week_number][week_day] = CalendarHeatmap.Cell(
                    year=a.when_year,
                    month=a.when_month,
                    day=a.when_day,
                    activity_types=self.activity_types,
                    activities=[],
                )
                cells.append(sparse_heatmap[year][week_number][week_day])

            sparse_heatmap[year][week_number][week_day].add_activity(a)

        # complete heatmap for given date range
        current_date = self.start_date
        while current_date <= self.end_date:
            year = current_date.year
            week_number = current_date.isocalendar()[1]
            week_day = current_date.weekday()

            # week numbers start from 52/53 in previous year, change it to 0
            if week_number >= 52 and current_date.month == 1:
                week_number = 0
            if week_number == 1 and current_date.month == 12:
                week_number = 53

            if year not in self.heatmap:
                self.heatmap[year] = {}
            if year not in self.week_stats:
                self.week_stats[year] = {}

            if week_number not in self.heatmap[year]:
                self.heatmap[year][week_number] = {}
            if week_number not in self.week_stats[year]:
                self.week_stats[year][week_number] = {
                    # weight, time, ...
                    CalendarHeatmap.KEY_M: 0,
                    CalendarHeatmap.KEY_KG: 0,
                    CalendarHeatmap.KEY_ELEVATION: 0,
                    CalendarHeatmap.KEY_SECONDS: 0,
                    CalendarHeatmap.KEY_WEEK_DATE: "",
                }
            if not self.week_stats[year][week_number].get(
                CalendarHeatmap.KEY_WEEK_DATE
            ):
                try:
                    d = datetime.date.fromisocalendar(year, week_number, 1)
                except ValueError:
                    d = None
                self.week_stats[year][week_number][CalendarHeatmap.KEY_WEEK_DATE] = (
                    f"{d.month}/{d.day}" if d else ""
                )

            if week_day not in self.heatmap[year][week_number]:
                self.heatmap[year][week_number][week_day] = (
                    sparse_heatmap.get(year, {})
                    .get(week_number, {})
                    .get(
                        week_day,
                        CalendarHeatmap.Cell(
                            year=current_date.year,
                            month=current_date.month,
                            day=current_date.day,
                            activity_types=self.activity_types,
                        ),
                    )
                )

            current_date += datetime.timedelta(days=1)

        # sort cells
        for c in cells:
            a_sorted = []
            a_sick = []
            for a in c.activities:
                if a.activity_type_key in [commons.AT_SICK, commons.AT_INJURED]:
                    a_sick.append(a)
                else:
                    a_sorted.append(a)
            a_sorted.extend(a_sick)
            c.activities = a_sorted

        # reverse heatmap keys
        reversed_heatmap = {}
        for y in reversed(sorted(self.heatmap.keys())):
            reversed_heatmap[y] = self.heatmap[y]
        self.heatmap = reversed_heatmap

        self.logger.info(
            f"Sport heatmap built in {datetime.datetime.now() - start_time}s"
        )

    def build_sickness_heatmap(
        self,
        activities: list[entities.ActivityEntity],
        sick_or_injured: list | None = None,
    ):
        """(Re)build sickness calendar heatmap:

        - build for the current year
        - uses data from all year and maps it to the current year (dates)
          and counts the number of years in which the user was sick
          that day

        """
        sick_or_injured = sick_or_injured or [commons.AT_SICK, commons.AT_INJURED]

        # fix year to leap year ~ has February 29th (like 2024)
        leap_year = 2024

        # sparse heatmap of actual activities
        # map: CURRENT year -> week number -> week day -> CalendarHeatmap.Cell
        sparse_heatmap: dict = {}
        for a in activities:
            if a.activity_type_key in sick_or_injured:
                self.activities.append(a)

            current_date = datetime.date(
                year=leap_year,  # fix to current year
                month=a.when_month,
                day=a.when_day,
            )

            year = leap_year
            week_number = current_date.isocalendar()[1]
            week_day = current_date.weekday()

            # week numbers start from 52/53 in previous year, change it to 0
            if week_number >= 52 and current_date.month == 1:
                week_number = 0
            if week_number == 1 and current_date.month == 12:
                week_number = 53

            if year not in sparse_heatmap:
                sparse_heatmap[year] = {}

            if week_number not in sparse_heatmap[year]:
                sparse_heatmap[year][week_number] = {}

            if week_day not in sparse_heatmap[year][week_number]:
                sparse_heatmap[year][week_number][week_day] = None

            if sparse_heatmap[year][week_number][week_day] is None:
                sparse_heatmap[year][week_number][week_day] = CalendarHeatmap.Cell(
                    year=leap_year,
                    month=a.when_month,
                    day=a.when_day,
                    activity_types=self.activity_types,
                    activities=[],
                )

            sparse_heatmap[year][week_number][week_day].add_activity(a)

        # complete heatmap for given date range
        current_date = self.start_date
        while current_date <= self.end_date:
            year = leap_year
            week_number = current_date.isocalendar()[1]
            week_day = current_date.weekday()

            # week numbers start from 52/53 in previous year, change it to 0
            if week_number >= 52 and current_date.month == 1:
                week_number = 0
            if week_number == 1 and current_date.month == 12:
                week_number = 53

            if year not in self.heatmap:
                self.heatmap[year] = {}

            if week_number not in self.heatmap[year]:
                self.heatmap[year][week_number] = {}

            if week_day not in self.heatmap[year][week_number]:
                # gather data for this week number and week day from sparse heatmap
                sickness_activities = []
                for y in sparse_heatmap.keys():
                    sparse_cell = (
                        sparse_heatmap.get(y, {})
                        .get(week_number, {})
                        .get(week_day, None)
                    )
                    if sparse_cell:
                        for a in sparse_cell.activities:
                            if a.activity_type_key in sick_or_injured:
                                sickness_activities.append(a)

                # create heatmap cell
                self.heatmap[year][week_number][week_day] = CalendarHeatmap.Cell(
                    year=current_date.year,
                    month=current_date.month,
                    day=current_date.day,
                    activity_types=self.activity_types,
                    activities=sickness_activities,
                )

            current_date += datetime.timedelta(days=1)

        # reverse heatmap keys
        reversed_heatmap = {}
        for y in reversed(sorted(self.heatmap.keys())):
            reversed_heatmap[y] = self.heatmap[y]
        self.heatmap = reversed_heatmap

    @staticmethod
    def get_ukm_for_activity(activity: entities.ActivityEntity) -> int:
        """Get universal meters for the given activity."""
        return activity.distance

    def _week_activities(self, year: int, week_number: int) -> list:
        """Get activities for the given week."""
        week_stats = self.heatmap.get(year, {}).get(week_number, {})
        if week_stats:
            return [c.activities for c in week_stats.values()]
        return []

    def _week_stat_aspect(
        self, year: int, week_number: int, aspect: commons.StatsAspect
    ) -> list:
        """Get stats for the given week.

        Returns
        -------
        List
          A list with 7 numbers for given aspect (distance, duration, ...).

        """
        week_as = self._week_activities(year=year, week_number=week_number)

        def _count_as(activities: list) -> int:
            count = 0
            if activities:
                for a in activities:
                    if not self.activity_types.is_meta(a.activity_type_key):
                        count += 1
            return count

        if aspect == commons.StatsAspect.ACTIVITIES:
            return [_count_as(a) for a in week_as]
        elif aspect == commons.StatsAspect.DISTANCE:
            result = [
                sum([self.get_ukm_for_activity(a) for a in activities])
                for activities in week_as
            ]
            # 0 padding
            if len(result) == 7:
                return result
            elif week_number == 1:
                return [0] * (7 - len(result)) + result
            return result + [0] * (7 - len(result))
        elif aspect == commons.StatsAspect.DURATION:
            return [
                sum([a.duration_seconds for a in activities]) for activities in week_as
            ]
        elif aspect == commons.StatsAspect.KGS:
            return [sum([a.exercise_kgs for a in activities]) for activities in week_as]
        elif aspect == commons.StatsAspect.ELEVATION:
            return [
                sum([a.elevation_gain for a in activities]) for activities in week_as
            ]

        raise ValueError(f"Unsupported aspect: {aspect}")

    def vs_week_stats(
        self,
        aspect: commons.StatsAspect = commons.StatsAspect.ACTIVITIES,
        units: str = "km",
    ) -> tuple[list, list]:
        """Get last vs. this week data. There are various cases to handle:

        - within the year:
          - last and this week are in the SAME year
        - end of year:
          - last week is in the OLD year,
            this week is in the NEW year (rare)
          - last week is in the OLD year,
            this week: a part is in the OLD year, another part in the NEW year
          - last week: a part is in the OLD year, another part in the NEW year
          - this week is in the NEW year

        Problems:

        - heatmap is build for a particular year, not for the date range
          (last year heatmap is needed)

        Parameters
        ----------
        aspect : StatsAspect
            Aspect of the data to get: distance, duration, ...
        units : str
            Units for the data: km, m, ...

        """
        today = datetime.datetime.now()

        # detect whether the last and this week are in the same year
        # this week
        this_sun_y, this_sun_m, this_sun_d = cals.get_sunday(
            year=today.year, month=today.month, day=today.day
        )
        this_mon_y, this_mon_m, this_mon_d = cals.get_monday(
            year=today.year, month=today.month, day=today.day
        )
        # last week
        last_sun_y, last_sun_m, last_sun_d = cals.get_yesterday(
            year=this_mon_y, month=this_mon_m, day=this_mon_d
        )
        last_mon_y, last_mon_m, last_mon_d = cals.get_monday(
            year=last_sun_y, month=last_sun_m, day=last_sun_d
        )
        # is the last week in the same year?
        same_year = last_mon_y == this_sun_y

        if same_year:
            this_week_number = today.isocalendar()[1]
            last_week_number = this_week_number - 1

            this_week_stats = self._week_stat_aspect(
                year=last_mon_y, week_number=this_week_number, aspect=aspect
            )
            last_week_stats = self._week_stat_aspect(
                year=last_mon_y,
                week_number=last_week_number,
                aspect=aspect,
            )
        elif last_mon_y == last_sun_y:
            # last week: whole in the OLD year, ...
            week_number = datetime.date(
                last_mon_y, last_mon_m, last_mon_d
            ).isocalendar()[1]
            last_week_stats = self._week_stat_aspect(
                year=last_mon_y,
                week_number=week_number,
                aspect=aspect,
            )
            # TODO this week: a part is in the OLD year, another part in the NEW year
            #   - last year heatmap is needed
            this_week_stats_old = self._week_stat_aspect(  # last year heatmap is needed
                year=this_mon_y,
                week_number=week_number + 1,
                aspect=aspect,
            )
            this_week_stats_new = self._week_stat_aspect(  # this is OK
                year=this_sun_y,
                week_number=1,
                aspect=aspect,
            )
            this_week_stats = [
                x + y for x, y in zip(this_week_stats_old, this_week_stats_new)
            ]
        else:
            # TODO last week: a part is in the old year, another part in the new year
            #   - last year heatmap is needed
            week_number = datetime.date(
                last_mon_y, last_mon_m, last_mon_d
            ).isocalendar()[1]
            last_week_stats_old = self._week_stat_aspect(  # last year heatmap is needed
                year=last_mon_y,
                week_number=week_number + 1,
                aspect=aspect,
            )
            last_week_stats_new = self._week_stat_aspect(  # this is OK
                year=last_sun_y,
                week_number=1,
                aspect=aspect,
            )
            last_week_stats = [
                x + y for x, y in zip(last_week_stats_old, last_week_stats_new)
            ]
            # this week: whole NEW year
            week_number = datetime.date(
                this_mon_y, this_mon_m, this_mon_d
            ).isocalendar()[1]
            this_week_stats = self._week_stat_aspect(
                year=this_sun_y, week_number=week_number, aspect=aspect
            )

        #
        # normalization
        #

        if aspect == commons.StatsAspect.DISTANCE and units == "km":
            this_week_stats = [a / 1000 for a in this_week_stats]
            last_week_stats = [a / 1000 for a in last_week_stats]

        return last_week_stats, this_week_stats

    def to_dict(self):
        return {
            "from_year": self.from_year,
            "to_year": self.to_year,
            "heatmap": {
                year: {
                    week_number: {
                        week_day: cell.to_dict() if cell else None
                        for week_day, cell in week.items()
                    }
                    for week_number, week in year_weeks.items()
                }
                for year, year_weeks in self.heatmap.items()
            },
        }

    def to_json(self):
        return json.dumps(self.to_dict(), indent=2)


_SKIP_ACTIVITY_TYPES = frozenset({"sick", "injured", "comment"})


def build_feed_bar_chart_data(activities: list) -> list[dict]:
    """Pre-aggregate activities into per-day stats for the feed bar chart navigation.

    Returns a sorted list of dicts (one per day that has activities), ready for
    JSON serialisation.  Replaces the old client-side aggregation over the full
    ActivityEntity list.
    """
    days: dict[int, dict] = {}

    for activity in activities:
        date = datetime.date(activity.when_year, activity.when_month, activity.when_day)
        day_of_year = date.timetuple().tm_yday

        if day_of_year not in days:
            days[day_of_year] = {
                "day_of_year": day_of_year,
                "month": activity.when_month,
                "day": activity.when_day,
                "total_distance": 0,
                "total_duration": 0,
                "total_tonnage": 0.0,
                "total_weight": 0.0,
                "activity_count": 0,
                "first_key": activity.key,
                "names": [],
            }

        day = days[day_of_year]
        day["activity_count"] += 1
        if len(day["names"]) < 3:
            day["names"].append(activity.name or activity.activity_type_key)

        if activity.activity_type_key not in _SKIP_ACTIVITY_TYPES:
            day["total_distance"] += activity.distance or 0
            day["total_duration"] += (
                activity.hours * 3600 + activity.minutes * 60 + activity.seconds
            )
            day["total_tonnage"] += activity.exercise_kgs or 0
            if activity.weight:
                day["total_weight"] = activity.weight

    return sorted(days.values(), key=lambda d: d["day_of_year"])
