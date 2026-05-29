# MyTraL: my trailing log
#
# Copyright (C) 2015-2026 Martin Dvorak <martin.dvorak@mindforger.com>
#
# This program is free software: you can redistribute it and/or modify
# it under the terms of the GNU Affero General Public License as published by
# the Free Software Foundation, either version 3 of the License, or
# (at your option) any later version.
import pathlib

# This program is distributed in the hope that it will be useful,
# but WITHOUT ANY WARRANTY; without even the implied warranty of
# MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the
# GNU Affero General Public License for more details.
#
# You should have received a copy of the GNU Affero General Public License
# along with this program. If not, see <http://www.gnu.org/licenses/>.
import pytest

from mytral import commons
from mytral import config
from mytral import loggers
from mytral import settings
from mytral.backends import dataset
from mytral.backends import entities

# TODO bugs:
# TODO: indices are not cached
# ...


SETTING_TYPES = [
    "activity-types",
    "exercises",
    "gear",
    "gear-strava",
    "goals",
    "laps",
    "outfits",
    "symptoms",
]


def _given_mytral_ds_with_user(
    tmp_path: pathlib.Path,
) -> tuple[pathlib.Path, dataset.MyTraLDataset, str, str]:
    data_dir = tmp_path / ".local"
    data_dir.mkdir(parents=True, exist_ok=True)
    user_id = "12345678-cb74-41d5-9a59-bfdd05b817c9"
    user_name = "cox"
    dataset_name = commons.DS_LIFELONG

    logger = loggers.MytralPrintLogger()
    app_config = config.MytralConfig(
        port=config.MytralConfig.DEFAULT_PORT,
        persistence_data_dir=data_dir.absolute(),
        auto_account_create=True,
    )
    mytral_ds = dataset.MyTraLDataset(mytral_config=app_config, logger=logger)
    assert mytral_ds
    mytral_ds.user().register_new_user(user_name=user_name, user_id=user_id)

    return data_dir, mytral_ds, user_id, dataset_name


@pytest.mark.mytral
def test_json_dataset_activities(tmp_path: pathlib.Path):
    """Test activities CRUD."""
    #
    # GIVEN
    #

    data_dir, mytral_ds, user_id, dataset_name = _given_mytral_ds_with_user(
        tmp_path=tmp_path
    )

    #
    # WHEN: activities CRUD
    #

    created_activities = []
    for when_year in range(2023, 2026, 1):
        # CREATE
        a = mytral_ds.user().create_activity(
            user_id=user_id,
            dataset_name=dataset_name,
            entity=entities.ActivityEntity(name=f"A {when_year}", when_year=when_year),
        )
        print(f"CREATED '{a.name}'")
        created_activities.append(a)

        # GET
        a = mytral_ds.user().get_activity(
            user_id=user_id, dataset_name=dataset_name, key=a.key
        )
        print(f"GOT '{a.name}'")

        # UPDATE
        a_update = mytral_ds.user().update_activity(
            user_id=user_id,
            dataset_name=dataset_name,
            entity=entities.ActivityEntity(
                key=a.key,
                name=f"A '{when_year}' UPDATED",
                # test year change which impacts target YEAR dataset
                when_year=when_year + 1 if when_year <= 2024 else when_year,
            ),
        )
        mytral_ds.user().update_activity(
            user_id=user_id, dataset_name=dataset_name, entity=a_update
        )
        print(f"UPDATED '{a.name}'")

    # DELETE
    for a in created_activities:
        print(f"DELETING '{a.name}' ...")
        mytral_ds.user().delete_activity(
            user_id=user_id, dataset_name=dataset_name, key=a.key
        )
    # TODO assert empty

    #
    # THEN
    #
    print("\nTest summary:")
    print(f"  CACHE size: {mytral_ds.user().cache_memory_size(user_id=user_id):,} B")
    print(f"  DATA dir  : file://{data_dir}")
    # TODO assert existing & content of the user files


