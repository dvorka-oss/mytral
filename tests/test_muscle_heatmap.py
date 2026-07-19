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
"""Tests for the daily muscle heat-map: hit counting and calibration."""

import datetime

import pytest

from mytral import muscle_groups
from mytral import settings
from mytral.backends import entities

_RUN_TYPE = settings.ActivityType(
    name="Run",
    is_distance=True,
    is_exercise=False,
    is_regen=False,
    key="run",
    muscle_groups=["quads", "hamstrings", "calves"],
    muscle_groups_secondary=["abs"],
)

_SQUAT_EXERCISE = settings.Exercise(
    name="squat",
    key="squat",
    muscle_groups=["quads", "glutes"],
    muscle_groups_secondary=["lower_back"],
)


def _activity_types_registry():
    return settings.UserActivityTypes(activity_types=[_RUN_TYPE])


def _exercises_registry():
    return settings.UserExercises(exercises=[_SQUAT_EXERCISE])


def _run_activity(year=2026, month=3, day=5, with_squats=False):
    exercises = (
        [entities.ExerciseEntity(name="squat", series=3, repetitions=10)]
        if with_squats
        else []
    )
    return entities.ActivityEntity(
        activity_type_key="run",
        when_year=year,
        when_month=month,
        when_day=day,
        exercises=exercises,
    )


#
# compute_daily_muscle_stats
#


@pytest.mark.mytral
def test_compute_daily_muscle_stats_counts_activity_type_and_exercise_hits():
    # GIVEN one run (quads/hamstrings/calves + secondary abs) with a squat
    # (quads/glutes + secondary lower_back) logged inside it
    activities = [_run_activity(with_squats=True)]

    # WHEN aggregating the day's muscle stats
    result = muscle_groups.compute_daily_muscle_stats(
        activities, _activity_types_registry(), _exercises_registry()
    )

    # THEN quads is hit twice (run + squat), the rest once, secondary muscles
    # that are not also primary are recorded separately
    assert result.counts == {
        "quads": 2,
        "hamstrings": 1,
        "calves": 1,
        "glutes": 1,
    }
    assert result.secondary_keys == {"abs", "lower_back"}
    print("DONE: compute_daily_muscle_stats counts activity-type and exercise hits")


@pytest.mark.mytral
def test_compute_daily_muscle_stats_empty_day():
    # GIVEN no activities
    # WHEN aggregating the day's muscle stats
    result = muscle_groups.compute_daily_muscle_stats(
        [], _activity_types_registry(), _exercises_registry()
    )
    # THEN there is nothing to show
    assert result.counts == {}
    assert result.secondary_keys == set()
    print("DONE: compute_daily_muscle_stats handles an empty day")


#
# group_activities_by_date
#


@pytest.mark.mytral
def test_group_activities_by_date_buckets_by_calendar_day():
    # GIVEN activities on two distinct days
    activities = [
        _run_activity(year=2026, month=3, day=5),
        _run_activity(year=2026, month=3, day=5),
        _run_activity(year=2026, month=3, day=6),
    ]

    # WHEN grouping by date
    by_date = muscle_groups.group_activities_by_date(activities)

    # THEN each bucket contains exactly the activities of that day
    assert set(by_date.keys()) == {
        datetime.date(2026, 3, 5),
        datetime.date(2026, 3, 6),
    }
    assert len(by_date[datetime.date(2026, 3, 5)]) == 2
    assert len(by_date[datetime.date(2026, 3, 6)]) == 1
    print("DONE: group_activities_by_date buckets by calendar day")


#
# calibrate_intensity_thresholds / intensity_class_for_count
#


@pytest.mark.mytral
def test_calibrate_intensity_thresholds_needs_minimum_history():
    # GIVEN a muscle group with fewer nonzero days than the minimum sample size
    history = [
        {"quads": 1} for _ in range(muscle_groups.HEATMAP_MIN_HISTORY_SAMPLES - 1)
    ]

    # WHEN calibrating thresholds
    thresholds = muscle_groups.calibrate_intensity_thresholds(history)

    # THEN the muscle group is omitted so callers fall back to the defaults
    assert "quads" not in thresholds
    print("DONE: calibrate_intensity_thresholds requires a minimum sample size")


