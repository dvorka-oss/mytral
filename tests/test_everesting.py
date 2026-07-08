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
import datetime

import pytest

from mytral import commons
from mytral import everesting
from mytral.backends import entities


def _activity(
    key: str, year: int, month: int, day: int, activity_type_key: str, gain: int
) -> entities.ActivityEntity:
    return entities.ActivityEntity(
        key=key,
        when_year=year,
        when_month=month,
        when_day=day,
        activity_type_key=activity_type_key,
        elevation_gain=gain,
    )


@pytest.mark.mytral
def test_climbed_meters_is_sport_and_period_scoped():
    # GIVEN rides and runs across this and previous week
    today = datetime.date(2024, 6, 13)  # Thursday; week starts Mon 2024-06-10
    ride_this_week = _activity("r1", 2024, 6, 12, commons.AT_RIDE, 1500)
    ride_earlier_month = _activity("r2", 2024, 6, 3, commons.AT_RIDE, 1000)
    run_this_week = _activity("run1", 2024, 6, 11, commons.AT_RUN, 700)
    ride_last_week = _activity("r3", 2024, 6, 6, commons.AT_RIDE, 999)
    activities = [ride_this_week, ride_earlier_month, run_this_week, ride_last_week]

    # WHEN summing Ride elevation for the week and the month
    ride_week = everesting.climbed_meters(
        activities, commons.M_AT_RIDE, commons.StatsPeriod.WEEK, today
    )
    ride_month = everesting.climbed_meters(
        activities, commons.M_AT_RIDE, commons.StatsPeriod.MONTH, today
    )

    # THEN only Ride activities in the window count; the run is always excluded,
    # last week's ride is out of the week but still within the month
    assert ride_week == 1500
    assert ride_month == 1500 + 1000 + 999
    print("DONE climbed meters are sport and period scoped")


@pytest.mark.mytral
def test_in_period_excludes_future_and_incomplete_dates():
    # GIVEN a future activity and one with an incomplete date
    today = datetime.date(2024, 6, 13)
    future = _activity("f", 2024, 6, 20, commons.AT_RIDE, 500)
    incomplete = entities.ActivityEntity(
        key="i", activity_type_key=commons.AT_RIDE, elevation_gain=500
    )
    incomplete.when_year = 0  # force an incomplete date

    # WHEN checking period membership for the current year
    # THEN both are excluded
    assert not everesting.in_period(future, commons.StatsPeriod.YEAR, today)
    assert not everesting.in_period(incomplete, commons.StatsPeriod.YEAR, today)
    print("DONE future and incomplete dates are excluded")


@pytest.mark.mytral
def test_top_climbing_meta_sport_picks_most_vertical():
    # GIVEN more running vertical than riding this year
    today = datetime.date(2024, 6, 13)
    activities = [
        _activity("run1", 2024, 1, 5, commons.AT_RUN, 3000),
        _activity("run2", 2024, 3, 5, commons.AT_RUN, 3000),
        _activity("ride1", 2024, 2, 5, commons.AT_RIDE, 2000),
    ]

    # WHEN picking the top climbing sport
    top = everesting.top_climbing_meta_sport(activities, today)

    # THEN running wins
    assert top == commons.M_AT_RUN
    print("DONE top climbing sport is the one with most vertical")


@pytest.mark.mytral
def test_top_climbing_meta_sport_none_without_climbing():
    # GIVEN only a swim (non-climbing sport) with no elevation
    today = datetime.date(2024, 6, 13)
    activities = [_activity("s1", 2024, 6, 1, commons.AT_SWIM, 0)]

    # WHEN picking the top climbing sport
    # THEN there is none
    assert everesting.top_climbing_meta_sport(activities, today) is None
    print("DONE no climbing sport yields None")


@pytest.mark.mytral
def test_progress_reports_pct_and_eta():
    # GIVEN 1000 m climbed by day 10 of the month
    today = datetime.date(2024, 6, 10)
    activities = [_activity("r1", 2024, 6, 5, commons.AT_RIDE, 1000)]

    # WHEN computing month progress
    p = everesting.progress(
        activities, commons.M_AT_RIDE, commons.StatsPeriod.MONTH, today
    )

    # THEN climbed, pct, summited and ETA are consistent
    assert p.climbed_m == 1000
    assert p.target_m == commons.EVERESTING_M
    assert not p.summited
    assert round(p.pct, 2) == round(1000 / commons.EVERESTING_M * 100.0, 2)
    # rate = 1000 / 10 = 100 m/day; remaining 7848 -> ceil(78.48) = 79 days
    assert p.eta_days == 79
    assert p.meta_sport_label == "Ride"
    print("DONE progress reports pct and ETA")


