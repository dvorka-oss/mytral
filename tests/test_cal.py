# MyTraL: my trailing log
#
# Copyright (C) 2022-2026 Martin Dvorak <martin.dvorak@mindforger.com>
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


@pytest.mark.parametrize(
    "week_date",
    [
        "2024-W28-1",  # Monday
        "2024-W28-2",  # Tuesday
        "2024-W28-3",  # Wednesday
        "2024-W28-4",  # Thursday
        "2024-W28-5",  # Friday
        "2024-W28-6",  # Saturday
        "2024-W28-0",  # Sunday
    ],
)
@pytest.mark.tool
def test_week_to_date(week_date):
    #
    # GIVEN
    #
    import datetime

    #
    # WHEN
    #
    r = datetime.datetime.strptime(week_date, "%Y-W%W-%w")

    #
    # THEN
    print(r)
