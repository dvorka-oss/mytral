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

"""Tests for GearComponent model."""

from datetime import datetime
from datetime import timedelta

import pytest

from mytral import settings


@pytest.mark.mytral
def test_component_creation():
    """Test basic component creation."""
    # GIVEN
    component = settings.GearComponent(
        name="Chain",
        cost=45.0,
        installed_date="2024-01-15",
        next_service_km=500,
    )

    # WHEN / THEN
    assert component.name == "Chain"
    assert component.cost == 45.0
    assert component.installed_date == "2024-01-15"
    assert component.next_service_km == 500
    assert component.status == "active"
    assert component.distance_meters == 0
    assert component.time_seconds == 0
    assert component.key != ""


@pytest.mark.mytral
def test_component_distance_conversion():
    """Test distance conversion from meters to km."""
    # GIVEN
    component = settings.GearComponent(name="Chain", distance_meters=45000)

    # WHEN
    km = component.distance_km

    # THEN
    assert km == 45.0


@pytest.mark.mytral
def test_component_time_conversion():
    """Test time conversion from seconds to hours."""
    # GIVEN
    component = settings.GearComponent(name="Fork", time_seconds=7200)

    # WHEN
    hours = component.time_hours

    # THEN
    assert hours == 2.0


@pytest.mark.mytral
def test_component_requires_service_km():
    """Test service requirement based on kilometers."""
    # GIVEN
    component = settings.GearComponent(
        name="Chain",
        next_service_km=500,
        distance_meters=550000,  # 550 km
        last_service_km=0.0,
    )

    # WHEN
    requires = component.requires_service_km

    # THEN
    assert requires is True
    assert component.km_since_service == 550.0


@pytest.mark.mytral
def test_component_requires_service_hours():
    """Test service requirement based on hours."""
    # GIVEN
    component = settings.GearComponent(
        name="Fork",
        next_service_hours=50,
        time_seconds=200000,  # ~55.5 hours
        last_service_hours=0.0,
    )

    # WHEN
    requires = component.requires_service_hours

    # THEN
    assert requires is True
    assert component.hours_since_service > 50


@pytest.mark.mytral
def test_component_requires_service_time():
    """Test service requirement based on time (months)."""
    # GIVEN
    past_date = (datetime.now() - timedelta(days=400)).date().isoformat()
    component = settings.GearComponent(
        name="Fork",
        installed_date=past_date,
        next_service_months=12,
    )

    # WHEN
    requires = component.requires_service_time

    # THEN
    assert requires is True


@pytest.mark.mytral
def test_component_service_progress_km():
    """Test service progress calculation for km."""
    # GIVEN
    component = settings.GearComponent(
        name="Chain",
        next_service_km=500,
        distance_meters=250000,  # 250 km
        last_service_km=0.0,
    )

    # WHEN
    progress = component.service_progress_km

    # THEN
    assert progress == 0.5  # 50%


@pytest.mark.mytral
def test_component_service_progress_hours():
    """Test service progress calculation for hours."""
    # GIVEN
    component = settings.GearComponent(
        name="Fork",
        next_service_hours=50,
        time_seconds=90000,  # 25 hours
        last_service_hours=0.0,
    )

    # WHEN
    progress = component.service_progress_hours

    # THEN
    assert progress == 0.5  # 50%


@pytest.mark.mytral
def test_component_retired_no_service():
    """Test that retired components don't require service."""
    # GIVEN
    component = settings.GearComponent(
        name="Old Chain",
        next_service_km=500,
        distance_meters=600000,  # 600 km - over service
        status="retired",
    )

    # WHEN
    requires = component.requires_service

    # THEN
    assert requires is False


@pytest.mark.mytral
def test_component_to_dict_from_dict():
    """Test serialization and deserialization."""
    # GIVEN
    component = settings.GearComponent(
        name="Chain",
        cost=45.0,
        installed_date="2024-01-15",
        next_service_km=500,
        distance_meters=250000,
        time_seconds=30000,
        status="active",
        notes="SRAM XX1",
    )

    # WHEN
    data = component.to_dict()
    restored = settings.GearComponent.from_dict(data)

    # THEN
    assert restored.name == component.name
    assert restored.cost == component.cost
    assert restored.installed_date == component.installed_date
    assert restored.next_service_km == component.next_service_km
    assert restored.distance_meters == component.distance_meters
    assert restored.time_seconds == component.time_seconds
    assert restored.status == component.status
    assert restored.notes == component.notes
    assert restored.key == component.key


@pytest.mark.mytral
def test_component_replacement_chain():
    """Test replacement chain linking."""
    # GIVEN
    old_component = settings.GearComponent(
        name="Old Chain",
        cost=40.0,
        status="retired",
        replaced_by_key="new-chain-key",
    )
    new_component = settings.GearComponent(
        name="New Chain",
        cost=45.0,
        status="active",
        replaces_key=old_component.key,
        key="new-chain-key",
    )

    # WHEN / THEN
    assert old_component.replaced_by_key == new_component.key
    assert new_component.replaces_key == old_component.key
    assert old_component.status == "retired"
    assert new_component.status == "active"


@pytest.mark.mytral
def test_component_multiple_service_intervals():
    """Test component with multiple service intervals."""
    # GIVEN
    past_date = (datetime.now() - timedelta(days=400)).date().isoformat()
    component = settings.GearComponent(
        name="Fork",
        installed_date=past_date,
        next_service_km=1000,
        next_service_hours=50,
        next_service_months=12,
        distance_meters=500000,  # 500 km - not due yet
        time_seconds=180000,  # 50 hours - due
    )

    # WHEN / THEN
    assert component.requires_service_km is False
    assert component.requires_service_hours is True
    assert component.requires_service_time is True
    assert component.requires_service is True  # any one triggers