@pytest.mark.mytral
def test_progress_summited_has_no_eta():
    # GIVEN a full Everest climbed in the day
    today = datetime.date(2024, 6, 10)
    activities = [_activity("r1", 2024, 6, 10, commons.AT_RIDE, 9000)]

    # WHEN computing day progress
    p = everesting.progress(
        activities, commons.M_AT_RIDE, commons.StatsPeriod.DAY, today
    )

    # THEN it is summited with no ETA and pct over 100
    assert p.summited
    assert p.eta_days is None
    assert p.pct > 100.0
    print("DONE summited progress has no ETA")


@pytest.mark.mytral
def test_dashboard_periods_empty_without_climbing():
    # GIVEN no climbing activities
    today = datetime.date(2024, 6, 10)
    activities = [_activity("s1", 2024, 6, 1, commons.AT_SWIM, 0)]

    # WHEN building dashboard periods
    # THEN the result is empty so the card can hide
    assert everesting.dashboard_periods(activities, today) == {}
    print("DONE dashboard periods empty without climbing")


@pytest.mark.mytral
def test_dashboard_periods_covers_all_windows():
    # GIVEN riding vertical spread across the year
    today = datetime.date(2024, 6, 13)
    activities = [
        _activity("r_today", 2024, 6, 13, commons.AT_RIDE, 300),
        _activity("r_week", 2024, 6, 11, commons.AT_RIDE, 200),
        _activity("r_month", 2024, 6, 2, commons.AT_RIDE, 500),
        _activity("r_year", 2024, 1, 2, commons.AT_RIDE, 1000),
    ]

    # WHEN building dashboard periods
    periods = everesting.dashboard_periods(activities, today)

    # THEN each window accumulates the expected cumulative vertical
    assert set(periods.keys()) == {"day", "week", "month", "year"}
    assert periods["day"].climbed_m == 300
    assert periods["week"].climbed_m == 500  # today + week
    assert periods["month"].climbed_m == 1000  # + month
    assert periods["year"].climbed_m == 2000  # + year
    print("DONE dashboard periods cover day/week/month/year")


@pytest.mark.mytral
def test_everesting_variant_tiers():
    # GIVEN various single-activity elevation gains
    # WHEN resolving the variant
    # THEN the highest reached tier is returned
    assert commons.everesting_variant(100) is None
    assert commons.everesting_variant(2212) == "Quarter Everest"
    assert commons.everesting_variant(4424) == "Half Everest"
    assert commons.everesting_variant(8848) == "Everesting"
    assert commons.everesting_variant(20000) == "Double Everesting"
    assert commons.everesting_variant(30000) == "Triple Everesting"
    print("DONE everesting variant tiers resolve correctly")


@pytest.mark.mytral
def test_activity_everested_properties():
    # GIVEN activities below and at the Everest threshold
    below = _activity("a", 2024, 6, 1, commons.AT_RIDE, 5000)
    everested = _activity("b", 2024, 6, 1, commons.AT_RIDE, 8848)

    # WHEN reading the entity properties
    # THEN the flags and labels are correct
    assert not below.everested
    assert below.everesting_variant == "Half Everest"
    assert everested.everested
    assert everested.everesting_variant == "Everesting"
    print("DONE activity everested properties are correct")


@pytest.mark.mytral
def test_lifetime_vertical_and_everests():
    # GIVEN a lifetime of activities
    activities = [
        _activity("a", 2020, 1, 1, commons.AT_RIDE, 8848),
        _activity("b", 2021, 1, 1, commons.AT_RUN, 8848),
    ]

    # WHEN computing lifetime vertical and Everests
    total = everesting.lifetime_vertical_m(activities)
    everests = everesting.everests_climbed(total)

    # THEN the totals are consistent with the constants
    assert total == 2 * commons.EVERESTING_M
    assert round(everests, 3) == 2.0
    print("DONE lifetime vertical and Everests are correct")
