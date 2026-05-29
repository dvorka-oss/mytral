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
from mytral import persistences
from tests import _given


@pytest.mark.skip("MyTraL tool - not a test")
@pytest.mark.parametrize("action,ds_path", [("complete-run-duration", "...path")])
@pytest.mark.tool
def test_digitalization_patch_year_tool(
    tmp_path: pathlib.Path, action: str, ds_path: pathlib.Path
):
    """The test which is used a tool for patching, completion, recalculation, and fixes
    of the digitized data.

    """

    #
    # GIVEN
    #
    if not ds_path.exists():
        raise f"Target file {ds_path} does not exist"
    ds_dict = persistences.load_json(ds_path)

    #
    # WHEN
    #

    modified = False
    for a in ds_dict.values():
        if not a.duration:
            # TODO supply default duration at 5min/km pace
            ...

    result_path = tmp_path / ds_path.name
    if modified:
        persistences.save_json(file_path=result_path, data_dict=ds_dict)

    #
    # THEN
    #

    # TODO verification
    print(f"Patched dataset saved to file://{result_path}")


@pytest.mark.skip("MyTraL tool - not a test")
@pytest.mark.tool
def test_ds_patch_for_100_persistence(tmp_path: pathlib.Path):
    """Patch all datasets for 1.0.0 persistence rewrite."""
    #
    # GIVEN
    #

    user_dir_path = pathlib.Path(f"data/{commons.DEFAULT_USER_NAME}")
    # list files with "dataset-" prefix
    for f in list(user_dir_path.glob("dataset-*.json")):
        print(f"{f}")

        #
        # WHEN
        #

        # load dataset
        f_dict = persistences.load_json(f)
        new_f_dict = f_dict.get("activities", {})

        # save changes
        new_name = f.name.replace("dataset-", "activities-")
        persistences.save_json(file_path=tmp_path / new_name, data_dict=new_f_dict)
        print(f"  {new_name}")


@pytest.mark.skip("MyTraL tool - not a test")
@pytest.mark.tool
def test_patch_exercise_names_to_keys():
    """Replace exercise names with keys in activities of all datasets."""

    #
    # GIVEN
    #

    data_path = pathlib.Path(f"{_given.EXT_TEST_DATA_ROOT}/development")

    _, ds, profile = _given.given_test(
        config.MytralConfig(persistence_data_dir=data_path),
        user_id=commons.DEFAULT_USER_NAME,
    )

    # exercises map: name -> key
    e_dict = persistences.load_json(ds.user_exercises_path(profile.user_id))
    e_name_to_key = {e["name"]: e["key"] for e in e_dict.values()}
    print(f"Exercises: {e_name_to_key}")

    dataset_names = profile.dataset_names

    print("Datasets:")
    for d in dataset_names:
        print(f"  {d}")
        d_path = ds._activities_dataset._ds_path(
            user_id=profile.user_id, dataset_name=d
        )
        print(f"    {d_path}")
        if not d_path.exists():
            raise FileNotFoundError(f"Dataset {d} not found at {d_path}")

        # patch the dataset
        d_dict = persistences.load_json(d_path)
        # skip empty datasets
        if not d_dict:
            continue

        modified = False
        for a in d_dict.values():
            print(f"    {a['name']}")

            #
            # WHEN
            #

            if "exercises" in a:
                for e in a["exercises"]:
                    print(f"      {e}")
                    e_name = e["name"]
                    if e_name not in e_name_to_key:
                        raise ValueError(
                            f"Exercise '{e_name}' not found in exercises map:"
                            f"\n dataset: {d}"
                            f"\n activity: {a['key']}"
                            f"\n activity: {a['name']}"
                        )

                    e["name"] = e_name_to_key[e["name"]]

                    modified = True

        # save changes
        if modified:
            persistences.save_json(file_path=d_path, data_dict=d_dict)


@pytest.mark.skip("MyTraL tool - not a test")
@pytest.mark.tool
def test_patch_symptom_names_to_keys():
    """Replace symptom names with keys in activities of all datasets."""

    #
    # GIVEN
    #

    data_path = pathlib.Path(f"{_given.EXT_TEST_DATA_ROOT}/development")

    _, ds, profile = _given.given_test(
        config.MytralConfig(persistence_data_dir=data_path),
        user_id=commons.DEFAULT_USER_NAME,
    )

    # symptoms map: name -> key
    s_dict = persistences.load_json(ds.user_symptoms_path(profile.user_id))

    s_name_to_key = {e["name"]: e["key"] for e in s_dict.values()}
    print(f"Symptoms: {s_name_to_key}")

    dataset_names = profile.dataset_names

    print("Datasets:")
    for d in dataset_names:
        print(f"  {d}")
        d_path = ds._activities_dataset._ds_path(
            user_id=profile.user_id, dataset_name=d
        )
        print(f"    {d_path}")
        if not d_path.exists():
            raise FileNotFoundError(f"Dataset {d} not found at {d_path}")

        # patch the dataset
        d_dict = persistences.load_json(d_path)
        # skip empty datasets
        if not d_dict:
            continue

        modified = False
        for a in d_dict.values():
            print(f"    {a['name']}")

            #
            # WHEN
            #

            if "sickness_symptoms" in a:
                for s in a["sickness_symptoms"]:
                    print(f"      {s}")
                    s_name = s["symptom"]
                    if s_name not in s_name_to_key:
                        raise ValueError(
                            f"Symptom '{s_name}' not found in symptoms map:"
                            f"\n dataset: {d}"
                            f"\n activity: {a['key']}"
                            f"\n activity: {a['name']}"
                        )

                    s["symptom"] = s_name_to_key[s["symptom"]]

                    modified = True

        # save changes
        if modified:
            persistences.save_json(file_path=d_path, data_dict=d_dict)