@pytest.mark.mytral
def test_calibrate_intensity_thresholds_uniform_history_is_not_stuck_coldest():
    # GIVEN a user who hits quads with a count of 1 on every training day for
    # 60 days -- with the old fixed thresholds (2/4/7/10) this always painted
    # the coldest step, regardless of how consistent the training was
    history = [{"quads": 1} for _ in range(60)]

    # WHEN calibrating thresholds and classifying a typical day (count=1)
    thresholds = muscle_groups.calibrate_intensity_thresholds(history)
    css_class = muscle_groups.intensity_class_for_count(1, thresholds["quads"])

    # THEN a day matching the user's own consistent baseline clears the
    # coldest step -- it is no longer pinned to intensity-1 by construction
    assert css_class != "state-active intensity-1"
    print("DONE: a consistent training baseline is not pinned to the coldest step")


@pytest.mark.mytral
def test_calibrate_intensity_thresholds_spreads_a_varied_history_across_buckets():
    # GIVEN a varied history: mostly light days (count=1), some medium
    # (count=3), a few heavy (count=6), rare very heavy (count=12)
    history = (
        [{"quads": 1} for _ in range(50)]
        + [{"quads": 3} for _ in range(20)]
        + [{"quads": 6} for _ in range(8)]
        + [{"quads": 12} for _ in range(2)]
    )

    # WHEN calibrating and classifying each of those counts
    thresholds = muscle_groups.calibrate_intensity_thresholds(history)
    classes = [
        muscle_groups.intensity_class_for_count(c, thresholds["quads"])
        for c in (1, 3, 6, 12)
    ]

    # THEN the ramp is monotonic and actually reaches the hottest step for
    # the rarest, heaviest days -- the calibration is meaningful, not flat
    assert classes == sorted(classes)
    assert classes[0] != classes[-1]
    assert classes[-1] == "state-active intensity-5"
    print("DONE: a varied history spreads across the full intensity ramp")


@pytest.mark.mytral
def test_intensity_class_for_count_boundaries():
    # GIVEN fixed thresholds
    thresholds = (2, 4, 7, 10)

    # WHEN / THEN each boundary count maps to the expected class
    assert muscle_groups.intensity_class_for_count(0, thresholds) == (
        "state-active intensity-1"
    )
    assert muscle_groups.intensity_class_for_count(2, thresholds) == (
        "state-active intensity-2"
    )
    assert muscle_groups.intensity_class_for_count(4, thresholds) == (
        "state-active intensity-3"
    )
    assert muscle_groups.intensity_class_for_count(7, thresholds) == (
        "state-active intensity-4"
    )
    assert muscle_groups.intensity_class_for_count(10, thresholds) == (
        "state-active intensity-5"
    )
    print("DONE: intensity_class_for_count boundaries map correctly")


#
# build_day_muscle_highlights
#


@pytest.mark.mytral
def test_build_day_muscle_highlights_falls_back_without_history():
    # GIVEN a day with a single quads hit and no history at all
    day_stats = muscle_groups.DailyMuscleStats(
        counts={"quads": 1}, secondary_keys=set()
    )

    # WHEN building highlights
    highlights = muscle_groups.build_day_muscle_highlights(day_stats, [])

    # THEN it falls back to the default thresholds (count=1 -> coolest step)
    assert highlights == {"quads": "state-active intensity-1"}
    print("DONE: build_day_muscle_highlights falls back without history")


@pytest.mark.mytral
def test_build_day_muscle_highlights_secondary_only_muscle_is_coolest():
    # GIVEN a day where abs is touched only as a secondary muscle
    day_stats = muscle_groups.DailyMuscleStats(counts={}, secondary_keys={"abs"})

    # WHEN building highlights
    highlights = muscle_groups.build_day_muscle_highlights(day_stats, [])

    # THEN it renders at the coolest step
    assert highlights == {"abs": "state-active intensity-1"}
    print("DONE: secondary-only muscle groups render at the coolest step")


@pytest.mark.mytral
def test_build_day_muscle_highlights_primary_count_wins_over_secondary():
    # GIVEN a muscle group that is both primary (hit twice) and secondary today
    day_stats = muscle_groups.DailyMuscleStats(
        counts={"quads": 2}, secondary_keys={"quads"}
    )

    # WHEN building highlights with no history (default thresholds apply)
    highlights = muscle_groups.build_day_muscle_highlights(day_stats, [])

    # THEN the primary count's class is kept, not downgraded to intensity-1
    assert highlights == {"quads": "state-active intensity-2"}
    print("DONE: primary count wins over secondary-only status")
