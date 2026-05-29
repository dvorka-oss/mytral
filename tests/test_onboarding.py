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

from mytral import onboarding as ob
from mytral import settings


@pytest.mark.mytral
def test_default_onboarding_state():
    # GIVEN: default state
    state = ob.get_default_onboarding_state()

    # WHEN: inspecting state
    # THEN: all items should be False
    assert state["onboarding_enabled"] is True
    assert state["onboarding_dismissed"] is False
    assert state["completion_percentage"] == 0
    assert all(not v for v in state["checklist_items"].values())
    print(f"DONE Default state: {state}")


@pytest.mark.mytral
def test_completion_percentage_calculation():
    # GIVEN: state with some items complete
    state = ob.get_default_onboarding_state()
    state["checklist_items"][ob.ITEM_PROFILE_COMPLETE] = True
    state["checklist_items"][ob.ITEM_FIRST_ACTIVITY] = True
    state["checklist_items"][ob.ITEM_FIRST_GOAL] = True

    # WHEN: calculating percentage
    percentage = ob.calculate_completion_percentage(state)

    # THEN: should be 37% (3/8 items)
    assert percentage == 37  # 3/8 = 0.375 = 37%
    print(f"DONE Completion: 3/8 items = {percentage}%")


@pytest.mark.mytral
def test_is_onboarding_active():
    # GIVEN: user profile with onboarding
    profile = settings.UserProfile(
        user_id="test",
        user="testuser",
        email="test@test.com",
        password_enc="",
        dataset_name="main",
        dataset_names=["main"],
        height=180,
    )

    # WHEN: checking if active
    # THEN: should be active by default
    assert ob.is_onboarding_active(profile) is True
    print("DONE Onboarding active for new user")


@pytest.mark.mytral
def test_dismiss_onboarding():
    # GIVEN: active onboarding
    profile = settings.UserProfile(
        user_id="test",
        user="testuser",
        email="test@test.com",
        password_enc="",
        dataset_name="main",
        dataset_names=["main"],
        height=180,
    )

    # WHEN: dismissing
    ob.dismiss_onboarding(profile)

    # THEN: should be dismissed
    assert profile.onboarding_state["onboarding_dismissed"] is True
    assert ob.is_onboarding_active(profile) is False
    print("DONE Onboarding dismissed successfully")


@pytest.mark.mytral
def test_reset_onboarding():
    # GIVEN: dismissed onboarding
    profile = settings.UserProfile(
        user_id="test",
        user="testuser",
        email="test@test.com",
        password_enc="",
        dataset_name="main",
        dataset_names=["main"],
        height=180,
    )
    ob.dismiss_onboarding(profile)

    # WHEN: resetting
    ob.reset_onboarding(profile)

    # THEN: should be active again
    assert ob.is_onboarding_active(profile) is True
    assert profile.onboarding_state["onboarding_dismissed"] is False
    print("DONE Onboarding reset successfully")


@pytest.mark.mytral
def test_update_checklist_item():
    # GIVEN: user profile
    profile = settings.UserProfile(
        user_id="test",
        user="testuser",
        email="test@test.com",
        password_enc="",
        dataset_name="main",
        dataset_names=["main"],
        height=180,
    )

    # WHEN: updating an item
    ob.update_checklist_item(profile, ob.ITEM_PROFILE_COMPLETE, True)

    # THEN: item should be marked complete and percentage updated
    assert profile.onboarding_state["checklist_items"][ob.ITEM_PROFILE_COMPLETE] is True
    assert profile.onboarding_state["completion_percentage"] == 12  # 1/8 = 12%
    print(
        f"DONE Checklist item updated: "
        f"{profile.onboarding_state['completion_percentage']}%"
    )


@pytest.mark.mytral
def test_get_checklist_display_items():
    # GIVEN: onboarding state
    state = ob.get_default_onboarding_state()
    state["checklist_items"][ob.ITEM_PROFILE_COMPLETE] = True

    # WHEN: getting display items
    items = ob.get_checklist_display_items(state)

    # THEN: should return 8 items with correct structure
    assert len(items) == 8
    assert items[0]["key"] == ob.ITEM_PROFILE_COMPLETE
    assert items[0]["completed"] is True
    assert items[0]["url"] == "/athlete/metrics"
    assert items[1]["completed"] is False
    print(f"DONE Display items: {len(items)} items returned")


@pytest.mark.mytral
def test_completion_percentage_all_complete():
    # GIVEN: state with all items complete
    state = ob.get_default_onboarding_state()
    for key in ob.BASIC_CHECKLIST_ITEMS:
        state["checklist_items"][key] = True

    # WHEN: calculating percentage
    percentage = ob.calculate_completion_percentage(state)

    # THEN: should be 100%
    assert percentage == 100
    print(f"DONE All items complete: {percentage}%")


@pytest.mark.mytral
def test_bootstrap_uuid_generation():
    # GIVEN: bootstrap names
    name1 = "pain"
    name2 = "Pain"  # different case
    name3 = "  pain  "  # with whitespace

    # WHEN: generating UUIDs
    uuid1 = settings.generate_bootstrap_uuid(name1)
    uuid2 = settings.generate_bootstrap_uuid(name2)
    uuid3 = settings.generate_bootstrap_uuid(name3)

    # THEN: should produce same UUID (case-insensitive, whitespace-stripped)
    assert uuid1 == uuid2 == uuid3
    # THEN: should be valid UUID string
    assert len(uuid1) == 36
    assert uuid1.count("-") == 4
    print(f"DONE Bootstrap UUID for '{name1}': {uuid1}")


