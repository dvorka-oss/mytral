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
"""Tests for the "today" marker on the sickness calendar heatmap."""

import datetime

import pytest

from mytral import settings
from mytral import views


def _activity_types() -> settings.UserActivityTypes:
    return settings.UserActivityTypes(activity_types=[])


@pytest.mark.mytral
def test_cell_is_today_matches_current_month_and_day():
    # GIVEN a heatmap cell for today's month and day
    today = datetime.date.today()
    cell = views.CalendarHeatmap.Cell(
        year=today.year,
        month=today.month,
        day=today.day,
        activity_types=_activity_types(),
    )

    # WHEN checking whether the cell maps to today
    # THEN it does
    assert cell.is_today is True


@pytest.mark.mytral
def test_cell_is_today_false_for_other_day():
    # GIVEN a heatmap cell for a day that is not today
    today = datetime.date.today()
    other = today + datetime.timedelta(days=1)
    cell = views.CalendarHeatmap.Cell(
        year=other.year,
        month=other.month,
        day=other.day,
        activity_types=_activity_types(),
    )

    # WHEN checking whether the cell maps to today
    # THEN it does not
    assert cell.is_today is False


@pytest.mark.mytral
def test_cell_is_today_false_for_same_day_different_year():
    # GIVEN a cell with today's month and day but a different year
    today = datetime.date.today()
    cell = views.CalendarHeatmap.Cell(
        year=today.year - 3,
        month=today.month,
        day=today.day,
        activity_types=_activity_types(),
    )

    # WHEN checking whether the cell maps to today
    # THEN it does not, because the activity heatmap keeps the real year per cell
    assert cell.is_today is False
