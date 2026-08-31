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

import pytest

from mytral import settings
from mytral import stats
from mytral.blueprints import gear_crud


def _gear_fixture() -> tuple[list, stats.UserGearStats]:
    """Build gear items of two activity types and their statistics."""
    shoes = settings.Gear(activity_type_key="run", name="Shoes", key="k-shoes")
    bike = settings.Gear(activity_type_key="ride", name="Bike", key="k-bike")
    boat = settings.Gear(activity_type_key="row", name="Boat", key="k-boat")

    gear_stats = stats.UserGearStats()
    gear_stats.add_stats("k-shoes", stats.GearStats(stat_use=3, stat_to="2026-01-01"))
    gear_stats.add_stats("k-bike", stats.GearStats(stat_use=1, stat_to="2026-03-01"))
    gear_stats.add_stats("k-boat", stats.GearStats(stat_use=7, stat_to="2026-02-01"))

    return [shoes, bike, boat], gear_stats


@pytest.mark.mytral
def test_filter_gear_by_default_activity_type():
    # GIVEN
    gear_items, gear_stats = _gear_fixture()

    # WHEN
    filtered = gear_crud._filter_and_sort_gear(
        gear_items, gear_stats, "run", "used", "desc"
    )

    # THEN
    assert [g.name for g in filtered] == ["Shoes"]
    print("DONE gear filtered by default activity type")


@pytest.mark.mytral
def test_filter_gear_by_empty_activity_type_keeps_all():
    # GIVEN
    gear_items, gear_stats = _gear_fixture()

    # WHEN
    filtered = gear_crud._filter_and_sort_gear(
        gear_items, gear_stats, "", "used", "desc"
    )

    # THEN
    assert len(filtered) == 3
    print("DONE empty activity type filter keeps all gear")


@pytest.mark.mytral
def test_sort_gear_by_last_used_descending_is_the_default():
    # GIVEN
    gear_items, gear_stats = _gear_fixture()

    # WHEN
    sorted_gear = gear_crud._filter_and_sort_gear(
        gear_items, gear_stats, "", "used", "desc"
    )

    # THEN
    assert [g.name for g in sorted_gear] == ["Bike", "Boat", "Shoes"]
    print("DONE gear sorted by last used descending")


@pytest.mark.mytral
def test_sort_gear_by_name_ascending():
    # GIVEN
    gear_items, gear_stats = _gear_fixture()

    # WHEN
    sorted_gear = gear_crud._filter_and_sort_gear(
        gear_items, gear_stats, "", "name", "asc"
    )

    # THEN
    assert [g.name for g in sorted_gear] == ["Bike", "Boat", "Shoes"]
    print("DONE gear sorted by name ascending")


@pytest.mark.mytral
def test_sort_gear_by_usage_descending():
    # GIVEN
    gear_items, gear_stats = _gear_fixture()

    # WHEN
    sorted_gear = gear_crud._filter_and_sort_gear(
        gear_items, gear_stats, "", "usage", "desc"
    )

    # THEN
    assert [g.name for g in sorted_gear] == ["Boat", "Shoes", "Bike"]
    print("DONE gear sorted by usage descending")


@pytest.mark.mytral
def test_sort_gear_without_statistics_does_not_fail():
    # GIVEN
    gear_items, _ = _gear_fixture()
    empty_stats = stats.UserGearStats()

    # WHEN
    sorted_gear = gear_crud._filter_and_sort_gear(
        gear_items, empty_stats, "", "distance", "desc"
    )

    # THEN
    assert len(sorted_gear) == 3
    print("DONE gear without statistics sorted without failure")
