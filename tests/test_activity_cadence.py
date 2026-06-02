# MyTraL: my trailing log
#
# Copyright (C) 2015-2026 Martin Dvorak <martin.dvorak@mindforger.com>
#
# This program is free software: you can redistribute it and/or modify
# it under the terms of the GNU General Public License as published by
# the Free Software Foundation, either version 3 of the License, or
# (at your option) any later version.
# This program is distributed in the hope that it will be useful,
# but WITHOUT ANY WARRANTY; without even the implied warranty of
# MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the
# GNU General Public License for more details.
#
# You should have received a copy of the GNU General Public License
# along with this program. If not, see <http://www.gnu.org/licenses/>.
import dataclasses
import pathlib

import pytest

from mytral import config
from mytral.backends import entities
from tests import _given


@pytest.mark.mytral
def test_activity_entity_cadence_defaults():
    """ActivityEntity has zero cadence fields by default."""
    #
    # GIVEN / WHEN
    #
    activity = entities.ActivityEntity()

    #
    # THEN
    #
    assert activity.avg_cadence == 0, "avg_cadence should default to 0"
    assert activity.max_cadence == 0, "max_cadence should default to 0"

    print("DONE: avg_cadence and max_cadence default to 0")


@pytest.mark.mytral
def test_activity_entity_cadence_assignment():
    """ActivityEntity stores avg_cadence and max_cadence correctly."""
    #
    # GIVEN
    #
    activity = entities.ActivityEntity()

    #
    # WHEN
    #
    activity.avg_cadence = 88
    activity.max_cadence = 105

    #
    # THEN
    #
    assert activity.avg_cadence == 88
    assert activity.max_cadence == 105

    print(
        f"DONE: avg_cadence={activity.avg_cadence}, max_cadence={activity.max_cadence}"
    )


@pytest.mark.mytral
def test_activity_entity_cadence_json_round_trip(tmp_path: pathlib.Path):
    """avg_cadence and max_cadence survive a JSON persistence round-trip."""
    #
    # GIVEN
    #
    from mytral import commons

    ds, user_ds, profile = _given.given_test(
        config.MytralConfig(persistence_data_dir=tmp_path),
        user_id="cadence_test_user",
    )
    user_id = profile.user_id
    dataset_name = commons.DS_LIFELONG

    activity = entities.ActivityEntity(
        name="Morning Ride",
        activity_type_key="cycling",
        avg_cadence=92,
        max_cadence=118,
        avg_watts=220.0,
        avg_hr=155,
    )

    #
    # WHEN
    #
    created = user_ds.create_activity(
        user_id=user_id, dataset_name=dataset_name, entity=activity
    )
    restored = user_ds.get_activity(
        user_id=user_id, dataset_name=dataset_name, key=created.key
    )

    #
    # THEN
    #
    assert restored is not None, "Activity not found after save"
    assert restored.avg_cadence == 92, (
        f"Expected avg_cadence=92, got {restored.avg_cadence}"
    )
    assert restored.max_cadence == 118, (
        f"Expected max_cadence=118, got {restored.max_cadence}"
    )

    print(
        f"DONE: round-trip avg_cadence={restored.avg_cadence},"
        f" max_cadence={restored.max_cadence}"
    )


@pytest.mark.mytral
def test_activity_entity_cadence_asdict():
    """dataclasses.asdict includes avg_cadence and max_cadence keys."""
    #
    # GIVEN
    #
    activity = entities.ActivityEntity()
    activity.avg_cadence = 75
    activity.max_cadence = 95

    #
    # WHEN
    #
    d = dataclasses.asdict(activity)

    #
    # THEN
    #
    assert "avg_cadence" in d, "avg_cadence missing from serialised dict"
    assert "max_cadence" in d, "max_cadence missing from serialised dict"
    assert d["avg_cadence"] == 75
    assert d["max_cadence"] == 95

    print(
        f"DONE: asdict avg_cadence={d['avg_cadence']}, max_cadence={d['max_cadence']}"
    )


@pytest.mark.mytral
def test_activity_entity_cadence_backward_compat_no_cadence_key():
    """Loading JSON without cadence keys falls back to default zero values."""
    #
    # GIVEN — simulate old JSON dict without cadence fields
    #
    old_dict: dict = {
        "key": "old-activity-1",
        "name": "Old Run",
        "activity_type_key": "run",
        "when_year": 2020,
        "when_month": 6,
        "when_day": 15,
        "when_hour": 8,
        "when_minute": 0,
        "when_second": 0,
        "hours": 0,
        "minutes": 45,
        "seconds": 0,
        "duration": 2700,
        "duration_seconds": 2700,
        "distance": 10000.0,
        "avg_speed": 13.3,
        "max_speed": 16.0,
        "elevation_gain": 50,
        "elevation_min": 200,
        "elevation_max": 250,
        "avg_watts": 0.0,
        "max_watts": 0.0,
        "avg_hr": 148,
        "max_hr": 172,
        "min_hr": 0,
        "kcal": 600,
        "weight": 0.0,
        "cost": 0.0,
        "weather": "",
        "temperature": 18,
        "fitness_score": 0.0,
        "src": "manual",
        "src_descriptor": "",
        "src_key": "",
        "src_url": "",
        "intensity": "easy",
        "commute": False,
        "ranked": False,
        "race": False,
        "warm_up": False,
        "cool_down": False,
        "sort_code": 0,
        "workout_sort_code": 0,
        "gears": [],
        "outfit": "",
        "exercises": [],
        "sickness_symptoms": [],
        "laps": [],
        "transient_fields": {},
    }

    #
    # WHEN
    #
    entity = entities.ActivityEntity(**old_dict)

    #
    # THEN
    #
    assert entity.avg_cadence == 0, (
        f"Expected avg_cadence=0 for old JSON, got {entity.avg_cadence}"
    )
    assert entity.max_cadence == 0, (
        f"Expected max_cadence=0 for old JSON, got {entity.max_cadence}"
    )

    print(
        "DONE: backward compat - avg_cadence and max_cadence default to 0"
        " when absent from old JSON"
    )


@pytest.mark.mytral
def test_strava_import_cadence_field_mapping():
    """Strava dataset_item 'average_cadence' is mapped to entity.avg_cadence."""
    #
    # GIVEN — verify that the field mapping is present in the integration code
    #
    import inspect

    from mytral.integrations import strava as strava_integration

    source = inspect.getsource(strava_integration.StravaActivityImportPlugin)

    #
    # WHEN / THEN
    #
    assert "average_cadence" in source, (
        "Strava integration does not reference 'average_cadence' field"
    )
    assert "avg_cadence" in source, (
        "Strava integration does not set 'avg_cadence' on entity"
    )

    print("DONE: Strava integration maps average_cadence to entity.avg_cadence")


@pytest.mark.mytral
def test_concept2_import_cadence_field_mapping():
    """Concept2 import maps 'Stroke Rate/Cadence' column to entity.avg_cadence."""
    #
    # GIVEN — verify that the field mapping is present in the integration code
    #
    import inspect

    from mytral.integrations import concept2 as concept2_integration

    source = inspect.getsource(concept2_integration.Concept2ActivitiesImportPlugin)

    #
    # WHEN / THEN
    #
    assert "Stroke Rate/Cadence" in source, (
        "Concept2 integration does not reference 'Stroke Rate/Cadence' column"
    )
    assert "avg_cadence" in source, (
        "Concept2 integration does not set 'avg_cadence' on entity"
    )

    print("DONE: Concept2 integration maps Stroke Rate/Cadence to entity.avg_cadence")
