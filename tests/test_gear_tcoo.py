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


@pytest.mark.mytral
def test_tcoo_total_calculation():
    """Test total cost of ownership calculation."""
    # GIVEN
    gear = settings.Gear(
        activity_type_key="run",
        name="Test Running Shoes",
        tcoo_base=150.0,
        tcoo_additional=25.0,
    )
    gear.tcoo_cost = 50.0

    # WHEN
    total = gear.tcoo_total

    # THEN
    assert total == 225.0, f"Expected 225.0 but got {total}"
    print(f"DONE TCoO total calculation: {total}")


@pytest.mark.mytral
def test_tcoo_maintenance_calculation_with_components():
    """Test maintenance cost calculation from components."""
    # GIVEN
    gear = settings.Gear(
        activity_type_key="ride",
        name="Road Bike",
        tcoo_base=2500.0,
        tcoo_additional=150.0,
    )

    # add components
    chain = settings.GearComponent(name="Chain", cost=30.0)
    tire_front = settings.GearComponent(name="Front Tire", cost=50.0)
    tire_rear = settings.GearComponent(name="Rear Tire", cost=50.0)

    gear.components = [
        chain.to_dict(),
        tire_front.to_dict(),
        tire_rear.to_dict(),
    ]

    # WHEN
    gear.recalculate_tcoo()

    # THEN
    assert gear.tcoo_cost == 130.0, f"Expected 130.0 but got {gear.tcoo_cost}"
    assert gear.tcoo_total == 2780.0, f"Expected 2780.0 but got {gear.tcoo_total}"
    print(f"DONE Component costs: {gear.tcoo_cost}")
    print(f"DONE Total TCoO: {gear.tcoo_total}")


@pytest.mark.mytral
def test_tcoo_maintenance_calculation_with_service_history():
    """Test maintenance cost includes service history."""
    # GIVEN
    gear = settings.Gear(
        activity_type_key="ride",
        name="Mountain Bike",
        tcoo_base=1500.0,
        tcoo_additional=0.0,
    )

    # add component
    fork = settings.GearComponent(name="Fork", cost=400.0)
    gear.components = [fork.to_dict()]

    # add service history
    gear.component_history = {
        fork.key: [
            {
                "date": "2024-01-15",
                "service_type": "service",
                "cost": 50.0,
                "notes": "Oil change",
                "km_at_service": 500.0,
                "hours_at_service": 25.0,
            },
            {
                "date": "2024-06-15",
                "service_type": "service",
                "cost": 75.0,
                "notes": "Full rebuild",
                "km_at_service": 1200.0,
                "hours_at_service": 60.0,
            },
        ]
    }

    # WHEN
    gear.recalculate_tcoo()

    # THEN
    assert gear.tcoo_cost == 525.0, f"Expected 525.0 but got {gear.tcoo_cost}"
    assert gear.tcoo_total == 2025.0, f"Expected 2025.0 but got {gear.tcoo_total}"
    print(f"DONE Maintenance cost (component + services): {gear.tcoo_cost}")
    print(f"DONE Total TCoO: {gear.tcoo_total}")


@pytest.mark.mytral
def test_tcoo_no_double_counting():
    """Test that component costs are not double counted."""
    # GIVEN
    gear = settings.Gear(
        activity_type_key="ride",
        name="Test Bike",
        tcoo_base=1000.0,
        tcoo_additional=50.0,
    )

    # add component with cost
    chain = settings.GearComponent(name="Chain", cost=30.0)
    gear.components = [chain.to_dict()]

    # WHEN - calculate twice to ensure no double counting
    gear.recalculate_tcoo()
    first_calculation = gear.tcoo_cost
    gear.recalculate_tcoo()
    second_calculation = gear.tcoo_cost

    # THEN
    assert first_calculation == 30.0, f"Expected 30.0 but got {first_calculation}"
    assert second_calculation == 30.0, f"Expected 30.0 but got {second_calculation}"
    assert first_calculation == second_calculation, "Recalculation changed the value!"
    print(f"DONE No double counting: {first_calculation} == {second_calculation}")


@pytest.mark.mytral
def test_tcoo_with_retired_components():
    """Test that retired components are still included in TCoO."""
    # GIVEN
    gear = settings.Gear(
        activity_type_key="ride",
        name="Test Bike",
        tcoo_base=1000.0,
        tcoo_additional=0.0,
    )

    # add active and retired components
    chain_old = settings.GearComponent(name="Chain Old", cost=30.0, status="retired")
    chain_new = settings.GearComponent(name="Chain New", cost=35.0, status="active")

    gear.components = [
        chain_old.to_dict(),
        chain_new.to_dict(),
    ]

    # WHEN
    gear.recalculate_tcoo()

    # THEN
    assert gear.tcoo_cost == 65.0, f"Expected 65.0 but got {gear.tcoo_cost}"
    assert gear.tcoo_total == 1065.0, f"Expected 1065.0 but got {gear.tcoo_total}"
    print(f"DONE Retired components included: {gear.tcoo_cost}")


