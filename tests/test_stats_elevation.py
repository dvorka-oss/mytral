# MyTraL: my trailing log
#
# Copyright (C) 2015-2026 Martin Dvorak <martin.dvorak@mindforger.com>
#
# This program is free software: you can redistribute it and/or modify
# it under the terms of the GNU Affero General Public License as published by
# the Free Software Foundation, either version 3 of the License, or
# (at your option) any later version.
# This program is distributed in the hope that it will be useful,
# but WITHOUT ANY WARRANTY; without even the implied warranty of
# MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the
# GNU Affero General Public License for more details.
#
# You should have received a copy of the GNU Affero General Public License
# along with this program. If not, see <http://www.gnu.org/licenses/>.
import pytest

from mytral import commons
from mytral import settings
from mytral import stats
from mytral.backends import entities


def _activity_types() -> settings.UserActivityTypes:
    run = settings.ActivityType(
        name="Run",
        is_distance=True,
        is_exercise=False,
        is_regen=False,
        key="run",
    )
    note = settings.ActivityType(
        name="Note",
        is_distance=False,
        is_exercise=False,
        is_regen=False,
        is_meta=True,
        key="note",
    )
    return settings.UserActivityTypes(activity_types=[run, note])


@pytest.mark.mytral
def test_get_month_totals_elevation_cumulative():
    # GIVEN two sport activities with known elevation gain and one meta activity
    activity_types = _activity_types()
    a1 = entities.ActivityEntity(
        key="a1",
        when_year=2024,
        when_month=1,
        when_day=1,
        activity_type_key="run",
        elevation_gain=100,
    )
    a2 = entities.ActivityEntity(
        key="a2",
        when_year=2024,
        when_month=1,
        when_day=2,
        activity_type_key="run",
        elevation_gain=200,
    )
    # meta activity must be excluded from sport totals
    a_meta = entities.ActivityEntity(
        key="a3",
        when_year=2024,
        when_month=1,
        when_day=2,
        activity_type_key="note",
        elevation_gain=999,
    )
    activities_stats = stats.ActivitiesStats([a1, a2, a_meta])

    # WHEN computing cumulative monthly elevation totals
    totals = activities_stats.get_month_totals(
        aspect=commons.StatsAspect.ELEVATION, activity_types=activity_types
    )

    # THEN totals accumulate elevation gain and ignore the meta activity
    assert totals[1] == 100
    assert totals[2] == 300
    assert totals[31] == 300
    print("DONE monthly elevation totals are cumulative and exclude meta")


@pytest.mark.mytral
def test_get_year_totals_elevation_cumulative():
    # GIVEN sport activities in different months and one meta activity
    activity_types = _activity_types()
    a1 = entities.ActivityEntity(
        key="a1",
        when_year=2024,
        when_month=1,
        when_day=1,
        activity_type_key="run",
        elevation_gain=100,
    )
    a2 = entities.ActivityEntity(
        key="a2",
        when_year=2024,
        when_month=3,
        when_day=1,
        activity_type_key="run",
        elevation_gain=200,
    )
    a_meta = entities.ActivityEntity(
        key="a3",
        when_year=2024,
        when_month=3,
        when_day=1,
        activity_type_key="note",
        elevation_gain=999,
    )
    activities_stats = stats.ActivitiesStats([a1, a2, a_meta])

    # WHEN computing cumulative yearly elevation totals
    totals = activities_stats.get_year_totals(
        aspect=commons.StatsAspect.ELEVATION, activity_types=activity_types
    )

    # THEN totals accumulate elevation gain per month and ignore the meta activity
    assert totals[1] == 100
    assert totals[2] == 100
    assert totals[3] == 300
    assert totals[12] == 300
    print("DONE yearly elevation totals are cumulative and exclude meta")


@pytest.mark.mytral
def test_get_month_totals_elevation_scoped_to_meta_sport():
    # GIVEN a ride and a run on the same day with known elevation gain
    activity_types = _activity_types()
    ride = entities.ActivityEntity(
        key="ride",
        when_year=2024,
        when_month=1,
        when_day=1,
        activity_type_key=commons.AT_RIDE,
        elevation_gain=500,
    )
    run = entities.ActivityEntity(
        key="run",
        when_year=2024,
        when_month=1,
        when_day=1,
        activity_type_key=commons.AT_RUN,
        elevation_gain=300,
    )
    activities_stats = stats.ActivitiesStats([ride, run])

    # WHEN computing monthly elevation totals scoped to the Ride meta sport
    totals = activities_stats.get_month_totals(
        aspect=commons.StatsAspect.ELEVATION,
        activity_types=activity_types,
        meta_sport=commons.M_AT_RIDE,
    )

    # THEN only the ride counts, the run is excluded
    assert totals[1] == 500
    print("DONE monthly elevation totals can be scoped to a meta sport")


@pytest.mark.mytral
def test_get_year_totals_elevation_scoped_to_meta_sport():
    # GIVEN a ride and a run in different months
    activity_types = _activity_types()
    ride = entities.ActivityEntity(
        key="ride",
        when_year=2024,
        when_month=1,
        when_day=1,
        activity_type_key=commons.AT_RIDE,
        elevation_gain=500,
    )
    run = entities.ActivityEntity(
        key="run",
        when_year=2024,
        when_month=2,
        when_day=1,
        activity_type_key=commons.AT_RUN,
        elevation_gain=300,
    )
    activities_stats = stats.ActivitiesStats([ride, run])

    # WHEN computing yearly elevation totals scoped to the Run meta sport
    totals = activities_stats.get_year_totals(
        aspect=commons.StatsAspect.ELEVATION,
        activity_types=activity_types,
        meta_sport=commons.M_AT_RUN,
    )

    # THEN only the run counts, the ride is excluded
    assert totals[1] == 0
    assert totals[2] == 300
    assert totals[12] == 300
    print("DONE yearly elevation totals can be scoped to a meta sport")