@pytest.mark.mytral
def test_exercises_bootstrap_has_deterministic_uuids():
    # GIVEN: bootstrap exercises
    exercises = settings.UserExercises.bootstrap()

    # WHEN: checking UUIDs
    # THEN: should all have deterministic UUIDs
    for exercise in exercises:
        expected_uuid = settings.generate_bootstrap_uuid(exercise.name)
        assert exercise.key == expected_uuid
        print(f"DONE Exercise '{exercise.name}' has UUID: {exercise.key}")


@pytest.mark.mytral
def test_symptoms_bootstrap_has_deterministic_uuids():
    # GIVEN: bootstrap symptoms
    symptoms = settings.UserSymptoms.bootstrap()

    # WHEN: checking UUIDs
    # THEN: should all have deterministic UUIDs
    for symptom in symptoms:
        expected_uuid = settings.generate_bootstrap_uuid(symptom.name)
        assert symptom.key == expected_uuid
        print(f"DONE Symptom '{symptom.name}' has UUID: {symptom.key}")


@pytest.mark.mytral
def test_is_bootstrap_only_exercises_true():
    # GIVEN: exercises with only bootstrap data
    exercises = settings.UserExercises.bootstrap()
    user_exercises = settings.UserExercises(exercises=exercises)

    # WHEN: checking if bootstrap only
    is_bootstrap = user_exercises.is_bootstrap_only()

    # THEN: should return True
    assert is_bootstrap is True
    print("DONE Detected bootstrap-only exercises")


@pytest.mark.mytral
def test_is_bootstrap_only_exercises_false_when_modified():
    # GIVEN: exercises with bootstrap data + one custom exercise
    exercises = settings.UserExercises.bootstrap()
    user_exercises = settings.UserExercises(exercises=exercises)
    user_exercises.add_exercise(settings.Exercise(name="Custom Exercise"))

    # WHEN: checking if bootstrap only
    is_bootstrap = user_exercises.is_bootstrap_only()

    # THEN: should return False
    assert is_bootstrap is False
    print("DONE Detected modified exercises (custom exercise added)")


@pytest.mark.mytral
def test_is_bootstrap_only_exercises_false_when_deleted():
    # GIVEN: exercises with bootstrap data - one item
    exercises = settings.UserExercises.bootstrap()
    user_exercises = settings.UserExercises(exercises=exercises)
    first_key = list(user_exercises.exercise_by_key.keys())[0]
    user_exercises.delete(first_key)

    # WHEN: checking if bootstrap only
    is_bootstrap = user_exercises.is_bootstrap_only()

    # THEN: should return False (subset of bootstrap)
    assert is_bootstrap is False
    print("DONE Detected modified exercises (item deleted)")


@pytest.mark.mytral
def test_is_bootstrap_only_symptoms_true():
    # GIVEN: symptoms with only bootstrap data
    symptoms = settings.UserSymptoms.bootstrap()
    user_symptoms = settings.UserSymptoms(symptoms=symptoms)

    # WHEN: checking if bootstrap only
    is_bootstrap = user_symptoms.is_bootstrap_only()

    # THEN: should return True
    assert is_bootstrap is True
    print("DONE Detected bootstrap-only symptoms")


@pytest.mark.mytral
def test_is_bootstrap_only_symptoms_false_when_modified():
    # GIVEN: symptoms with bootstrap data + one custom symptom
    symptoms = settings.UserSymptoms.bootstrap()
    user_symptoms = settings.UserSymptoms(symptoms=symptoms)
    user_symptoms.add_symptom(settings.Symptom(name="Custom Symptom"))

    # WHEN: checking if bootstrap only
    is_bootstrap = user_symptoms.is_bootstrap_only()

    # THEN: should return False
    assert is_bootstrap is False
    print("DONE Detected modified symptoms (custom symptom added)")


@pytest.mark.mytral
def test_is_bootstrap_only_activity_types_true():
    # GIVEN: activity types with only bootstrap data
    activity_types = settings.UserActivityTypes.bootstrap()
    user_activity_types = settings.UserActivityTypes(activity_types=activity_types)

    # WHEN: checking if bootstrap only
    is_bootstrap = user_activity_types.is_bootstrap_only()

    # THEN: should return True
    assert is_bootstrap is True
    print("DONE Detected bootstrap-only activity types")


@pytest.mark.mytral
def test_is_bootstrap_only_activity_types_false_when_modified():
    # GIVEN: activity types with bootstrap data + one custom type
    activity_types = settings.UserActivityTypes.bootstrap()
    user_activity_types = settings.UserActivityTypes(activity_types=activity_types)
    user_activity_types.add_activity_type(
        settings.ActivityType(
            name="Custom Activity",
            is_distance=True,
            is_exercise=False,
            is_regen=False,
        )
    )

    # WHEN: checking if bootstrap only
    is_bootstrap = user_activity_types.is_bootstrap_only()

    # THEN: should return False
    assert is_bootstrap is False
    print("DONE Detected modified activity types (custom activity added)")