@pytest.mark.skip("MyTraL tool - not a test")
@pytest.mark.tool
def test_patch_sick_activities():
    """Patch sick activities: reset gear, set time to 5:00, ..."""

    #
    # GIVEN
    #

    data_path = pathlib.Path(f"{_given.EXT_TEST_DATA_ROOT}/development")
    user_id = "ba16be59-83ee-4999-9b37-d2c49e454135"
    ds, user_ds = _given.given_ds(config.MytralConfig(persistence_data_dir=data_path))
    profile = user_ds.profile(user_id)

    dataset_names = profile.dataset_names

    print("Datasets:")
    for d in dataset_names:
        print(f"  {d}")
        d_path = user_ds._activities_dataset._ds_path(
            user_id=profile.user_id, dataset_name=d
        )
        print(f"    {d_path}")
        if not d_path.exists():
            raise FileNotFoundError(f"Dataset {d} not found at {d_path}")

        # patch the dataset
        d_dict = persistences.load_json(d_path)
        # skip empty datasets
        if not d_dict:
            continue

        modified = False
        for a in d_dict.values():
            print(f"    {a['name']}")

            #
            # WHEN
            #

            if a.get("activity_type_key") == commons.AT_SICK:
                print(f"      SICK: {a}")
                a["when_hour"] = 5
                a["when_minute"] = 0
                a["when_second"] = 0
                a["gear"] = ""

                modified = True

        # save changes
        if modified:
            persistences.save_json(file_path=d_path, data_dict=d_dict)


@pytest.mark.skip("MyTraL tool - not a test")
@pytest.mark.tool
def test_gym_activities_duration():
    """Patch gym activities: 4 tons counts for 30 minutes."""

    #
    # GIVEN
    #

    data_path = pathlib.Path(f"{_given.EXT_TEST_DATA_ROOT}/pythonanywhere")
    user_id = "ba16be59-83ee-4999-9b37-d2c49e454135"
    ds, user_ds = _given.given_ds(config.MytralConfig(persistence_data_dir=data_path))
    profile = user_ds.profile(user_id)

    dataset_names = profile.dataset_names

    print("Datasets:")
    for d in dataset_names:
        if "2025" not in d:
            continue

        print(f"  {d}")
        d_path = user_ds._activities_dataset._ds_path(
            user_id=profile.user_id, dataset_name=d
        )
        print(f"    {d_path}")
        if not d_path.exists():
            raise FileNotFoundError(f"Dataset {d} not found at {d_path}")

        # patch the dataset
        d_dict = persistences.load_json(d_path)
        # skip empty datasets
        if not d_dict:
            continue

        modified = False
        for a in d_dict.values():
            #
            # WHEN
            #

            if a.get("activity_type_key") == commons.AT_GYM:
                if not a["hours"] and not a["minutes"] and not a["seconds"]:
                    print(f"  {a['name']}")
                    print(f"    GYM: {a}")

                    if "klik" in a["name"].lower():
                        a["minutes"] = 30
                    elif "fit2b" in a["name"].lower():
                        a["minutes"] = 60
                    else:
                        a["minutes"] = 20

                    modified = True

        # save changes
        if modified:
            persistences.save_json(file_path=d_path, data_dict=d_dict)


@pytest.mark.skip("MyTraL tool - not a test")
@pytest.mark.parametrize(
    "user_data_dir",
    [
        f"{_given.EXT_TEST_DATA_ROOT}/development"
        f"/data/ba16be59-83ee-4999-9b37-d2c49e454135"
    ],
)
@pytest.mark.tool
def test_import_routes_to_laps(user_data_dir: str):
    """Import routes to laps: load user-routes.json to add entries to user-laps.json."""

    #
    # GIVEN
    #

    user_dir = pathlib.Path(user_data_dir)
    if not user_dir.exists():
        raise FileNotFoundError(f"User directory {user_dir} does not exist")

    routes_path = user_dir / "user-routes.json"
    laps_path = user_dir / "user-laps.json"

    if not routes_path.exists():
        raise FileNotFoundError(f"Routes file {routes_path} does not exist")
    if not laps_path.exists():
        raise FileNotFoundError(f"Laps file {laps_path} does not exist")

    routes_dict = persistences.load_json(routes_path)
    laps_dict = persistences.load_json(laps_path)

    print(f"Routes loaded: {len(routes_dict)} entries")
    print(f"Laps loaded: {len(laps_dict)} entries")

    #
    # WHEN
    #

    added_count = 0
    for route_key, route in routes_dict.items():
        if route_key not in laps_dict:
            lap_entry = {
                "name": route["name"],
                "description": route.get("description", ""),
                "default_distance": route.get("distance", 0),
                "default_duration": 0,
                "key": route["key"],
            }
            laps_dict[route_key] = lap_entry
            added_count += 1
            print(
                f"  Added lap: {route['name']} (distance: {route.get('distance', 0)}m)"
            )

    #
    # THEN
    #

    if added_count > 0:
        persistences.save_json(file_path=laps_path, data_dict=laps_dict)
        print(f"\nAdded {added_count} new laps to {laps_path}")
        print(f"Total laps now: {len(laps_dict)}")
    else:
        print("\nNo new laps to add - all routes already exist in laps")


