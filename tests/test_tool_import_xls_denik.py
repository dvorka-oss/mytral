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
import random
from datetime import datetime

import pytest

from mytral import commons
from mytral import config
from mytral import persistences
from mytral import settings
from mytral.backends import entities
from tests import _given


@pytest.mark.skip("MyTraL tool - not a test")
@pytest.mark.parametrize(
    "raw_csv_name,year,month",
    [
        # 1996
        ("denik96.xls - Kveten.csv", 1996, 5),
        ("denik96.xls - Cerven.csv", 1996, 6),
        ("denik96.xls - Cervenec.csv", 1996, 7),
        ("denik96.xls - Srpen.csv", 1996, 8),
        ("denik96.xls - Zari.csv", 1996, 9),
        ("denik96.xls - Rijen.csv", 1996, 10),
        ("denik96.xls - Listopad.csv", 1996, 11),
        ("denik96.xls - Prosinec.csv", 1996, 12),
        # 1997
        ("denik97.xls - Leden.csv", 1997, 1),
        ("denik97.xls - Unor.csv", 1997, 2),
        ("denik97.xls - Brezen.csv", 1997, 3),
        ("denik97.xls - Duben.csv", 1997, 4),
        ("denik97.xls - Kveten.csv", 1997, 5),
        ("denik97.xls - Cerven.csv", 1997, 6),
        ("denik97.xls - Cervenec.csv", 1997, 7),
        ("denik97.xls - Srpen.csv", 1997, 8),
        ("denik97.xls - Zari.csv", 1997, 9),
        ("denik97.xls - Rijen.csv", 1997, 10),
        ("denik97.xls - Listopad.csv", 1997, 11),
        ("denik97.xls - Prosinec.csv", 1997, 12),
        # 1998
        ("denik98.xls - Leden.csv", 1998, 1),
        ("denik98.xls - Unor.csv", 1998, 2),
        ("denik98.xls - Brezen.csv", 1998, 3),
        ("denik98.xls - Duben.csv", 1998, 4),
        ("denik98.xls - Kveten.csv", 1998, 5),
        ("denik98.xls - Cerven.csv", 1998, 6),
        ("denik98.xls - Cervenec.csv", 1998, 7),
        ("denik98.xls - Srpen.csv", 1998, 8),
        ("denik98.xls - Zari.csv", 1998, 9),
        ("denik98.xls - Rijen.csv", 1998, 10),
        ("denik98.xls - Listopad.csv", 1998, 11),
        ("denik98.xls - Prosinec.csv", 1998, 12),
    ],
)
@pytest.mark.tool
def test_import_1_csv_sheet(tmp_path: pathlib.Path, raw_csv_name, year, month):
    """Import one CSV sheet exported from my 1996 - 1999 training diary.
    Prune raw CSV to clean CSV, load it, extra data, create entities,
    store them using the database.

    """
    #
    # GIVEN
    #
    normalized_file_name = f"{year}-{month:02}-xls"
    raw_csv_path = pathlib.Path("data-sources") / "xls" / raw_csv_name
    print(f"Raw CSV path:\n{raw_csv_path}")
    normalized_json_path = tmp_path / f"{normalized_file_name}.json"
    print(f"Normalized JSON path:\n{normalized_json_path}")

    # prune raw CSV
    with open(raw_csv_path, "r") as file:
        raw_csv_str = file.read()

    csv_str = ""
    prelude = True
    for r in raw_csv_str.split("\n"):
        if r.startswith(",Den"):
            prelude = False

        if prelude:
            continue

        csv_str += r + "\n"

    print(csv_str)

    # user and dataset
    _, ds, profile = _given.given_test(
        config.MytralConfig(persistence_data_dir=tmp_path),
        user_id=commons.DEFAULT_USER_NAME,
    )

    new_ds_name = f"XLS-IMPORT-{year}-{month:02}"
    ds.create_activities_dataset(
        user_id=profile.user_id,
        dataset_name=new_ds_name,
    )

    #
    # WHEN
    #
    normalized_dict = {}
    zero_time = "0:00:00"

    for r in csv_str.split("\n"):
        r_s = r.split(",")
        r_ann = [f"{e}={v}" for e, v in enumerate(r_s)]
        workout = 1
        print(r_ann)

        if len(r_s) < 4 or r_s[1] == "Den":
            print("  Skipping ^")
            continue

        r_day = r_s[1]
        r_run_km = r_s[4]
        r_run_t = r_s[5]
        r_bike_km = r_s[10]
        r_bike_t = r_s[11]
        r_swim_km = r_s[16]
        r_swim_t = r_s[17]
        r_ski_km = r_s[22]
        r_ski_t = r_s[23]
        r_squat = r_s[28]
        r_calf = r_s[29]
        r_sit_up = r_s[30]

        r_day = int(r_day.replace(".", ""))
        r_run_km = int(float(r_run_km))
        r_bike_km = int(float(r_bike_km))
        r_ski_km = int(float(r_ski_km))
        r_swim_km = int(float(r_swim_km))
        r_squat = int(r_squat)
        r_calf = int(r_calf)
        r_sit_up = int(r_sit_up)

        print(f"{r_day}. {raw_csv_name}")
        print(f"  Run : {r_run_km} km, {r_run_t}")
        print(f"  Bike: {r_bike_km} km, {r_bike_t}")
        print(f"  Swim: {r_swim_km} km, {r_swim_t}")
        print(f"  Ski : {r_ski_km} km, {r_ski_t}")
        print(f"  Squat: {r_squat}")
        print(f"  Calf : {r_calf}")
        print(f"  Sit up: {r_sit_up}")

        if (
            not r_run_km
            and r_run_t.endswith(zero_time)
            and not r_bike_km
            and r_bike_t.endswith(zero_time)
            and not r_swim_km
            and r_swim_t.endswith(zero_time)
            and not r_ski_km
            and r_ski_t.endswith(zero_time)
            and not r_squat
            and not r_calf
            and not r_sit_up
        ):
            print("  Skipping ^")
            continue

        # normalization
        def _prototype(workout_order: int) -> tuple[entities.ActivityEntity, int]:
            a = entities.ActivityEntity()

            a.src = "xls-log-import"

            # reset
            a.minutes = 0

            a.when_year = year
            a.when_month = month
            a.when_day = r_day
            try:
                print(
                    f"{year=} {month=} {r_day} "
                    f"{a.when_hour=} {a.when_minute=} {a.when_second=}"
                )
                a.when = datetime(
                    year=year,
                    month=month,
                    day=r_day,
                    hour=a.when_hour,
                    minute=a.when_minute,
                    second=a.when_second,
                ).isoformat()
            except ValueError as x:
                raise ValueError(
                    f"Error: {x}\n"
                    f"  {year=} {month=} {r_day=}\n"
                    f"  {a.when_hour=} {a.when_minute=} {a.when_second=}"
                )

            a.workout_sort_code = workout_order
            workout_order += 1

            return a, workout_order

        def _parse_time(a: entities.ActivityEntity, r_t: str):
            if r_t and not r_t.endswith(zero_time):
                a.hours = int(r_t.split(":")[0])
                a.minutes = int(r_t.split(":")[1])
                a.seconds = int(r_t.split(":")[2])
            else:
                a.hours = 0
                a.minutes = 0
                a.seconds = 0

        if r_run_km or (r_run_t and not r_run_t.endswith(zero_time)):
            aa, workout = _prototype(workout)

            aa.activity_type_key = commons.AT_RUN
            aa.name = "Run"
            aa.distance = r_run_km * 1000
            _parse_time(aa, r_run_t)

            entities.evaluate_activity(entity=aa, user_profile=profile)

            normalized_dict[aa.key] = aa.to_dict()

        if r_bike_km or (r_bike_t and not r_bike_t.endswith(zero_time)):
            aa, workout = _prototype(workout)

            aa.activity_type_key = commons.AT_RIDE
            aa.name = "Bike"
            aa.distance = r_bike_km * 1000
            _parse_time(aa, r_bike_t)

            entities.evaluate_activity(entity=aa, user_profile=profile)

            normalized_dict[aa.key] = aa.to_dict()

        if r_ski_km or (r_ski_t and not r_ski_t.endswith(zero_time)):
            aa, workout = _prototype(workout)

            aa.activity_type_key = commons.AT_SKI_F
            aa.name = "Ski skating"
            aa.distance = r_ski_km * 1000
            _parse_time(aa, r_ski_t)

            entities.evaluate_activity(entity=aa, user_profile=profile)

            normalized_dict[aa.key] = aa.to_dict()

        if r_swim_km or (r_swim_t and not r_swim_t.endswith(zero_time)):
            aa, workout = _prototype(workout)

            aa.activity_type_key = commons.AT_SWIM
            aa.name = "Swim"
            aa.distance = r_swim_km * 1000
            _parse_time(aa, r_swim_t)

            entities.evaluate_activity(entity=aa, user_profile=profile)

            normalized_dict[aa.key] = aa.to_dict()

        if r_squat or r_calf or r_sit_up:
            aa, workout = _prototype(workout)

            aa.activity_type_key = commons.AT_GYM
            aa.name = "Bodyweight training"

            es = [
                ("squat", r_squat),
                ("calf-lift", r_calf),
                ("sit-up", r_sit_up),
            ]
            for e in es:
                if e[1]:
                    e_e = entities.ExerciseEntity(
                        activity_key=aa.key,
                        name=e[0],
                        weight=0,
                        series=1,
                        repetitions=e[1],
                    )
                    aa.exercises.append(e_e)

            entities.evaluate_activity(entity=aa, user_profile=profile)

            normalized_dict[aa.key] = aa.to_dict()

    normalized_json_path = tmp_path / f"dataset-{year}-{month}-xls.json"
    persistences.save_json(file_path=normalized_json_path, data_dict=normalized_dict)

    #
    # THEN
    #

    print(f"Saved to:\nfile://{normalized_json_path}")


