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
import pathlib

import pytest

from mytral import commons
from mytral import config
from mytral import loggers
from mytral import persistences
from mytral import settings
from mytral.backends import dataset
from mytral.backends import entities
from mytral.backends.datasets import dataset_json


@pytest.mark.mytral
def test_normalize_dict_or_list_to_dict():
    """Test backward compatibility helper function."""
    #
    # GIVEN
    #

    # Old format (dict)
    old_format = {
        "uuid-1": {"key": "uuid-1", "name": "Item 1"},
        "uuid-2": {"key": "uuid-2", "name": "Item 2"},
    }

    # New format (list)
    new_format = [
        {"key": "uuid-1", "name": "Item 1"},
        {"key": "uuid-2", "name": "Item 2"},
    ]

    # Empty formats
    empty_dict = {}
    empty_list = []

    #
    # WHEN
    #

    result_from_dict = persistences.normalize_dict_or_list_to_dict(old_format)
    result_from_list = persistences.normalize_dict_or_list_to_dict(new_format)
    result_from_empty_dict = persistences.normalize_dict_or_list_to_dict(empty_dict)
    result_from_empty_list = persistences.normalize_dict_or_list_to_dict(empty_list)

    #
    # THEN
    #

    # Both should produce the same dict structure
    assert isinstance(result_from_dict, dict)
    assert isinstance(result_from_list, dict)
    assert len(result_from_dict) == 2
    assert len(result_from_list) == 2
    assert result_from_dict["uuid-1"]["name"] == "Item 1"
    assert result_from_list["uuid-1"]["name"] == "Item 1"

    # Empty data should produce empty dict
    assert isinstance(result_from_empty_dict, dict)
    assert isinstance(result_from_empty_list, dict)
    assert len(result_from_empty_dict) == 0
    assert len(result_from_empty_list) == 0


@pytest.mark.mytral
def test_user_exercises_backward_compatibility():
    """Test UserExercises can load old dict format and save new list format."""
    #
    # GIVEN
    #

    # Old format (dict)
    old_format = {
        "ex-1": {"key": "ex-1", "name": "Push-up", "description": "", "weight": 0.0},
        "ex-2": {"key": "ex-2", "name": "Pull-up", "description": "", "weight": 0.0},
    }

    #
    # WHEN
    #

    # Load from old format
    exercises = settings.UserExercises.from_dict_dict(old_format)

    # Save to new format
    new_format = exercises.to_dict_dict()

    #
    # THEN
    #

    assert isinstance(new_format, list)
    assert len(new_format) == 2
    # Verify all entries have 'key' attribute
    for entry in new_format:
        assert "key" in entry
        assert "name" in entry


@pytest.mark.mytral
def test_user_exercises_new_format():
    """Test UserExercises can load new list format."""
    #
    # GIVEN
    #

    # New format (list)
    new_format = [
        {"key": "ex-1", "name": "Push-up", "description": "", "weight": 0.0},
        {"key": "ex-2", "name": "Pull-up", "description": "", "weight": 0.0},
    ]

    #
    # WHEN
    #

    exercises = settings.UserExercises.from_dict_dict(new_format)

    #
    # THEN
    #

    assert len(exercises.exercise_by_key) == 2
    assert exercises.exists("ex-1")
    assert exercises.exists("ex-2")


@pytest.mark.mytral
def test_user_gear_backward_compatibility():
    """Test UserGear can load old dict format and save new list format."""
    #
    # GIVEN
    #

    # Old format (dict)
    old_format = {
        "gear-1": {
            "key": "gear-1",
            "name": "Running Shoes",
            "activity_type_key": "run",
            "vendor": "Nike",
            "model": "Pegasus",
            "size": "42",
            "url": "",
            "comment": "",
            "is_default": False,
            "retired": False,
            "tcoo_base": 0.0,
            "tcoo_additional": 0.0,
            "components": [],
            "component_history": {},
        },
    }

    #
    # WHEN
    #

    gear = settings.UserGear.from_dict_dict(old_format)
    new_format = gear.to_dict_dict()

    #
    # THEN
    #

    assert isinstance(new_format, list)
    assert len(new_format) == 1
    assert new_format[0]["key"] == "gear-1"


@pytest.mark.mytral
def test_user_symptoms_backward_compatibility():
    """Test UserSymptoms can load old dict format and save new list format."""
    #
    # GIVEN
    #

    # Old format (dict)
    old_format = {
        "sym-1": {"key": "sym-1", "name": "Cold"},
        "sym-2": {"key": "sym-2", "name": "Fever"},
    }

    #
    # WHEN
    #

    symptoms = settings.UserSymptoms.from_dict_dict(old_format)
    new_format = symptoms.to_dict_dict()

    #
    # THEN
    #

    assert isinstance(new_format, list)
    assert len(new_format) == 2


@pytest.mark.mytral
def test_user_laps_backward_compatibility():
    """Test UserLaps can load old dict format and save new list format."""
    #
    # GIVEN
    #

    # Old format (dict)
    old_format = {
        "lap-1": {
            "key": "lap-1",
            "name": "400m",
            "description": "",
            "default_distance": 400,
            "default_duration": 0,
        },
    }

    #
    # WHEN
    #

    laps = settings.UserLaps.from_dict_dict(old_format)
    new_format = laps.to_dict_dict()

    #
    # THEN
    #

    assert isinstance(new_format, list)
    assert len(new_format) == 1


