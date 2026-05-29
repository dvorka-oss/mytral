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

"""Tests for component service interval calculation correctness.

Verifies that:
- km_since_service and hours_since_service are 0 when a component is first installed
- Usage accumulates correctly after installation
- km_at_service / hours_at_service in service history record usage since last
  service (or installation), NOT total gear mileage since purchase
- After a service event the counter resets and accumulates again correctly
- Replacement history entries record km/h since last service, not all-time gear km
"""

import functools
from unittest.mock import MagicMock

import pytest

from mytral import settings
from mytral.backends import dataset
from mytral.backends import entities

#
# GearComponent unit tests
#


@pytest.mark.mytral
def test_new_component_km_since_service_is_zero_when_last_service_km_matches():
    """Newly installed component should have km_since_service == 0."""
    # GIVEN - component installed on a bike that already has 5 000 km
    # last_service_km is set to the current gear km at installation time
    component = settings.GearComponent(
        name="Chain",
        next_service_km=500,
        distance_meters=5_000_000,  # gear has 5 000 km total
        last_service_km=5_000.0,  # baseline set to current gear km at install
    )

    # WHEN
    km_since = component.km_since_service

    # THEN - DONE: usage since installation is 0, not 5 000
    assert km_since == 0.0


@pytest.mark.mytral
def test_component_usage_accumulates_after_installation():
    """Usage should accumulate only from the installation baseline."""
    # GIVEN - component installed at 5 000 km, gear now at 5 300 km
    component = settings.GearComponent(
        name="Chain",
        next_service_km=500,
        distance_meters=5_300_000,  # gear now at 5 300 km
        last_service_km=5_000.0,  # baseline at installation
    )

    # WHEN
    km_since = component.km_since_service

    # THEN - DONE: only 300 km accumulated since installation
    assert km_since == pytest.approx(300.0)


@pytest.mark.mytral
def test_component_service_not_due_below_interval():
    """Service should not be required when km_since_service < next_service_km."""
    # GIVEN - component installed at 5 000 km, accumulated 300 km, interval 500
    component = settings.GearComponent(
        name="Chain",
        next_service_km=500,
        distance_meters=5_300_000,
        last_service_km=5_000.0,
    )

    # WHEN
    requires = component.requires_service_km

    # THEN - DONE: 300 km < 500 km interval, no service needed
    assert requires is False


@pytest.mark.mytral
def test_component_service_due_after_interval_from_installation():
    """Service should be required once km_since_service >= next_service_km."""
    # GIVEN - component installed at 5 000 km, accumulated 550 km, interval 500
    component = settings.GearComponent(
        name="Chain",
        next_service_km=500,
        distance_meters=5_550_000,  # gear at 5 550 km
        last_service_km=5_000.0,  # installed at 5 000 km
    )

    # WHEN
    requires = component.requires_service_km
    km_since = component.km_since_service

    # THEN - DONE: 550 km >= 500 km interval, service is due
    assert km_since == pytest.approx(550.0)
    assert requires is True


@pytest.mark.mytral
def test_km_since_service_resets_after_service():
    """After recording a service the km counter should reset to zero."""
    # GIVEN - component serviced; last_service_km updated to current distance
    # (simulating what the service recording code does after a service event)
    distance_km_at_service = 5_550.0
    component = settings.GearComponent(
        name="Chain",
        next_service_km=500,
        distance_meters=int(distance_km_at_service * 1000),
        last_service_km=distance_km_at_service,  # reset after service
    )

    # WHEN
    km_since = component.km_since_service

    # THEN - DONE: counter is zero right after a service
    assert km_since == 0.0


@pytest.mark.mytral
def test_second_service_interval_accumulates_from_previous_service():
    """Between the 2nd and 3rd service only km since 2nd service should count."""
    # GIVEN - 1st service at 5 550 km, gear now at 5 900 km
    component = settings.GearComponent(
        name="Chain",
        next_service_km=500,
        distance_meters=5_900_000,  # gear at 5 900 km
        last_service_km=5_550.0,  # last service was at 5 550 km
    )

    # WHEN
    km_since = component.km_since_service

    # THEN - DONE: 350 km accumulated since last service, not 900 km
    assert km_since == pytest.approx(350.0)


#
# ComponentServiceHistoryEntry -- km_at_service semantics
#