@pytest.mark.mytral
def test_json_dataset_indices_and_settings(tmp_path: pathlib.Path):
    #
    # GIVEN
    #

    data_dir, mytral_ds, user_id, dataset_name = _given_mytral_ds_with_user(
        tmp_path=tmp_path
    )

    # activities for settings stats
    when_years = []
    for when_year in range(2020, 2026, 1):
        when_years.append(when_year)
        mytral_ds.user().create_activity(
            user_id=user_id,
            dataset_name=dataset_name,
            entity=entities.ActivityEntity(name=f"A {when_year}", when_year=when_year),
        )

    #
    # WHEN: indices
    #

    # TODO heatmap data

    #
    # WHEN: settings w/ activities stats
    #

    created_activity_types = []
    created_exercises = []
    created_gear = []
    created_goals = []
    created_outfits = []
    created_laps = []
    created_symptoms = []

    for i in range(3):
        # ACTIVITY TYPES
        print("ACTIVITY TYPES")
        print(f"  CREATE #{i}")
        activity_type = mytral_ds.user().create_activity_type(
            user_id=user_id,
            activity_type=settings.ActivityType(
                name=f"Activity Type {i}",
                is_distance=True,
                is_exercise=False,
                is_regen=False,
            ),
        )
        created_activity_types.append(activity_type)
        print(f"  GET #{i}")
        get_activity_type = mytral_ds.user().get_activity_type(
            user_id=user_id, key=activity_type.key
        )
        assert get_activity_type.key == activity_type.key
        assert get_activity_type.name == activity_type.name
        print(f"  UPDATE #{i}")
        new_activity_type = settings.ActivityType(
            name=f"UPDATED activity type {i}",
            is_distance=True,
            is_exercise=False,
            is_regen=False,
            key=activity_type.key,
        )
        updated_activity_type = mytral_ds.user().update_activity_type(
            user_id=user_id, activity_type=new_activity_type
        )
        assert updated_activity_type.key == activity_type.key
        assert updated_activity_type.name == new_activity_type.name

        # EXERCISES
        print("EXERCISES")
        print(f"  CREATE #{i}")
        exercise = mytral_ds.user().create_exercise(
            user_id=user_id, exercise=settings.Exercise(name=f"Exercise {i}")
        )
        created_exercises.append(exercise)
        print(f"  GET #{i}")
        get_exercise = mytral_ds.user().get_exercise(user_id=user_id, key=exercise.key)
        assert get_exercise.key == exercise.key
        assert get_exercise.name == exercise.name
        print(f"  UPDATE #{i}")
        new_exercise = settings.Exercise(name=f"UPDATED exercise {i}", key=exercise.key)
        updated_exercise = mytral_ds.user().update_exercise(
            user_id=user_id, exercise=new_exercise
        )
        assert updated_exercise.key == exercise.key
        assert updated_exercise.name == new_exercise.name

        # GEAR
        print("GEAR")
        print(f"  CREATE #{i}")
        gear = mytral_ds.user().create_gear(
            user_id=user_id,
            dataset_name=dataset_name,
            gear=settings.Gear(activity_type_key=commons.AT_RUN, name=f"Gear {i}"),
        )
        created_gear.append(gear)
        print(f"  GET #{i}")
        get_gear = mytral_ds.user().get_gear(
            user_id=user_id, key=gear.key, dataset_name=dataset_name
        )
        assert get_gear.key == gear.key
        assert get_gear.name == gear.name
        print(f"  UPDATE #{i}")
        new_gear = settings.Gear(
            activity_type_key=commons.AT_RUN, name=f"UPDATED gear {i}", key=gear.key
        )
        updated_gear = mytral_ds.user().update_gear(
            user_id=user_id, dataset_name=dataset_name, gear=new_gear
        )
        assert updated_gear.key == gear.key
        assert updated_gear.name == new_gear.name

        # STRAVA GEAR
        if i == 0:
            print("STRAVA GEAR")
            print("  LIST (should be empty initially)")
            strava_gears = mytral_ds.user().list_strava_gear(user_id=user_id)
            assert strava_gears.gears == []

            print("  UPDATE (add sample Strava gear)")
            sample_strava_gears = settings.StravaUserGear(
                gears=[
                    {
                        "id": f"strava_gear_{i}",
                        "name": f"Strava Gear {i}",
                        "primary": i == 0,
                        "brand_name": "Nike",
                        "model_name": f"Model {i}",
                        "distance": 10000 * (i + 1),
                        "retired": False,
                    }
                    for i in range(3)
                ]
            )
            updated_strava_gears = mytral_ds.user().update_strava_gears(
                user_id=user_id, strava_gears=sample_strava_gears
            )
            assert len(updated_strava_gears.gears) == 3

            print("  LIST (verify updated Strava gear)")
            listed_strava_gears = mytral_ds.user().list_strava_gear(user_id=user_id)
            assert len(listed_strava_gears.gears) == 3
            assert listed_strava_gears.strava_gear_ids() == [
                "strava_gear_0",
                "strava_gear_1",
                "strava_gear_2",
            ]

        # GOALS
        print("GOALS")
        print(f"  CREATE #{i}")
        goal = mytral_ds.user().create_goal(
            user_id=user_id,
            goal=settings.Goal(name=f"Goal {i}", activity_type=commons.AT_RUN),
        )
        created_goals.append(goal)
        print(f"  GET #{i}")
        get_goal = mytral_ds.user().get_goal(user_id=user_id, key=goal.key)
        assert get_goal.key == goal.key
        assert get_goal.name == goal.name
        print(f"  UPDATE #{i}")
        new_goal = settings.Goal(
            name=f"UPDATED goal {i}", activity_type=commons.AT_RUN, key=goal.key
        )
        updated_goal = mytral_ds.user().update_goal(user_id=user_id, goal=new_goal)
        assert updated_goal.key == goal.key
        assert updated_goal.name == new_goal.name

        # OUTFITS
        print("OUTFITS")
        print(f"  CREATE #{i}")
        outfit = mytral_ds.user().create_outfit(
            user_id=user_id,
            outfit=settings.Outfit(name=f"Outfit {i}", activity_type=commons.AT_RUN),
        )
        created_outfits.append(outfit)
        print(f"  GET #{i}")
        get_outfit = mytral_ds.user().get_outfit(user_id=user_id, key=outfit.key)
        assert get_outfit.key == outfit.key
        assert get_outfit.name == outfit.name
        print(f"  UPDATE #{i}")
        new_outfit = settings.Outfit(
            name=f"UPDATED outfit {i}", activity_type=commons.AT_RUN, key=outfit.key
        )
        updated_outfit = mytral_ds.user().update_outfit(
            user_id=user_id, outfit=new_outfit
        )
        assert updated_outfit.key == outfit.key
        assert updated_outfit.name == new_outfit.name

        # SYMPTOMS
        print("SYMPTOMS")
        print(f"  CREATE #{i}")
        symptom = mytral_ds.user().create_symptom(
            user_id=user_id, symptom=settings.Symptom(name=f"Symptom {i}")
        )
        created_symptoms.append(symptom)
        print(f"  GET #{i}")
        get_symptom = mytral_ds.user().get_symptom(user_id=user_id, key=symptom.key)
        assert get_symptom.key == symptom.key
        assert get_symptom.name == symptom.name
        print(f"  UPDATE #{i}")
        new_symptom = settings.Symptom(name=f"UPDATED symptom {i}", key=symptom.key)
        updated_symptom = mytral_ds.user().update_symptom(
            user_id=user_id, symptom=new_symptom
        )
        assert updated_symptom.key == symptom.key
        assert updated_symptom.name == new_symptom.name

        # LAP TYPES
        print("LAP TYPES")
        print(f"  CREATE #{i}")
        lap = mytral_ds.user().create_lap(
            user_id=user_id,
            lap=settings.Lap(
                name=f"Lap {i}",
                description=f"Lap description {i}",
                default_distance=1000 * (i + 1),
                default_duration=300 * (i + 1),
            ),
        )
        created_laps.append(lap)
        print(f"  GET #{i}")
        get_lap = mytral_ds.user().get_lap(user_id=user_id, key=lap.key)
        assert get_lap.key == lap.key
        assert get_lap.name == lap.name
        print(f"  UPDATE #{i}")
        new_lap = settings.Lap(
            name=f"UPDATED lap {i}",
            description=f"UPDATED lap description {i}",
            default_distance=2000 * (i + 1),
            default_duration=600 * (i + 1),
            key=lap.key,
        )
        updated_lap = mytral_ds.user().update_lap(user_id=user_id, lap=new_lap)
        assert updated_lap.key == lap.key
        assert updated_lap.name == new_lap.name

    #
    # WHEN: LIST all settings (verify all created entities exist)
    #
    print("\nLIST all settings (verify created entities):")

    print("  LIST activity types...")
    listed_activity_types = mytral_ds.user().list_activity_types(user_id=user_id)
    # should have bootstrap types + 3 created
    assert len(listed_activity_types.activity_types_by_key) >= 3
    for at in created_activity_types:
        assert at.key in listed_activity_types.activity_types_by_key

    print("  LIST exercises...")
    listed_exercises = mytral_ds.user().list_exercises(user_id=user_id)
    # should have bootstrap exercises + 3 created
    assert len(listed_exercises.exercise_by_key) >= 3
    for ex in created_exercises:
        assert ex.key in listed_exercises.exercise_by_key

    print("  LIST gear...")
    listed_gear = mytral_ds.user().list_gear(user_id=user_id, dataset_name=dataset_name)
    assert len(listed_gear.gear_by_key) == 3
    for g in created_gear:
        assert g.key in listed_gear.gear_by_key

    print("  LIST goals...")
    listed_goals = mytral_ds.user().list_goals(user_id=user_id)
    assert len(listed_goals.goals_by_key) == 3
    for goal in created_goals:
        assert goal.key in listed_goals.goals_by_key

    print("  LIST outfits...")
    listed_outfits = mytral_ds.user().list_outfits(user_id=user_id)
    assert len(listed_outfits.outfits_by_key) == 3
    for outfit in created_outfits:
        assert outfit.key in listed_outfits.outfits_by_key

    print("  LIST laps...")
    listed_laps = mytral_ds.user().list_laps(user_id=user_id)
    # should have bootstrap laps + 3 created
    assert len(listed_laps.lap_by_key) >= 3
    for route in created_laps:
        assert route.key in listed_laps.lap_by_key

    print("  LIST symptoms...")
    listed_symptoms = mytral_ds.user().list_symptoms(user_id=user_id)
    # should have bootstrap symptoms + 3 created
    assert len(listed_symptoms.symptoms_by_key) >= 3
    for symptom in created_symptoms:
        assert symptom.key in listed_symptoms.symptoms_by_key

    # DELETE all created entities
    print(f"DELETE {len(created_activity_types)} activity types...")
    for at in created_activity_types:
        mytral_ds.user().delete_activity_type(user_id=user_id, key=at.key)

    print(f"DELETE {len(created_exercises)} exercises...")
    for e in created_exercises:
        mytral_ds.user().delete_exercise(user_id=user_id, key=e.key)

    print(f"DELETE {len(created_gear)} gear...")
    for g in created_gear:
        mytral_ds.user().delete_gear(
            user_id=user_id, key=g.key, dataset_name=dataset_name
        )

    print(f"DELETE {len(created_goals)} goals...")
    for g in created_goals:
        mytral_ds.user().delete_goal(user_id=user_id, key=g.key)

    print(f"DELETE {len(created_outfits)} outfits...")
    for o in created_outfits:
        mytral_ds.user().delete_outfit(user_id=user_id, key=o.key)

    print(f"DELETE {len(created_laps)} laps...")
    for r in created_laps:
        mytral_ds.user().delete_lap(user_id=user_id, key=r.key)

    print(f"DELETE {len(created_symptoms)} symptoms...")
    for s in created_symptoms:
        mytral_ds.user().delete_symptom(user_id=user_id, key=s.key)

    #
    # WHEN: LIST all settings (verify deleted entities are gone)
    #
    print("\nLIST all settings (verify deleted entities are gone):")

    print("  LIST activity types...")
    listed_activity_types_after = mytral_ds.user().list_activity_types(user_id=user_id)
    for at in created_activity_types:
        assert at.key not in listed_activity_types_after.activity_types_by_key

    print("  LIST exercises...")
    listed_exercises_after = mytral_ds.user().list_exercises(user_id=user_id)
    for ex in created_exercises:
        assert ex.key not in listed_exercises_after.exercise_by_key

    print("  LIST gear...")
    listed_gear_after = mytral_ds.user().list_gear(
        user_id=user_id, dataset_name=dataset_name
    )
    assert len(listed_gear_after.gear_by_key) == 0
    for g in created_gear:
        assert g.key not in listed_gear_after.gear_by_key

    print("  LIST goals...")
    listed_goals_after = mytral_ds.user().list_goals(user_id=user_id)
    assert len(listed_goals_after.goals_by_key) == 0
    for goal in created_goals:
        assert goal.key not in listed_goals_after.goals_by_key

    print("  LIST outfits...")
    listed_outfits_after = mytral_ds.user().list_outfits(user_id=user_id)
    assert len(listed_outfits_after.outfits_by_key) == 0
    for outfit in created_outfits:
        assert outfit.key not in listed_outfits_after.outfits_by_key

    print("  LIST laps...")
    listed_laps_after = mytral_ds.user().list_laps(user_id=user_id)
    for lap in created_laps:
        assert lap.key not in listed_laps_after.lap_by_key

    print("  LIST symptoms...")
    listed_symptoms_after = mytral_ds.user().list_symptoms(user_id=user_id)
    for symptom in created_symptoms:
        assert symptom.key not in listed_symptoms_after.symptoms_by_key

    #
    # WHEN: indices caching
    #

    print(f"= BEGIN INDICES {30 * '#'}")
    idx = mytral_ds.user().profile_stats(user_id=user_id, dataset_name=dataset_name)
    print(f"=> Profile stats: {idx}")
    idx = mytral_ds.user().exercises_stats(user_id=user_id, dataset_name=dataset_name)
    print(f"=> Exercise stats: {idx}")
    idx = mytral_ds.user().activity_types_stats(
        user_id=user_id, dataset_name=dataset_name
    )
    print(f"=> Activity types stats: {idx}")
    idx = mytral_ds.user().gear_stats(user_id=user_id, dataset_name=dataset_name)
    print(f"=> Gear stats: {idx}")
    idx = mytral_ds.user().symptoms_stats(user_id=user_id, dataset_name=dataset_name)
    print(f"=> Symptoms stats: {idx}")
    idx = mytral_ds.user().activity_type_heatmap(
        user_id=user_id, dataset_name=dataset_name
    )
    print(f"=> Sport heatmap: {idx}")
    idx = mytral_ds.user().sick_heatmap(user_id=user_id, dataset_name=dataset_name)
    print(f"=> Sick heatmap: {idx}")
    print(f"= END INDICES {30 * '#'}")

    #
    # THEN
    #
    print("\nTest summary:")
    print(f"  CACHE size: {mytral_ds.user().cache_memory_size(user_id=user_id):,} B")
    print(f"  DATA dir  : file://{data_dir}")

    # assert filesystem and memory
    user_dir = data_dir / "data" / user_id
    assert user_dir.exists()
    assert not (user_dir / "lifelong.json").exists()
    for when_year in when_years:
        assert (user_dir / f"activities-{when_year}.json").exists()
    for setting_type in SETTING_TYPES:
        assert (user_dir / f"user-{setting_type}.json").exists()


