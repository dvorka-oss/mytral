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

from mytral import commons
from mytral import settings as app_settings


@pytest.mark.mytral
def test_user_activity_types_bootstrap_covers_all_commons_activity_constants():
    # GIVEN
    bootstrap = app_settings.UserActivityTypes.bootstrap()
    bootstrap_keys = {activity_type.key for activity_type in bootstrap}
    commons_keys = {
        value
        for name, value in vars(commons).items()
        if name.startswith("AT_") and isinstance(value, str)
    }

    # WHEN
    missing_keys = commons_keys - bootstrap_keys
    extra_keys = bootstrap_keys - commons_keys

    # THEN
    assert missing_keys == set()
    assert extra_keys == set()
    print("DONE: bootstrap covers all commons AT_* constants")


@pytest.mark.mytral
def test_user_activity_types_bootstrap_flags_for_representative_activity_types():
    # GIVEN
    activity_types = app_settings.UserActivityTypes.bootstrap()
    by_key = {activity_type.key: activity_type for activity_type in activity_types}

    # WHEN
    workout = by_key[commons.AT_WORKOUT]
    triathlon = by_key[commons.AT_TRIATHLON]
    transition = by_key[commons.AT_TRANSITION]
    calisthenics = by_key[commons.AT_CALISTHENICS]
    comment = by_key[commons.AT_COMMENT]
    skiing = by_key[commons.AT_SKI_DOWNHILL]

    # THEN
    assert workout.is_exercise is True
    assert workout.is_distance is False
    assert triathlon.is_distance is True
    assert triathlon.is_exercise is False
    assert transition.is_meta is True
    assert calisthenics.is_exercise is True
    assert comment.is_meta is True
    assert skiing.is_distance is False
    assert skiing.is_exercise is False
    print("DONE: representative bootstrap flags are correct")


@pytest.mark.mytral
def test_activity_type_serializes_meta_activity_type():
    # GIVEN
    activity_type = app_settings.ActivityType(
        name="Roller ski skate",
        is_distance=True,
        is_exercise=False,
        is_regen=False,
        is_meta=False,
        is_built_in=True,
        emoji="🎿",
        color="blue",
        meta_activity_type=commons.M_AT_SKI,
        key=commons.AT_RS_F,
    )

    # WHEN
    data = activity_type.to_dict()
    restored = app_settings.ActivityType.from_dict(data)

    # THEN
    assert data["meta_activity_type"] == commons.M_AT_SKI
    assert restored.meta_activity_type == commons.M_AT_SKI
    print("DONE: meta activity type round-trips through ActivityType")


@pytest.mark.mytral
def test_user_activity_types_bootstrap_assigns_meta_activity_type_from_taxonomy():
    # GIVEN
    activity_types = app_settings.UserActivityTypes.bootstrap()
    expected_meta_by_activity_key = {
        activity_type_key: meta_activity_type
        for meta_activity_type, taxonomy_activity_types in commons.AT_TAXONOMY.items()
        for activity_type_key in taxonomy_activity_types
    }

    # WHEN
    actual_meta_by_activity_key = {
        activity_type.key: activity_type.meta_activity_type
        for activity_type in activity_types
    }

    # THEN
    for activity_type in activity_types:
        assert actual_meta_by_activity_key[
            activity_type.key
        ] == expected_meta_by_activity_key.get(activity_type.key, "")
    print("DONE: bootstrap meta activity types follow commons taxonomy")


@pytest.mark.mytral
def test_user_activity_types_bootstrap_assigns_reasonable_muscle_groups():
    # GIVEN
    activity_types = app_settings.UserActivityTypes.bootstrap()
    by_key = {activity_type.key: activity_type for activity_type in activity_types}

    # WHEN
    run = by_key[commons.AT_RUN]
    row = by_key[commons.AT_ROW]
    workout = by_key[commons.AT_WORKOUT]
    sail = by_key[commons.AT_SAIL]
    sleep = by_key[commons.AT_SLEEP]
    comment = by_key[commons.AT_COMMENT]

    # THEN
    for activity_type in activity_types:
        assert activity_type.muscle_groups == app_settings.mg.validate_muscle_keys(
            activity_type.muscle_groups
        )
        assert (
            activity_type.muscle_groups_secondary
            == app_settings.mg.validate_muscle_keys(
                activity_type.muscle_groups_secondary
            )
        )

    assert run.muscle_groups == [
        "quads",
        "hamstrings",
        "glutes",
        "calves",
        "hip_flexors",
    ]
    assert row.muscle_groups_secondary == ["abs", "obliques", "lower_back", "quads"]
    assert "pecs" in workout.muscle_groups
    assert "forearms" in sail.muscle_groups
    assert sleep.muscle_groups == []
    assert comment.muscle_groups == []
    print("DONE: bootstrap assigns valid muscle groups where meaningful")