@pytest.mark.skip("MyTraL tool - not a test")
@pytest.mark.parametrize(
    "activities_path",
    [
        pathlib.Path(
            f"{_given.EXT_TEST_DATA_ROOT}/digitalization-1996-2023"
            "/data/ba16be59-83ee-4999-9b37-d2c49e454135/activities-1996.json"
        )
    ],
)
@pytest.mark.tool
def test_check_and_fix_year(tmp_path: pathlib.Path, activities_path: pathlib.Path):
    """Check and fix activities-<YEAR>.json file previously imported from XLS."""

    #
    # GIVEN
    #

    if not activities_path.exists():
        pytest.skip(f"Test file not found: {activities_path}")

    activities_dict = persistences.load_json(file_path=activities_path)
    print(f"Loaded {len(activities_dict)} activities from:\n{activities_path}")

    fixed_activities_dict = {}
    fixed_count = 0

    # user profile for evaluation
    _, ds, profile = _given.given_test(
        config.MytralConfig(persistence_data_dir=tmp_path),
        user_id=commons.DEFAULT_USER_NAME,
    )

    # try to load user exercises from the real data directory
    user_exercises_path = activities_path.parent / "user-exercises.json"
    if user_exercises_path.exists():
        print(f"Loading user exercises from:\n{user_exercises_path}")
        exercises_data = persistences.load_json(file_path=user_exercises_path)
        user_exercises = settings.UserExercises.from_dict_dict(exercises_data)
    else:
        raise f"User exercises file NOT found: {user_exercises_path}"

    exercise_by_key = user_exercises.exercise_by_key
    print(f"Loaded {len(exercise_by_key)} exercise types")

    #
    # WHEN
    #

    for key, activity_data in activities_dict.items():
        activity = entities.ActivityEntity(**activity_data)

        # convert nested entities from dicts to objects
        if activity.exercises:
            activity.exercises = [
                entities.ExerciseEntity(**e) if isinstance(e, dict) else e
                for e in activity.exercises
            ]
        if activity.sickness_symptoms:
            activity.sickness_symptoms = [
                entities.SicknessSymptomEntity(**s) if isinstance(s, dict) else s
                for s in activity.sickness_symptoms
            ]
        if activity.laps:
            activity.laps = [
                entities.LapEntity(**lap) if isinstance(lap, dict) else lap
                for lap in activity.laps
            ]

        changed = False

        if activity.activity_type_key in [commons.AT_RUN]:
            activity.when_hour = random.randint(19, 22)
            activity.when_minute = random.randint(3, 57)
            activity.when_second = random.randint(1, 59)
        elif activity.activity_type_key in [
            commons.AT_SKI_F,
            commons.AT_SKI_F,
            commons.AT_GYM,
            commons.AT_SWIM,
        ]:
            activity.when_hour = random.randint(10, 19)
            activity.when_minute = random.randint(3, 57)
            activity.when_second = random.randint(1, 59)
        elif activity.activity_type_key in [
            commons.AT_COMMENT,
            commons.AT_SICK,
            commons.AT_INJURED,
        ]:
            activity.when_hour = 1
            activity.when_minute = 0
            activity.when_second = 0

        # fix body weight exercises with no kilograms
        if activity.activity_type_key == commons.AT_GYM and activity.exercises:
            for exercise in activity.exercises:
                if exercise.repetitions > 0 and exercise.weight == 0.0:
                    # ensure activity key
                    exercise.activity_key = activity.key

                    # try to get default weight from user exercises by key (UUID)
                    print(
                        f"Checking exercise key='{exercise.name}' with "
                        f"weight={exercise.weight}, "
                        f"reps={exercise.repetitions} in activity {key}"
                    )
                    if exercise.name in exercise_by_key:
                        user_exercise = exercise_by_key[exercise.name]
                        default_weight = user_exercise.weight
                        print(
                            f"  Found in user-exercises.json: key='{exercise.name}' "
                            f"name='{user_exercise.name}' with default "
                            f"weight={default_weight} kg"
                        )
                        if not exercise.weight and default_weight:
                            exercise.weight = default_weight
                            changed = True
                            print(
                                f"  DONE Fixed exercise weight for {key}: "
                                f"{user_exercise.name} = {default_weight} kg"
                            )
                        else:
                            print(
                                f"  ✗ Default weight is 0.0, not applying for {key}: "
                                f"{user_exercise.name}"
                            )
                    else:
                        print(
                            f"  ✗ Warning: exercise key '{exercise.name}' not found in "
                            f"exercise_by_key"
                        )
                        print(
                            f"  Available exercise keys (first 5): "
                            f"{list(exercise_by_key.keys())[:5]}"
                        )

        # fix bike activity with no duration
        if activity.activity_type_key == commons.AT_RIDE:
            if not activity.gears:
                activity.gears = ["c4705bb9-4b66-45ae-855a-2f2277a31b5a"]
            if activity.hours == 0 and activity.minutes == 0 and activity.seconds == 0:
                if activity.distance > 0:
                    speed_kmh = 17.0
                    duration_hours = (activity.distance / 1000.0) / speed_kmh
                    total_seconds = int(duration_hours * 3600)
                    activity.hours = total_seconds // 3600
                    activity.minutes = (total_seconds % 3600) // 60
                    activity.seconds = total_seconds % 60
                    changed = True
                    print(
                        f"Fixed bike duration for {key}: "
                        f"{activity.hours}h{activity.minutes}m{activity.seconds}s "
                        f"({activity.distance}m @ 17km/h)"
                    )

        # fix swim activity with no duration (has distance, needs duration)
        if activity.activity_type_key == commons.AT_SWIM:
            if activity.hours == 0 and activity.minutes == 0 and activity.seconds == 0:
                if activity.distance > 0:
                    pace_min_per_km = 25.0
                    duration_minutes = (activity.distance / 1000.0) * pace_min_per_km
                    total_seconds = int(duration_minutes * 60)
                    activity.hours = total_seconds // 3600
                    activity.minutes = (total_seconds % 3600) // 60
                    activity.seconds = total_seconds % 60
                    changed = True
                    print(
                        f"Fixed swim duration for {key}: "
                        f"{activity.hours}h{activity.minutes}m{activity.seconds}s "
                        f"({activity.distance}m @ 21min/km)"
                    )
            # fix swim activity with no distance (has duration, needs distance)
            if activity.distance == 0:
                total_seconds = (
                    activity.hours * 3600 + activity.minutes * 60 + activity.seconds
                )
                if total_seconds > 0:
                    # 1km in 20 minutes = 0.05 km/min
                    distance_km = (total_seconds / 60) * 0.05
                    activity.distance = int(distance_km * 1000)
                    changed = True
                    print(
                        f"Fixed swim distance for {key}: "
                        f"{activity.distance}m "
                        f"({activity.hours}h{activity.minutes}m{activity.seconds}s "
                        f"@ 20min/km)"
                    )

        # fix ski skate activity with no duration
        if activity.activity_type_key in [commons.AT_SKI_F, commons.AT_SKI_DP]:
            if not activity.gears:
                activity.gears = ["f3229d1a-e65d-481e-b61e-0ce541deb911"]
            if (
                activity.activity_type_key in [commons.AT_SKI_F]
                and "ba7050e8-cddc-4808-b9dd-3bdd54e49ede" not in activity.gears
            ):
                activity.gears.append("ba7050e8-cddc-4808-b9dd-3bdd54e49ede")

            if activity.hours == 0 and activity.minutes == 0 and activity.seconds == 0:
                if activity.distance > 0:
                    pace_min_per_km = 5.0
                    duration_minutes = (activity.distance / 1000.0) * pace_min_per_km
                    total_seconds = int(duration_minutes * 60)
                    activity.hours = total_seconds // 3600
                    activity.minutes = (total_seconds % 3600) // 60
                    activity.seconds = total_seconds % 60
                    changed = True
                    print(
                        f"Fixed ski duration for {key}: "
                        f"{activity.hours}h{activity.minutes}m{activity.seconds}s "
                        f"({activity.distance}m @ 5min/km)"
                    )

        if activity.activity_type_key in [commons.AT_RUN]:
            if not activity.gears:
                activity.gears = ["a5b8229d-19ce-4e24-bb55-c531cf72ba17"]

        # fix URL for xls-log-import source activities from 1996
        if activity.src == "xls-log-import" and activity.when_year == 1996:
            if not activity.src_url:
                activity.src_url = (
                    "https://docs.google.com/spreadsheets/d/"
                    "1RdvdiMzQF5DJLbP7-i04P4I4s8q7beCE"
                )
                changed = True
                print(f"Fixed URL for {key}")

        if changed:
            fixed_count += 1

        # ALWAYS evaluate
        entities.evaluate_activity(entity=activity, user_profile=profile)

        # preserve all fields including default values
        fixed_activities_dict[key] = activity.to_dict()

    # save fixed activities
    fixed_path = tmp_path / f"{activities_path.name}"
    persistences.save_json(file_path=fixed_path, data_dict=fixed_activities_dict)

    #
    # THEN
    #

    print(f"\nFixed {fixed_count} activities out of {len(activities_dict)}")
    print(f"Saved fixed activities to:\nfile://{fixed_path}")

    # check for missing durations/kgs/distances for activities where expected
    issues = []

    for key, activity_data in fixed_activities_dict.items():
        activity = entities.ActivityEntity(**activity_data)

        # convert nested entities from dicts to objects
        if activity.exercises:
            activity.exercises = [
                entities.ExerciseEntity(**e) if isinstance(e, dict) else e
                for e in activity.exercises
            ]

        # check bike activities have duration if they have distance
        if activity.activity_type_key == commons.AT_RIDE and activity.distance > 0:
            if activity.hours == 0 and activity.minutes == 0 and activity.seconds == 0:
                issues.append(f"Bike activity {key} has distance but no duration")

        # check swim activities have duration if they have distance
        if activity.activity_type_key == commons.AT_SWIM and activity.distance > 0:
            if activity.hours == 0 and activity.minutes == 0 and activity.seconds == 0:
                issues.append(f"Swim activity {key} has distance but no duration")

        # check ski activities have duration if they have distance
        if activity.activity_type_key == commons.AT_SKI_F and activity.distance > 0:
            if activity.hours == 0 and activity.minutes == 0 and activity.seconds == 0:
                issues.append(f"Ski activity {key} has distance but no duration")

        # check exercises have weight
        if activity.exercises:
            for i, exercise in enumerate(activity.exercises):
                if exercise.repetitions > 0 and exercise.weight == 0.0:
                    issues.append(
                        f"Exercise #{i} in activity {key} has repetitions but no weight"
                    )

    if issues:
        print("\nRemaining issues found:")
        for issue in issues:
            print(f"  - {issue}")

    assert len(fixed_activities_dict) == len(activities_dict), (
        "Activities count mismatch"
    )
    assert fixed_count >= 0, "Fixed count should be non-negative"