@pytest.mark.mytral
def test_lap_entity_ranked_field():
    """Test that LapEntity has ranked field with default False."""
    #
    # GIVEN
    #
    lap = entities.LapEntity(
        activity_key="test-key",
        order=1,
        name="500m",
        distance=500,
        duration=120,
    )

    #
    # WHEN / THEN: default ranked is False
    #
    assert lap.ranked is False
    print("DONE: LapEntity ranked defaults to False")

    #
    # WHEN / THEN: ranked can be set to True
    #
    ranked_lap = entities.LapEntity(
        activity_key="test-key",
        order=1,
        name="500m",
        distance=500,
        duration=120,
        ranked=True,
    )
    assert ranked_lap.ranked is True
    print("DONE: LapEntity ranked can be set to True")


@pytest.mark.mytral
def test_ranked_laps_in_prs(tmp_path: pathlib.Path):
    """Test that ranked laps are collected from activities for PRs page."""
    #
    # GIVEN
    #
    data_dir, mytral_ds, user_id, dataset_name = _given_mytral_ds_with_user(
        tmp_path=tmp_path
    )

    # create an activity with a mix of ranked and non-ranked laps
    activity = mytral_ds.user().create_activity(
        user_id=user_id,
        dataset_name=dataset_name,
        entity=entities.ActivityEntity(
            name="Interval Workout",
            when_year=2025,
            when_month=3,
            when_day=1,
            activity_type_key="run",
            laps=[
                entities.LapEntity(
                    order=1, name="500m fast", distance=500, duration=90, ranked=True
                ),
                entities.LapEntity(
                    order=2, name="500m rest", distance=500, duration=180, ranked=False
                ),
                entities.LapEntity(
                    order=3, name="1000m", distance=1000, duration=200, ranked=True
                ),
            ],
        ),
    )

    #
    # WHEN: retrieve activities and collect ranked laps
    #
    activities = mytral_ds.user().list_activities(
        user_id=user_id,
        dataset_name=dataset_name,
        sort_by_when=True,
    )
    ranked_laps = []
    for a in activities:
        for lap in a.laps or []:
            if lap.ranked:
                ranked_laps.append(
                    {
                        "activity_key": a.key,
                        "activity_type_key": a.activity_type_key,
                        "name": lap.name,
                        "distance": lap.distance,
                        "duration": lap.duration,
                    }
                )

    #
    # THEN
    #
    assert len(ranked_laps) == 2, f"Expected 2 ranked laps, got {len(ranked_laps)}"
    lap_names = [lap["name"] for lap in ranked_laps]
    assert "500m fast" in lap_names
    assert "1000m" in lap_names
    assert "500m rest" not in lap_names
    assert ranked_laps[0]["activity_key"] == activity.key
    print(f"DONE: {len(ranked_laps)} ranked laps collected from activities")
    for lap in ranked_laps:
        print(f"  - {lap['name']}: {lap['distance']}m in {lap['duration']}s")