@pytest.mark.mytral
def test_tcoo_zero_values():
    """Test TCoO calculation with zero values."""
    # GIVEN
    gear = settings.Gear(
        activity_type_key="run",
        name="Free Shoes",
        tcoo_base=0.0,
        tcoo_additional=0.0,
    )
    gear.tcoo_cost = 0.0

    # WHEN
    total = gear.tcoo_total

    # THEN
    assert total == 0.0, f"Expected 0.0 but got {total}"
    print(f"DONE Zero TCoO: {total}")


@pytest.mark.mytral
def test_tcoo_serialization():
    """Test that TCoO fields serialize and deserialize correctly."""
    # GIVEN
    original = settings.Gear(
        activity_type_key="ride",
        name="Test Bike",
        tcoo_base=1500.0,
        tcoo_cost=300.0,
        tcoo_additional=100.0,
    )

    # WHEN
    gear_dict = original.to_dict()
    restored = settings.Gear.from_dict(gear_dict)

    # THEN
    assert restored.tcoo_base == 1500.0
    assert restored.tcoo_cost == 300.0
    assert restored.tcoo_additional == 100.0
    assert restored.tcoo_total == 1900.0
    print("DONE Serialization preserves TCoO values")


@pytest.mark.mytral
def test_tcoo_backward_compatibility():
    """Test that old gear without tcoo_additional field loads correctly."""
    # GIVEN - simulate old data without tcoo_additional
    old_gear_dict = {
        "activity_type_key": "run",
        "name": "Old Shoes",
        "tcoo_base": 100.0,
        "tcoo_cost": 20.0,
        # tcoo_additional is missing
        "key": "test-key-123",
    }

    # WHEN
    gear = settings.Gear.from_dict(old_gear_dict)

    # THEN
    assert gear.tcoo_base == 100.0
    assert gear.tcoo_cost == 20.0
    assert gear.tcoo_additional == 0.0, "Should default to 0.0"
    assert gear.tcoo_total == 120.0
    print("DONE Backward compatibility: tcoo_additional defaults to 0.0")


@pytest.mark.mytral
def test_tcoo_complex_scenario():
    """Test a complex real-world scenario."""
    # GIVEN - Road bike with multiple components and service history
    gear = settings.Gear(
        activity_type_key="ride",
        name="Road Bike Ultegra",
        tcoo_base=3500.0,
        tcoo_additional=250.0,  # professional bike fitting
    )

    # add components
    chain = settings.GearComponent(name="Chain", cost=45.0)
    cassette = settings.GearComponent(name="Cassette", cost=120.0)
    tire_front = settings.GearComponent(name="Front Tire", cost=60.0)
    tire_rear = settings.GearComponent(name="Rear Tire", cost=60.0)

    gear.components = [
        chain.to_dict(),
        cassette.to_dict(),
        tire_front.to_dict(),
        tire_rear.to_dict(),
    ]

    # add service history
    gear.component_history = {
        chain.key: [
            {
                "date": "2024-03-15",
                "service_type": "replacement",
                "cost": 45.0,
                "notes": "Chain replacement",
                "km_at_service": 3000.0,
                "hours_at_service": 100.0,
            },
            {
                "date": "2024-09-20",
                "service_type": "replacement",
                "cost": 45.0,
                "notes": "Chain replacement",
                "km_at_service": 6000.0,
                "hours_at_service": 200.0,
            },
        ],
        cassette.key: [
            {
                "date": "2024-09-20",
                "service_type": "replacement",
                "cost": 120.0,
                "notes": "Cassette replacement",
                "km_at_service": 6000.0,
                "hours_at_service": 200.0,
            },
        ],
    }

    # WHEN
    gear.recalculate_tcoo()

    # THEN
    # Components: 45 + 120 + 60 + 60 = 285
    # Services: 45 + 45 + 120 = 210
    # Total maintenance: 285 + 210 = 495
    # Total TCoO: 3500 + 495 + 250 = 4245

    assert gear.tcoo_cost == 495.0, f"Expected 495.0 but got {gear.tcoo_cost}"
    assert gear.tcoo_total == 4245.0, f"Expected 4245.0 but got {gear.tcoo_total}"

    print("DONE Complex scenario:")
    print(f"  - Base price: ${gear.tcoo_base}")
    print(f"  - Maintenance cost: ${gear.tcoo_cost}")
    print(f"  - Additional cost: ${gear.tcoo_additional}")
    print(f"  - Total TCoO: ${gear.tcoo_total}")