@pytest.mark.mytral
def test_service_history_entry_stores_km_since_service_not_total():
    """km_at_service must store km since last service, not total gear mileage."""
    # GIVEN - component installed at 5 000 km, first service at 5 550 km
    component = settings.GearComponent(
        name="Chain",
        next_service_km=500,
        distance_meters=5_550_000,  # gear total at service time
        last_service_km=5_000.0,  # installation baseline
    )

    # WHEN - simulate what the service recording code should do
    entry = settings.ComponentServiceHistoryEntry(
        date="2025-06-01",
        km_at_service=component.km_since_service,  # CORRECT: 550 km
        hours_at_service=component.hours_since_service,
        service_type="service",
    )

    # THEN - DONE: 550 km stored, not the total 5 550 km
    assert entry.km_at_service == pytest.approx(550.0)
    assert entry.km_at_service != pytest.approx(5_550.0)


@pytest.mark.mytral
def test_service_history_entry_hours_since_service():
    """hours_at_service must store hours since last service, not total gear hours."""
    # GIVEN - component installed at 100 h, first service at 160 h
    component = settings.GearComponent(
        name="Fork",
        next_service_hours=50,
        time_seconds=160 * 3600,  # gear at 160 h total
        last_service_hours=100.0,  # installation baseline (100 h)
    )

    # WHEN
    entry = settings.ComponentServiceHistoryEntry(
        date="2025-06-01",
        km_at_service=component.km_since_service,
        hours_at_service=component.hours_since_service,  # CORRECT: 60 h
        service_type="service",
    )

    # THEN - DONE: 60 h stored, not the total 160 h
    assert entry.hours_at_service == pytest.approx(60.0)
    assert entry.hours_at_service != pytest.approx(160.0)


#
# Gear.recalculate_component_usage_from_gear_stats (baseline init)
#


@pytest.mark.mytral
def test_new_component_on_existing_gear_baseline_should_equal_gear_km():
    """
    When a component is added to a gear that already has mileage, its
    last_service_km must be set to current gear km so km_since_service == 0.
    """
    # GIVEN - gear already has 5 000 km; new component added with baseline set
    component_dict = {
        "key": "new-chain-key",
        "name": "Chain",
        "cost": 45.0,
        "installed_date": "2025-01-01",
        "last_service_km": 5_000.0,  # set by component creation code
        "last_service_hours": 200.0,
        "next_service_km": 500,
        "next_service_hours": None,
        "next_service_months": None,
        "distance_meters": 5_000_000,  # set by recalculate_component_usage
        "time_seconds": 200 * 3600,
        "status": "active",
        "replaced_by_key": "",
        "replaces_key": "",
        "notes": "",
    }

    gear = settings.Gear(
        activity_type_key="cycling",
        name="Mountain Bike",
        components=[component_dict],
    )

    # WHEN
    chain = gear.get_components()[0]
    km_since = chain.km_since_service
    hours_since = chain.hours_since_service

    # THEN - DONE: component starts fresh at 0 usage
    assert km_since == 0.0
    assert hours_since == 0.0


@pytest.mark.mytral
def test_component_started_at_gear_purchase_has_zero_baseline():
    """Component installed at gear purchase (0 km) needs no special baseline."""
    # GIVEN - brand new gear and component, both start at 0 km
    component_dict = {
        "key": "chain-key",
        "name": "Chain",
        "cost": 45.0,
        "installed_date": "2025-01-01",
        "last_service_km": 0.0,  # installed at gear purchase: baseline = 0
        "last_service_hours": 0.0,
        "next_service_km": 500,
        "next_service_hours": None,
        "next_service_months": None,
        "distance_meters": 0,
        "time_seconds": 0,
        "status": "active",
        "replaced_by_key": "",
        "replaces_key": "",
        "notes": "",
    }

    gear = settings.Gear(
        activity_type_key="cycling", name="Mountain Bike", components=[component_dict]
    )

    # WHEN
    chain = gear.get_components()[0]
    km_since = chain.km_since_service

    # THEN - DONE: zero usage, no baseline adjustment needed
    assert km_since == 0.0


#
# Replacement history entry semantics
#


@pytest.mark.mytral
def test_replacement_entry_stores_km_since_installation_not_total():
    """
    When a component is replaced (retired by a new component), the auto-created
    replacement history entry must store km since installation, not all-time gear km.
    """
    # GIVEN - chain installed at 5 000 km; gear is now at 5 700 km (700 km ridden)
    old_chain = settings.GearComponent(
        name="Old Chain",
        next_service_km=500,
        distance_meters=5_700_000,  # gear total at replacement time
        last_service_km=5_000.0,  # installation baseline
        last_service_hours=200.0,
        time_seconds=228 * 3600,  # gear at 228 h total; 28 h since install
        status="active",
    )

    # WHEN - simulate what the replacement auto-creation code does
    replacement_entry = settings.ComponentServiceHistoryEntry(
        date="2025-09-01",
        km_at_service=old_chain.km_since_service,
        hours_at_service=old_chain.hours_since_service,
        service_type="replacement",
    )

    # THEN - DONE: 700 km stored, not the total 5 700 km
    assert replacement_entry.km_at_service == pytest.approx(700.0)
    assert replacement_entry.km_at_service != pytest.approx(5_700.0)
    assert replacement_entry.hours_at_service == pytest.approx(28.0)
    assert replacement_entry.hours_at_service != pytest.approx(228.0)