@pytest.mark.mytral
def test_user_activity_types_backward_compatibility():
    """Test UserActivityTypes can load old dict format and save new list format."""
    #
    # GIVEN
    #

    # Old format (dict)
    old_format = {
        "run": {
            "key": "run",
            "name": "Run",
            "is_distance": True,
            "is_exercise": False,
            "is_regen": False,
            "is_built_in": True,
            "emoji": "🏃",
            "color": "w3-brown",
        },
    }

    #
    # WHEN
    #

    activity_types = settings.UserActivityTypes.from_dict_dict(old_format)
    new_format = activity_types.to_dict_dict()

    #
    # THEN
    #

    assert isinstance(new_format, list)
    assert len(new_format) == 1


@pytest.mark.mytral
def test_activities_backward_compatibility():
    """Test activities can load old dict format and save new list format."""
    #
    # GIVEN
    #

    # Old format (dict)
    old_format = {
        "act-1": {
            "key": "act-1",
            "when_year": 2025,
            "when_month": 1,
            "when_day": 1,
            "when_hour": 8,
            "when_minute": 0,
            "when_second": 0,
            "distance": 5000,
            "hours": 0,
            "minutes": 30,
            "seconds": 0,
            "exercises": [],
            "sickness_symptoms": [],
            "laps": [],
            "gears": [],
        },
    }

    #
    # WHEN
    #

    activities = dataset_json.JSONUserActivitiesDataset._ddict_2_dict(old_format)

    #
    # THEN
    #

    assert isinstance(activities, dict)
    assert len(activities) == 1
    assert "act-1" in activities


@pytest.mark.mytral
def test_activities_new_format():
    """Test activities can load new list format."""
    #
    # GIVEN
    #

    # New format (list)
    new_format = [
        {
            "key": "act-1",
            "when_year": 2025,
            "when_month": 1,
            "when_day": 1,
            "when_hour": 8,
            "when_minute": 0,
            "when_second": 0,
            "distance": 5000,
            "hours": 0,
            "minutes": 30,
            "seconds": 0,
            "exercises": [],
            "sickness_symptoms": [],
            "laps": [],
            "gears": [],
        },
    ]

    #
    # WHEN
    #

    activities = dataset_json.JSONUserActivitiesDataset._ddict_2_dict(new_format)

    #
    # THEN
    #

    assert isinstance(activities, dict)
    assert len(activities) == 1
    assert "act-1" in activities


@pytest.mark.mytral
def test_activities_legacy_recording_blob_keys_migrated():
    """Test legacy FIT/GPX blob keys are migrated to recording entries."""
    #
    # GIVEN
    #
    old_format = {
        "act-1": {
            "key": "act-1",
            "when_year": 2025,
            "when_month": 1,
            "when_day": 1,
            "when_hour": 8,
            "when_minute": 0,
            "when_second": 0,
            "distance": 5000,
            "hours": 0,
            "minutes": 30,
            "seconds": 0,
            "gpx_blob_key": "gpx-uuid-1",
            "fit_blob_key": "fit-uuid-2",
            "exercises": [],
            "sickness_symptoms": [],
            "laps": [],
            "gears": [],
        },
    }

    #
    # WHEN
    #
    activities = dataset_json.JSONUserActivitiesDataset._ddict_2_dict(old_format)
    entity = activities["act-1"]

    #
    # THEN
    #
    assert isinstance(activities, dict)
    assert "act-1" in activities
    assert "gpx-uuid-1.gpx" in entity.recorded_blob_keys
    assert "fit-uuid-2.fit" in entity.recorded_blob_keys
    assert len(entity.recorded_blob_keys) == 2


@pytest.mark.parametrize(
    "activity,expected_ds_name",
    [
        (
            entities.ActivityEntity(
                when_year=2025,
            ),
            "activities-2025",
        )
    ],
)
@pytest.mark.mytral
def test_ds_name_for_activity(activity: entities.ActivityEntity, expected_ds_name: str):
    #
    # GIVEN
    #

    #
    # WHEN
    #
    actual_ds_name = dataset_json.JSONUserActivitiesDataset._ds_name_for_activity(
        dataset_name=commons.DS_LIFELONG, entity=activity
    )

    #
    # THEN
    #
    assert expected_ds_name == actual_ds_name


@pytest.mark.mytral
def test_json_dataset(tmp_path: pathlib.Path):
    """Test creation and use of the JSON user dataset on the filesystem."""
    #
    # GIVEN
    #

    linux_local_data_dir = tmp_path / ".local"

    #
    # WHEN
    #

    mytral_config = config.MytralConfig(
        persistence_type=config.PersistenceType.FILESYSTEM,
        persistence_data_dir=linux_local_data_dir,
    )

    ds = dataset.MyTraLDataset(
        mytral_config=mytral_config, logger=loggers.MytralPrintLogger()
    )

    #
    # THEN
    #
    assert ds
