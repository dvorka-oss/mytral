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

from mytral import loggers
from mytral import settings
from mytral import stats
from mytral.backends import entities


@pytest.mark.mytral
def test_user_profile_stats_from_entity():
    # GIVEN
    user_profile = settings.UserProfile(
        user_id="test_user",
        user="test_user",
        email="test@test.com",
        password_enc="none",
        dataset_name="test",
        dataset_names=["test"],
        height=1.8,
        athlete_metrics=settings.AthleteMetrics(),
    )
    logger = loggers.MytralPrintLogger()

    # Activity 1: older, has weight
    a1 = entities.ActivityEntity(
        key="a1",
        when_year=2024,
        when_month=1,
        when_day=1,
        when_hour=10,
        when_minute=0,
        when_second=0,
        weight=80.0,
        min_hr=60,
    )

    # Activity 2: newer, has only weight
    a2 = entities.ActivityEntity(
        key="a2",
        when_year=2024,
        when_month=1,
        when_day=2,
        when_hour=10,
        when_minute=0,
        when_second=0,
        weight=79.0,
        min_hr=0,
    )

    # Activity 3: newest, has only min_hr
    a3 = entities.ActivityEntity(
        key="a3",
        when_year=2024,
        when_month=1,
        when_day=3,
        when_hour=10,
        when_minute=0,
        when_second=0,
        weight=0.0,
        min_hr=55,
    )

    activities = [a1, a2, a3]

    # WHEN
    profile_stats = stats.UserProfileStats.from_entity(user_profile, activities, logger)

    # THEN
    assert profile_stats.weight == 79.0  # from a2
    assert profile_stats.resting_hr == 55  # from a3
    print("DONE: UserProfileStats correctly extracts weight and resting_hr")