@pytest.mark.mytral
def test_replacement_entry_after_intermediate_service():
    """
    If a component was serviced once before being replaced, the replacement entry
    should record km/h since the last service, not since installation.
    """
    # GIVEN - chain installed at 5 000 km, serviced at 5 550 km (550 km), then
    # replaced at 5 900 km.  km_since_service should be 5 900 - 5 550 = 350 km.
    old_chain = settings.GearComponent(
        name="Old Chain",
        next_service_km=500,
        distance_meters=5_900_000,  # gear total at replacement
        last_service_km=5_550.0,  # reset at the intermediate service
        time_seconds=0,
        last_service_hours=0.0,
        status="active",
    )

    # WHEN
    replacement_entry = settings.ComponentServiceHistoryEntry(
        date="2025-10-01",
        km_at_service=old_chain.km_since_service,
        hours_at_service=old_chain.hours_since_service,
        service_type="replacement",
    )

    # THEN - DONE: 350 km since last service, not 900 km from gear beginning
    assert replacement_entry.km_at_service == pytest.approx(350.0)
    assert replacement_entry.km_at_service != pytest.approx(5_900.0)


@pytest.mark.mytral
def test_replacement_entry_for_component_installed_at_gear_purchase():
    """Component installed at gear purchase (last_service_km=0);
    replacement at 800 km.
    """
    # GIVEN
    old_chain = settings.GearComponent(
        name="Stock Chain",
        distance_meters=800_000,  # 800 km total
        last_service_km=0.0,  # installed at gear purchase
        time_seconds=40 * 3600,
        last_service_hours=0.0,
        status="active",
    )

    # WHEN
    replacement_entry = settings.ComponentServiceHistoryEntry(
        date="2025-11-01",
        km_at_service=old_chain.km_since_service,
        hours_at_service=old_chain.hours_since_service,
        service_type="replacement",
    )

    # THEN - DONE: full 800 km since purchase/install is correct here
    assert replacement_entry.km_at_service == pytest.approx(800.0)
    assert replacement_entry.hours_at_service == pytest.approx(40.0)


#
# gear_km_at_date: activity-based cumulative usage computation
#


@pytest.mark.mytral
def test_gear_km_at_date_sums_activities_up_to_date():
    """gear_km_at_date should return cumulative km/hours from activities up to (and
    including) the given date, ignoring later activities."""
    # GIVEN - fake dataset with 4 activities on gear G1 across three dates
    from unittest.mock import MagicMock

    from mytral.backends.entities import ActivityEntity

    def _make_activity(when: str, dist_m: int, dur_s: int, gears: list[str]):
        a = ActivityEntity()
        a.when = when
        a.distance = dist_m
        a.duration_seconds = dur_s
        a.gears = gears
        return a

    activities = {
        "a1": _make_activity("2021-01-01 08:00:00", 20_000, 3_600, ["G1"]),
        "a2": _make_activity("2021-06-15 09:00:00", 30_000, 5_400, ["G1"]),
        "a3": _make_activity("2022-03-10 10:00:00", 25_000, 4_500, ["G1"]),
        "a4": _make_activity(
            "2022-03-10 11:00:00", 10_000, 1_800, ["G2"]
        ),  # other gear
    }

    ds = MagicMock()
    ds.all_activities.return_value = activities

    # WHEN - compute cumulative usage up to 2021-12-31 (exclude 2022 and G2 activities)
    km, h = dataset.UserDataset.gear_km_at_date(
        ds,
        user_id="u1",
        dataset_name="dev",
        gear_key="G1",
        iso_date="2021-12-31",
    )

    # THEN - DONE: a1 (20 km, 1 h) + a2 (30 km, 1.5 h) = 50 km, 2.5 h
    assert km == pytest.approx(50.0)
    assert h == pytest.approx(2.5)


@pytest.mark.mytral
def test_gear_km_at_date_includes_boundary_date():
    """Activities on exactly the cutoff date should be included."""
    # GIVEN
    a = entities.ActivityEntity()
    a.when = "2022-03-10 10:00:00"
    a.distance = 25_000
    a.duration_seconds = 3_600
    a.gears = ["G1"]

    ds = MagicMock()
    ds.all_activities.return_value = {"a1": a}

    # WHEN

    km, h = dataset.UserDataset.gear_km_at_date(
        ds,
        user_id="u1",
        dataset_name="dev",
        gear_key="G1",
        iso_date="2022-03-10",
    )

    # THEN - DONE: activity is on the boundary date and must be counted
    assert km == pytest.approx(25.0)
    assert h == pytest.approx(1.0)