@pytest.mark.skip("MyTraL tool - not a test")
@pytest.mark.parametrize(
    "activities_path",
    [
        pathlib.Path(
            f"{_given.EXT_TEST_DATA_ROOT}/digitalization-1996-2023"
            "/data/ba16be59-83ee-4999-9b37-d2c49e454135/activities-1996.json"
        ),
        pathlib.Path(
            f"{_given.EXT_TEST_DATA_ROOT}/pythonanywhere/data"
            "/ba16be59-83ee-4999-9b37-d2c49e454135/activities-2024.json"
        ),
        pathlib.Path(
            f"{_given.EXT_TEST_DATA_ROOT}/pythonanywhere/data"
            "/ba16be59-83ee-4999-9b37-d2c49e454135/activities-2025.json"
        ),
    ],
)
@pytest.mark.tool
def test_reset_watts(tmp_path: pathlib.Path, activities_path: pathlib.Path):
    #
    # GIVEN
    #

    if not activities_path.exists():
        pytest.skip(f"Test file not found: {activities_path}")

    activities_dict = persistences.load_json(file_path=activities_path)
    print(f"Loaded {len(activities_dict)} activities from:\n{activities_path}")

    activity_type_key_skip_list = [
        commons.AT_RIDE,
        commons.AT_ROW_ERG,
        commons.AT_ROW,
    ]

    #
    # WHEN
    #

    items = (
        activities_dict.values()
        if isinstance(activities_dict, dict)
        else activities_dict
    )
    for activity_data in items:
        if activity_data["activity_type_key"] not in activity_type_key_skip_list:
            activity_data["avg_watts"] = 0.0
            activity_data["max_watts"] = 0.0

    fixed_path = tmp_path / f"{activities_path.name}"
    persistences.save_json(file_path=fixed_path, data_dict=activities_dict)

    #
    # THEN
    #

    print(f"Saved fixed activities to:\nfile://{fixed_path}")


@pytest.mark.skip("MyTraL tool - not a test")
@pytest.mark.parametrize(
    "mytral_data_dir", [pathlib.Path(_given.EXT_TEST_DATA_ROOT / "development")]
)
@pytest.mark.tool
def test_patch_sport_2_activity_type_key(mytral_data_dir: pathlib.Path):
    """Patch activities: activity.activity_type_key > activity.activity_type_key"""

    #
    # GIVEN
    #

    data_path = mytral_data_dir / "data"
    user_dirs = [d for d in data_path.glob("*") if d.is_dir()]
    ds, user_ds = _given.given_ds(
        config.MytralConfig(
            persistence_data_dir=mytral_data_dir,
            persistence_cache=False,
        ),
    )

    for d in user_dirs:
        user_id = d.name
        print("User:", user_id)
        profile = user_ds.profile(user_id)

        #
        # WHEN gear
        #

        gear_path = d / "user-gear.json"
        if gear_path.exists():
            gear_list = persistences.load_json(gear_path)
            if not gear_list:
                continue

            for g in gear_list:
                print(f"  Gear: {g['name']}")

                if "activity_type_key" in g:
                    g["activity_type_key"] = g.pop("activity_type_key")

            # save changes
            persistences.save_json(file_path=gear_path, data_dict=gear_list)
        else:
            raise FileNotFoundError(f"Gear file does not exist at {gear_path}")

        #
        # WHEN activities
        #

        dataset_names = profile.dataset_names

        print("Datasets:")
        for d in dataset_names:
            if d == "lifelong":
                continue

            print(f"  {d}")
            d_path = user_ds._activities_dataset._ds_path(
                user_id=profile.user_id, dataset_name=d
            )
            print(f"    {d_path}")
            if not d_path.exists():
                raise FileNotFoundError(f"Dataset {d} not found at {d_path}")

            # patch the dataset
            d_list = persistences.load_json(d_path)
            # skip empty datasets
            if not d_list:
                continue

            for a in d_list:
                print(f"    {a['name']}")

                #
                # WHEN
                #

                if "activity_type_key" in a:
                    a["activity_type_key"] = a.pop("activity_type_key")

            # save changes
            persistences.save_json(file_path=d_path, data_dict=d_list)
