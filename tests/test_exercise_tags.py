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
import pytest

from mytral import settings


@pytest.mark.mytral
def test_exercise_with_tags():
    # GIVEN
    exercise = settings.Exercise(
        name="Bench Press",
        description="Chest exercise",
        weight=80.0,
        tags=["upper body", "strength", "compound"],
    )

    # WHEN
    exercise_dict = exercise.to_dict()

    # THEN
    assert exercise.name == "Bench Press"
    assert exercise.description == "Chest exercise"
    assert exercise.weight == 80.0
    assert exercise.tags == ["upper body", "strength", "compound"]
    assert len(exercise.tags) == 3
    assert "upper body" in exercise.tags
    assert "strength" in exercise.tags
    assert "compound" in exercise.tags
    assert exercise_dict["tags"] == ["upper body", "strength", "compound"]

    print(f"DONE: Exercise '{exercise.name}' has {len(exercise.tags)} tags")


@pytest.mark.mytral
def test_exercise_without_tags():
    # GIVEN
    exercise = settings.Exercise(
        name="Squat",
        description="Leg exercise",
        weight=100.0,
    )

    # WHEN
    exercise_dict = exercise.to_dict()

    # THEN
    assert exercise.name == "Squat"
    assert exercise.tags == []
    assert len(exercise.tags) == 0
    assert exercise_dict["tags"] == []

    print(f"DONE: Exercise '{exercise.name}' has no tags")


@pytest.mark.mytral
def test_exercise_from_dict_with_tags():
    # GIVEN
    exercise_dict = {
        "key": "ex-1",
        "name": "Deadlift",
        "description": "Full body exercise",
        "weight": 120.0,
        "tags": ["lower body", "strength", "compound"],
    }

    # WHEN
    exercise = settings.Exercise.from_dict(exercise_dict)

    # THEN
    assert exercise.name == "Deadlift"
    assert exercise.description == "Full body exercise"
    assert exercise.weight == 120.0
    assert exercise.tags == ["lower body", "strength", "compound"]
    assert exercise.key == "ex-1"

    print(
        f"DONE: Exercise '{exercise.name}' loaded from dict with "
        f"{len(exercise.tags)} tags"
    )


@pytest.mark.mytral
def test_exercise_from_dict_without_tags():
    # GIVEN
    exercise_dict = {
        "key": "ex-2",
        "name": "Plank",
        "description": "Core exercise",
        "weight": 0.0,
    }

    # WHEN
    exercise = settings.Exercise.from_dict(exercise_dict)

    # THEN
    assert exercise.name == "Plank"
    assert exercise.description == "Core exercise"
    assert exercise.weight == 0.0
    assert exercise.tags == []
    assert exercise.key == "ex-2"

    print(f"DONE: Exercise '{exercise.name}' loaded from dict without tags field")


@pytest.mark.mytral
def test_exercise_tags_with_spaces():
    # GIVEN
    exercise = settings.Exercise(
        name="Shoulder Press",
        description="Shoulder exercise",
        weight=50.0,
        tags=["upper body", "shoulder work", "overhead pressing"],
    )

    # WHEN
    exercise_dict = exercise.to_dict()

    # THEN
    print("Exercise tags: ", exercise_dict["tags"])
    assert "upper body" in exercise.tags
    assert "shoulder work" in exercise.tags
    assert "overhead pressing" in exercise.tags

    print("DONE: Exercise supports tags with spaces")


@pytest.mark.mytral
def test_exercise_roundtrip_with_tags():
    # GIVEN
    original = settings.Exercise(
        name="Pull-up",
        description="Back exercise",
        weight=0.0,
        tags=["upper body", "back", "bodyweight"],
    )

    # WHEN
    dict_form = original.to_dict()
    restored = settings.Exercise.from_dict(dict_form)

    # THEN
    assert original.name == restored.name
    assert original.description == restored.description
    assert original.weight == restored.weight
    assert original.tags == restored.tags
    assert original.key == restored.key

    print("DONE: Exercise roundtrip preserves tags")
