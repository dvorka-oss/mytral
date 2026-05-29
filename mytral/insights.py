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
from datetime import date

from mytral import app_logger
from mytral import commons
from mytral import settings
from mytral import stats
from mytral import views


class OnTheSameDay:
    """Show activities on the same day."""

    def is_available(self) -> bool:
        return bool(
            self.activity_preds
            or self.health_preds
            or self.activity_history
            or self.health_history
            or self.weight_history
            or self.weight_preds
        )

    def __init__(
        self,
        today: date,
        heatmap: views.CalendarHeatmap,
        profile_stats: stats.UserProfileStats,
        symptoms: settings.UserSymptoms,
    ) -> None:
        self.today = today
        self.heatmap = heatmap
        self.profile_stats = profile_stats
        self.symptoms = symptoms

        # [(<activity>, <percentage>), ...] - percentages sum to 100%
        self.activity_preds: list[tuple] = []
        # [("Sick"|"Injured"|"Healthy", <percentage>), ...] - percentages sum to 100%
        self.health_preds: list[tuple] = []
        # [(<year>, <month>, <day>, [<activity>]), ...]
        self.activity_history: list[tuple] = []
        # [(<year>, <month>, <day>, [<health_issue_name>]), ...]
        self.health_history: list[tuple] = []
        # [(<year>, <weight>, <diff>), ...]
        self.weight_history: list[tuple] = []
        # [(<metric>, <value>), ...]
        self.weight_preds: list[tuple] = []

        # NEW PREDICTIONS
        # Training load: [(<metric>, <value>), ...]
        self.training_load_preds: list[tuple] = []
        # Activity intensity: [(<type>, <percentage>), ...] - sum to 100%
        self.intensity_preds: list[tuple] = []
        # Performance pattern: [(<metric>, <value>), ...]
        self.performance_preds: list[tuple] = []
        # Performance category: [(<category>, <percentage>), ...] - sum to 100%
        self.performance_category: list[tuple] = []
        # Seasonal preferences: [(<type>, <percentage>), ...] - sum to 100%
        self.seasonal_preds: list[tuple] = []
        # Recovery prediction: [(<type>, <percentage>), ...] - sum to 100%
        self.recovery_preds: list[tuple] = []
        # Consistency score
        self.consistency_score: float = 0.0
        # Goal achievement: [(<metric>, <value>), ...]
        self.goal_preds: list[tuple] = []

        self._update()

    def _update(self) -> None:
        self.activity_history = []
        self.activity_preds = []
        self.health_history = []
        self.weight_preds = []

        years = list(self.heatmap.heatmap.keys())
        if not years or len(years) < 2:
            return

        week_number = self.today.isocalendar()[1]
        week_day = self.today.weekday()
        current_weight = self.profile_stats.weight
        # map: activity -> count
        activity_preds_data = {}
        # track years with sick/injured/healthy status
        years_sick = set()
        years_injured = set()
        years_with_data = set()
        # list of weights from history
        weight_history_data = []
        # NEW: data for new predictions
        daily_durations = []  # total minutes per day
        daily_distances = []  # total meters per day
        daily_activity_counts = []  # number of activities per day
        daily_paces = []  # pace in min/km for runs
        years_with_rest = set()  # years with no activity on this day
        years_with_recovery = set()  # years with recovery activity
        indoor_activity_count = 0
        outdoor_activity_count = 0

        for year in self.heatmap.heatmap:
            year_data = self.heatmap.heatmap[year]
            min_weight = 1000.0

            if (
                year_data.get(week_number)
                and year_data[week_number].get(week_day)
                and year_data[week_number][week_day].activities
            ):
                cell = year_data[week_number][week_day]
                activity_names = []
                health_names = []
                year_is_sick = False
                year_is_injured = False

                # NEW: collect detailed activity data
                day_duration_minutes = 0
                day_distance_meters = 0
                day_activity_count = 0
                day_recovery_count = 0
                day_training_count = 0

                for a in cell.activities:
                    if a.weight and a.weight < min_weight:
                        min_weight = a.weight
                    if self.heatmap.activity_types.is_sport(a.activity_type_key):
                        activity_names.append(
                            self.heatmap.activity_types.name(a.activity_type_key)
                        )

                        # NEW: collect training load data
                        day_duration_minutes += (
                            a.hours * 60 + a.minutes + a.seconds / 60.0
                        )
                        day_distance_meters += a.distance
                        day_activity_count += 1

                        # NEW: collect pace data for running
                        if (
                            a.activity_type_key in ["run", "running"]
                            and a.distance > 0
                            and day_duration_minutes > 0
                        ):
                            total_seconds = a.hours * 3600 + a.minutes * 60 + a.seconds
                            km = a.distance / 1000.0
                            if km > 0:
                                pace_min_per_km = (total_seconds / 60.0) / km
                                daily_paces.append(pace_min_per_km)

                        # NEW: categorize as recovery or training
                        if a.intensity in [
                            "regen",
                            "recovery",
                            "easy",
                        ] or a.activity_type_key in [
                            "yoga",
                            "stretching",
                            "walk",
                            "walking",
                        ]:
                            day_recovery_count += 1
                        else:
                            day_training_count += 1

                        # NEW: indoor/outdoor classification (simple heuristic)
                        if a.activity_type_key in [
                            "gym",
                            "treadmill",
                            "ergometer",
                            "indoor",
                        ]:
                            indoor_activity_count += 1
                        else:
                            outdoor_activity_count += 1

                    elif self.heatmap.activity_types.is_health_issue(
                        a.activity_type_key
                    ):
                        health_names.append(
                            self.heatmap.activity_types.name(a.activity_type_key)
                        )
                        # track sick vs injured
                        if a.activity_type_key == commons.AT_SICK:
                            year_is_sick = True
                        elif a.activity_type_key == commons.AT_INJURED:
                            year_is_injured = True

                # track this year as having data
                years_with_data.add(year)

                # track health status for this year
                if year_is_sick:
                    years_sick.add(year)
                if year_is_injured:
                    years_injured.add(year)

                # NEW: store daily metrics and categorize day type
                if day_activity_count > 0:
                    daily_durations.append(day_duration_minutes)
                    daily_distances.append(day_distance_meters)
                    daily_activity_counts.append(day_activity_count)

                    if day_recovery_count > 0 and day_training_count == 0:
                        years_with_recovery.add(year)
                elif not health_names:
                    years_with_rest.add(year)

                if activity_names:
                    a_entry = (year, cell.month, cell.day, activity_names)
                    self.activity_history.append(a_entry)
                    for a in activity_names:
                        activity_preds_data[a] = activity_preds_data.get(a, 0.0) + 1.0

                if health_names:
                    health_entry = (year, cell.month, cell.day, health_names)
                    self.health_history.append(health_entry)

                weight_for_day = None
                if min_weight < 1000.0:
                    weight_for_day = min_weight
                    app_logger.debug(
                        f"Year {year}: Found weight {min_weight} on specific day"
                    )
                elif (
                    year in self.heatmap.week_stats
                    and week_number in self.heatmap.week_stats[year]
                    and self.heatmap.week_stats[year][week_number].get(
                        views.CalendarHeatmap.KEY_WEIGHT
                    )
                ):
                    weight_for_day = self.heatmap.week_stats[year][week_number][
                        views.CalendarHeatmap.KEY_WEIGHT
                    ]
                    app_logger.debug(
                        f"Year {year}: Using week min weight {weight_for_day} "
                        f"(week {week_number})"
                    )

                if current_weight and weight_for_day:
                    self.weight_history.append(
                        (
                            year,
                            weight_for_day,
                            round(current_weight - weight_for_day, 1),
                        )
                    )
                    weight_history_data.append(weight_for_day)
                else:
                    if not weight_for_day:
                        app_logger.debug(
                            f"Year {year}: No weight data for day or week {week_number}"
                        )
            else:
                if year in years:  # only count years in heatmap
                    years_with_rest.add(year)

                    if (
                        year in self.heatmap.week_stats
                        and week_number in self.heatmap.week_stats[year]
                        and self.heatmap.week_stats[year][week_number].get(
                            views.CalendarHeatmap.KEY_WEIGHT
                        )
                    ):
                        week_weight = self.heatmap.week_stats[year][week_number][
                            views.CalendarHeatmap.KEY_WEIGHT
                        ]
                        app_logger.debug(
                            f"Year {year} (rest day): Using week min weight "
                            f"{week_weight} (week {week_number})"
                        )
                        if current_weight and week_weight:
                            self.weight_history.append(
                                (
                                    year,
                                    week_weight,
                                    round(current_weight - week_weight, 1),
                                )
                            )
                            weight_history_data.append(week_weight)
                    else:
                        app_logger.debug(
                            f"Year {year} (rest day): No weight data for week "
                            f"{week_number}"
                        )

        # calculate activity predictions formula:
        #   percentage = (activity occurrences / total occurrences) * 100
        # - counts ALL activity occurrences (if same day has 2 runs, both count)
        # - ensures percentages sum to exactly 100%
        # - reflects true distribution of activities across all historical data
        total_activities = sum(activity_preds_data.values())

        if total_activities > 0:
            remaining_pct = 100.0
            sorted_activities = sorted(
                activity_preds_data.items(), key=lambda x: x[1], reverse=True
            )

            for i, (a, count) in enumerate(sorted_activities):
                if i == len(sorted_activities) - 1:
                    # last item gets the remaining percentage to ensure sum = 100%
                    percentage = round(remaining_pct, 1)
                else:
                    percentage = round(count / total_activities * 100.0, 1)
                    remaining_pct -= percentage
                self.activity_preds.append((a, percentage))

        self.activity_preds.sort(key=lambda x: x[1], reverse=True)

        # calculate health predictions gormula:
        #   percentage = (years with condition / total years with data) * 100
        # three categories: Sick, Injured, Healthy (must sum to 100%)
        total_years = len(years_with_data)

        if total_years > 0:
            sick_pct = round(len(years_sick) / total_years * 100.0, 1)
            injured_pct = round(len(years_injured) / total_years * 100.0, 1)
            # healthy = remaining to ensure sum = 100%
            healthy_pct = round(100.0 - sick_pct - injured_pct, 1)

            # only add non-zero predictions
            if sick_pct > 0:
                self.health_preds.append(("Sick", sick_pct))
            if injured_pct > 0:
                self.health_preds.append(("Injured", injured_pct))
            if healthy_pct > 0:
                self.health_preds.append(("Healthy", healthy_pct))

            self.health_preds.sort(key=lambda x: x[1], reverse=True)

        # calculate weight predictions
        app_logger.debug("Weight data collection summary:")
        app_logger.debug(f"  Total weight history entries: {len(weight_history_data)}")
        app_logger.debug(f"  Weight values: {weight_history_data}")
        app_logger.debug(f"  Current weight: {current_weight}")

        if weight_history_data and current_weight:
            avg_weight = sum(weight_history_data) / len(weight_history_data)
            min_hist_weight = min(weight_history_data)
            max_hist_weight = max(weight_history_data)

            healthy_bmi_range = None
            if self.heatmap.user_profile.height > 0:
                height_m = self.heatmap.user_profile.height
                # healthy BMI range: 18.5 - 24.9
                healthy_weight_min = 18.5 * (height_m * height_m)
                healthy_weight_max = 24.9 * (height_m * height_m)
                healthy_bmi_range = (
                    round(healthy_weight_min, 1),
                    round(healthy_weight_max, 1),
                )

            self.weight_preds.append(
                (
                    "Average",
                    round(avg_weight, 1),
                    avg_weight,
                    current_weight,
                    healthy_bmi_range,
                )
            )
            self.weight_preds.append(
                (
                    "Min",
                    round(min_hist_weight, 1),
                    min_hist_weight,
                    current_weight,
                    healthy_bmi_range,
                )
            )
            self.weight_preds.append(
                (
                    "Max",
                    round(max_hist_weight, 1),
                    max_hist_weight,
                    current_weight,
                    healthy_bmi_range,
                )
            )
            self.weight_preds.append(
                (
                    "Current",
                    round(current_weight, 1),
                    current_weight,
                    current_weight,
                    healthy_bmi_range,
                )
            )

        # 1. TRAINING LOAD PREDICTION
        if daily_durations:
            avg_duration = sum(daily_durations) / len(daily_durations)
            min_duration = min(daily_durations)
            max_duration = max(daily_durations)
            self.training_load_preds.append(
                ("Avg Duration", f"{int(avg_duration)} min")
            )
            self.training_load_preds.append(
                ("Range", f"{int(min_duration)}-{int(max_duration)} min")
            )

        if daily_distances:
            avg_distance_km = sum(daily_distances) / len(daily_distances) / 1000.0
            self.training_load_preds.append(
                ("Avg Distance", f"{avg_distance_km:.1f} km")
            )

        # activity intensity distribution (rest, single, double, triple+)
        if total_years > 0:
            rest_count = len(years_with_rest)
            single_count = sum(1 for c in daily_activity_counts if c == 1)
            double_count = sum(1 for c in daily_activity_counts if c == 2)
            triple_count = sum(1 for c in daily_activity_counts if c >= 3)

            total_intensity = rest_count + single_count + double_count + triple_count
            if total_intensity > 0:
                remaining_pct = 100.0
                intensity_data = [
                    ("Rest Day", rest_count),
                    ("Single Activity", single_count),
                    ("Double Activity", double_count),
                    ("Triple+ Activity", triple_count),
                ]
                # Sort by count descending
                intensity_data.sort(key=lambda x: x[1], reverse=True)

                for i, (name, count) in enumerate(intensity_data):
                    if i == len(intensity_data) - 1:
                        pct = round(remaining_pct, 1)
                    else:
                        pct = round(count / total_intensity * 100.0, 1)
                        remaining_pct -= pct
                    if pct > 0:
                        self.intensity_preds.append((name, pct))

        # 2. PERFORMANCE PATTERN PREDICTION
        if daily_paces:
            avg_pace = sum(daily_paces) / len(daily_paces)
            best_pace = min(daily_paces)
            slowest_pace = max(daily_paces)

            # Format as min:sec per km
            def format_pace(pace_min):
                minutes = int(pace_min)
                seconds = int((pace_min - minutes) * 60)
                return f"{minutes}:{seconds:02d}"

            self.performance_preds.append(("Avg Pace", f"{format_pace(avg_pace)} /km"))
            self.performance_preds.append(("Best", f"{format_pace(best_pace)} /km"))
            self.performance_preds.append(
                ("Slowest", f"{format_pace(slowest_pace)} /km")
            )

            # peak = top 25%, Normal = middle 50%, Recovery = bottom 25%
            sorted_paces = sorted(daily_paces)
            q1_idx = max(0, len(sorted_paces) // 4 - 1)
            q3_idx = min(len(sorted_paces) - 1, 3 * len(sorted_paces) // 4)
            q1_pace = sorted_paces[q1_idx]  # faster (lower number)
            q3_pace = sorted_paces[q3_idx]  # slower (higher number)

            peak_count = sum(1 for p in daily_paces if p <= q1_pace)
            recovery_count = sum(1 for p in daily_paces if p >= q3_pace)
            normal_count = len(daily_paces) - peak_count - recovery_count

            total_perf = peak_count + normal_count + recovery_count
            if total_perf > 0:
                remaining_pct = 100.0
                perf_data = [
                    ("Peak Performance", peak_count),
                    ("Normal Pace", normal_count),
                    ("Recovery/Easy", recovery_count),
                ]
                perf_data.sort(key=lambda x: x[1], reverse=True)

                for i, (name, count) in enumerate(perf_data):
                    if i == len(perf_data) - 1:
                        pct = round(remaining_pct, 1)
                    else:
                        pct = round(count / total_perf * 100.0, 1)
                        remaining_pct -= pct
                    if pct > 0:
                        self.performance_category.append((name, pct))

        # 3. SEASONAL/INDOOR-OUTDOOR PREDICTION
        total_activities = indoor_activity_count + outdoor_activity_count
        if total_activities > 0:
            indoor_pct = round(indoor_activity_count / total_activities * 100.0, 1)
            outdoor_pct = round(100.0 - indoor_pct, 1)

            if indoor_pct > 0:
                self.seasonal_preds.append(("Indoor", indoor_pct))
            if outdoor_pct > 0:
                self.seasonal_preds.append(("Outdoor", outdoor_pct))

            self.seasonal_preds.sort(key=lambda x: x[1], reverse=True)

        # 4. RECOVERY / REST DAY PREDICTION
        all_years_count = len(years)

        if all_years_count > 0:
            rest_pct = round(len(years_with_rest) / all_years_count * 100.0, 1)
            recovery_pct = round(len(years_with_recovery) / all_years_count * 100.0, 1)
            # training = remaining to ensure sum = 100%
            training_pct = round(100.0 - rest_pct - recovery_pct, 1)

            if rest_pct > 0:
                self.recovery_preds.append(("Rest Day", rest_pct))
            if recovery_pct > 0:
                self.recovery_preds.append(("Recovery", recovery_pct))
            if training_pct > 0:
                self.recovery_preds.append(("Training", training_pct))

            self.recovery_preds.sort(key=lambda x: x[1], reverse=True)

            # Consistency score: % of years where user was active (not resting)
            years_with_activity = all_years_count - len(years_with_rest)
            self.consistency_score = (
                round(years_with_activity / all_years_count * 100.0, 1)
                if all_years_count > 0
                else 0.0
            )

        # 5. GOAL ACHIEVEMENT PREDICTION
        # calculate this day's typical contribution to the week
        if daily_durations and total_years > 0:
            avg_day_duration = sum(daily_durations) / len(daily_durations)

            day_name = [
                "Monday",
                "Tuesday",
                "Wednesday",
                "Thursday",
                "Friday",
                "Saturday",
                "Sunday",
            ][week_day]

            # simple heuristic: if duration > 60 min, it's a "key training day"
            if avg_day_duration > 60:
                importance = "High importance day"
            elif avg_day_duration > 30:
                importance = "Moderate day"
            else:
                importance = "Light day"

            self.goal_preds.append(("Day Type", day_name))
            self.goal_preds.append(("Importance", importance))
            self.goal_preds.append(("Avg Contribution", f"{int(avg_day_duration)} min"))


class WorkoutOfTheDay:
    """Show workout of the day."""

    def __init__(self, today: str, workout: str) -> None:
        self.today: str = today
        self.workout: str = workout

    def refresh(self, today: str, workout: str) -> None:
        self.today = today
        self.workout = workout

    def _past_workout(self) -> str:
        return self.workout


#
# More ideas v
#


class Eda:
    """Statistical EDA insight"""

    pass


class HeatmapDay:
    def __init__(self) -> None:
        self.pst: float = 0.0  # [0.0, 1.0]
        self.cardinality: int = 0
        self.weekday: int = 0  # Mon/0 ... Sun/6
        self.yearday: int = 0  # [1, 365|366]
        self.hexa_hue: str = f"{hex(0):02}"


class Heatmap:
    def __init__(self) -> None:
        self.days: list[HeatmapDay] = []


class InjuryYearHeatmap(Heatmap):
    """Show heatmap of "be injured" probability/cardinality:

    - indicates when I'm in risk of getting injured
      (due to training intensity, load, ...)

    """

    def __init__(self) -> None:
        Heatmap.__init__(self)


class SickYearHeatmap(Heatmap):
    """Show heatmap of "be sick" probability/cardinality:

    - indicates when I'm in risk of get sick usually

    """

    def __init__(self):
        Heatmap.__init__(self)


class FitnessScoreYearHeatmap(Heatmap):
    """Show heatmap with fitness score height combined over years:

    - indicates when is my performance peak

    """

    def __init__(self) -> None:
        Heatmap.__init__(self)


class ActivityHeatMapOfYear(Heatmap):
    """GitHub like heat map w/ the count of activities per day."""

    def __init__(self) -> None:
        Heatmap.__init__(self)


class ActivityHeatMapOfLife(Heatmap):
    """``ActivityHeatMap`` for all active years."""

    def __init__(self) -> None:
        Heatmap.__init__(self)


class MonthVsKmTableOfYear:
    pass
