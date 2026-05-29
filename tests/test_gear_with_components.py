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

"""Tests for Gear with components."""

import pytest

from mytral import settings


@pytest.mark.mytral
def test_gear_with_components():
    """Test gear with components."""
    # GIVEN
    chain = settings.GearComponent(
        name="Chain",
        cost=45.0,
        next_service_km=500,
        distance_meters=250000,
    )
    fork = settings.GearComponent(
        name="Fork",
        cost=800.0,
        next_service_hours=50,
        time_seconds=90000,
    )

    gear = settings.Gear(
        activity_type_key="cycling",
        name="Mountain Bike",
        components=[chain.to_dict(), fork.to_dict()],
    )

    # WHEN
    components = gear.get_components()

    # THEN
    assert len(components) == 2
    assert components[0].name == "Chain"
    assert components[1].name == "Fork"


@pytest.mark.mytral
def test_gear_requires_attention():
    """Test gear requiring attention when component needs service."""
    # GIVEN
    chain = settings.GearComponent(
        name="Chain",
        cost=45.0,
        next_service_km=500,
        distance_meters=550000,  # 550 km - needs service
    )
    gear = settings.Gear(
        activity_type_key="cycling",
        name="Mountain Bike",
        components=[chain.to_dict()],
    )

    # WHEN
    requires = gear.requires_attention()
    requiring_service = gear.components_requiring_service()

    # THEN
    assert requires is True
    assert len(requiring_service) == 1
    assert requiring_service[0].name == "Chain"


@pytest.mark.mytral
def test_gear_filter_active_components():
    """Test filtering active vs retired components."""
    # GIVEN
    active_chain = settings.GearComponent(
        name="New Chain",
        cost=45.0,
        status="active",
    )
    retired_chain = settings.GearComponent(
        name="Old Chain",
        cost=40.0,
        status="retired",
    )
    gear = settings.Gear(
        activity_type_key="cycling",
        name="Mountain Bike",
        components=[active_chain.to_dict(), retired_chain.to_dict()],
    )

    # WHEN
    active_only = gear.get_components(include_retired=False)
    all_components = gear.get_components(include_retired=True)

    # THEN
    assert len(active_only) == 1
    assert active_only[0].name == "New Chain"
    assert len(all_components) == 2


@pytest.mark.mytral
def test_gear_tcoo_recalculation():
    """Test TCoO recalculation with components and service history."""
    # GIVEN
    chain = settings.GearComponent(name="Chain", cost=45.0, key="chain-1")
    fork = settings.GearComponent(name="Fork", cost=800.0, key="fork-1")

    gear = settings.Gear(
        activity_type_key="cycling",
        name="Mountain Bike",
        tcoo_base=3500.0,
        components=[chain.to_dict(), fork.to_dict()],
        component_history={
            "chain-1": [
                {"cost": 45.0, "service_type": "replacement"},
            ],
            "fork-1": [
                {"cost": 120.0, "service_type": "service"},
            ],
        },
    )

    # WHEN
    gear.recalculate_tcoo()

    # THEN
    # tcoo_cost = chain(45) + fork(800) + chain service(45) + fork service(120) = 1010
    assert gear.tcoo_cost == 1010.0
    assert gear.tcoo_base == 3500.0  # unchanged


@pytest.mark.mytral
def test_gear_component_total_tcoo():
    """Test component total TCoO calculation."""
    # GIVEN
    chain = settings.GearComponent(name="Chain", cost=45.0, key="chain-1")
    gear = settings.Gear(
        activity_type_key="cycling",
        name="Mountain Bike",
        components=[chain.to_dict()],
        component_history={
            "chain-1": [
                {"cost": 45.0, "service_type": "replacement"},
                {"cost": 10.0, "service_type": "service"},
            ],
        },
    )

    # WHEN
    total_tcoo = gear.get_component_total_tcoo("chain-1")

    # THEN
    # base cost(45) + replacement(45) + service(10) = 100
    assert total_tcoo == 100.0


@pytest.mark.mytral
def test_gear_last_activity_processed():
    """Test last_activity_processed field."""
    # GIVEN
    gear = settings.Gear(
        activity_type_key="cycling",
        name="Mountain Bike",
        last_activity_processed="2024-12-14T10:30:00Z",
    )

    # WHEN / THEN
    assert gear.last_activity_processed == "2024-12-14T10:30:00Z"


@pytest.mark.mytral
def test_gear_serialization_with_components():
    """Test gear serialization with components."""
    # GIVEN
    chain = settings.GearComponent(name="Chain", cost=45.0)
    gear = settings.Gear(
        activity_type_key="cycling",
        name="Mountain Bike",
        components=[chain.to_dict()],
        component_history={"chain-1": []},
        last_activity_processed="2024-12-14T10:30:00Z",
    )

    # WHEN
    data = gear.to_dict()
    restored = settings.Gear.from_dict(data)

    # THEN
    assert len(restored.components) == 1
    assert restored.components[0]["name"] == "Chain"
    assert restored.component_history == {"chain-1": []}
    assert restored.last_activity_processed == "2024-12-14T10:30:00Z"