@pytest.mark.mytral
def test_gear_km_at_date_slash_when_format():
    """Activities stored with YYYY/MM/DD when format should be handled correctly."""
    # GIVEN - old-style slash-separated date format used by Strava imports
    a = entities.ActivityEntity()
    a.when = "2021/04/03 07:00:00"  # slash format
    a.distance = 50_000
    a.duration_seconds = 7_200
    a.gears = ["G1"]

    ds = MagicMock()
    ds.all_activities.return_value = {"a1": a}

    # WHEN
    km, h = dataset.UserDataset.gear_km_at_date(
        ds,
        user_id="u1",
        dataset_name="dev",
        gear_key="G1",
        iso_date="2021-04-04",
    )

    # THEN - DONE: 2021/04/03 <= 2021-04-04 so the activity is included
    assert km == pytest.approx(50.0)
    assert h == pytest.approx(2.0)


#
# recompute_gear_service_intervals: full in-memory recalculation
#


@pytest.mark.mytral
def test_recompute_gear_service_intervals_fixes_history_entries():
    """recompute_gear_service_intervals should overwrite stored km_at_service
    with values derived from activity records, correctly computing per-interval
    deltas even when the stored snapshot was stale."""
    # GIVEN - a gear with 3 rides and 2 service events, all km snapshots wrong (stale)

    def _ride(when: str, dist_m: int, dur_s: int):
        a = entities.ActivityEntity()
        a.when = when
        a.distance = dist_m
        a.duration_seconds = dur_s
        a.gears = ["G1"]
        return a

    activities = {
        "r1": _ride("2022-01-10 08:00:00", 50_000, 7_200),  # 50 km, 2 h
        "r2": _ride("2022-06-15 09:00:00", 30_000, 3_600),  # 30 km, 1 h
        "r3": _ride("2022-11-20 10:00:00", 20_000, 1_800),  # 20 km, 0.5 h
    }

    ds = MagicMock()
    ds.all_activities.return_value = activities

    # stale component data: all distances set to total gear km (wrong snapshot)
    gear = settings.Gear(
        activity_type_key="cycling",
        name="Test Bike",
        components=[
            {
                "key": "C1",
                "name": "Chain",
                "cost": 0.0,
                "installed_date": "2022-01-01",
                "last_service_km": 100.0,  # stale
                "last_service_hours": 11.0,  # stale
                "last_service_date": "",
                "next_service_km": 500,
                "next_service_hours": None,
                "next_service_months": None,
                "distance_meters": 100_000,  # stale: all-time total
                "time_seconds": 39_600,  # stale: all-time total
                "status": "active",
                "replaced_by_key": "",
                "replaces_key": "",
                "notes": "",
            }
        ],
    )
    gear.key = "G1"
    # two history entries with stale km values
    gear.component_history = {
        "C1": [
            {
                "date": "2022-01-15",
                "km_at_service": 100.0,
                "hours_at_service": 11.0,
                "service_type": "service",
                "cost": 0,
                "notes": "",
            },
            {
                "date": "2022-07-01",
                "km_at_service": 100.0,
                "hours_at_service": 11.0,
                "service_type": "service",
                "cost": 0,
                "notes": "",
            },
        ]
    }
    # wire gear_km_at_date on the mock to the real implementation so it uses
    # the mocked all_activities, which is the production computation path

    ds.gear_km_at_date = functools.partial(dataset.UserDataset.gear_km_at_date, ds)

    # WHEN
    dataset.UserDataset.recompute_gear_service_intervals(
        ds,
        user_id="u1",
        dataset_name="dev",
        gear=gear,
    )

    history = gear.component_history["C1"]
    entry_jan = next(e for e in history if e["date"] == "2022-01-15")
    entry_jul = next(e for e in history if e["date"] == "2022-07-01")
    chain = gear.get_components()[0]

    # THEN - DONE:
    # first interval: install(2022-01-01)..2022-01-15 => only r1 (50 km)
    assert entry_jan["km_at_service"] == pytest.approx(50.0)
    assert entry_jan["hours_at_service"] == pytest.approx(2.0)

    # THEN - DONE:
    # second interval: 2022-01-15..2022-07-01 => only r2 (30 km)
    assert entry_jul["km_at_service"] == pytest.approx(30.0)
    assert entry_jul["hours_at_service"] == pytest.approx(1.0)

    # THEN - DONE:
    # current km_since_service: last service 2022-07-01 => r3 still pending = 20 km
    assert chain.km_since_service == pytest.approx(20.0)
    assert chain.hours_since_service == pytest.approx(0.5)
