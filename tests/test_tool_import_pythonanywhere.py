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
import shutil
import uuid

import pytest

from mytral import persistences
from tests import _given
from tests import test_tool_dataset

"""Import PRODUCTION data from PythonAnywhere as new development/ data user profile."""


def _when_import_activity_file_1_0_0_to_1_1_0(
    src_ds_path: pathlib.Path, dst_ds_dir_path: pathlib.Path
):
    """Import the activity file.

    Parameters
    ----------
    src_ds_path : pathlib.Path
        Source dataset file path.
    dst_ds_dir_path : pathlib.Path
        Target dataset(s) dir path.

    """
    print(f"Importing file: {src_ds_path.name}")

    if not src_ds_path.name.startswith(
        "activities-"
    ) and not src_ds_path.name.startswith("user-"):
        print(f"Skipping file: {src_ds_path.name}")
        return

    tmp_ds_path = dst_ds_dir_path / src_ds_path.name
    shutil.copyfile(src_ds_path, tmp_ds_path)
    print(f"Copied to temporary file: {tmp_ds_path}")

    # RM SOCIAL: activities
    if src_ds_path.name.startswith("activities-"):
        print("PATCHING activities - removing social fields...")
        ds_dict = persistences.load_json(file_path=tmp_ds_path)
        social_fields = [
            "social_achievements",
            "social_kudos",
            "social_comments",
            "social_photos",
            "social_athletes",
            "social_prs",
        ]
        social_fields_removed = 0
        for activity_data in ds_dict.values():
            for field in social_fields:
                if field in activity_data:
                    del activity_data[field]
                    social_fields_removed += 1

        # replace seq- keys with UUIDs
        seq_keys_replaced = 0
        keys_to_replace = {}
        for key in ds_dict.keys():
            if key.startswith("seq-"):
                new_key = str(uuid.uuid4())
                keys_to_replace[key] = new_key

        for old_key, new_key in keys_to_replace.items():
            activity_data = ds_dict[old_key]
            activity_data["key"] = new_key
            ds_dict[new_key] = activity_data
            del ds_dict[old_key]
            seq_keys_replaced += 1

        persistences.save_json(file_path=tmp_ds_path, data_dict=ds_dict)
        print(f"  Removed {social_fields_removed} social fields from activities")
        print(f"  Replaced {seq_keys_replaced} seq- keys with UUIDs")
        return

    # RM STATS: outfits - remove count and save it back
    if src_ds_path.name == "user-outfits.json":
        print("PATCHING outfits...")
        ds_dict = persistences.load_json(file_path=tmp_ds_path)
        for entry_data in ds_dict.values():
            if "count" in entry_data:
                del entry_data["count"]
        persistences.save_json(file_path=tmp_ds_path, data_dict=ds_dict)
        return

    # RM STATS: symptoms
    if src_ds_path.name == "user-symptoms.json":
        print("PATCHING symptoms...")
        ds_dict = persistences.load_json(file_path=tmp_ds_path)
        for entry_data in ds_dict.values():
            if "count" in entry_data:
                del entry_data["count"]
        persistences.save_json(file_path=tmp_ds_path, data_dict=ds_dict)
        return

    # RM STATS: routes
    if src_ds_path.name == "user-routes.json":
        print("PATCHING routes...")
        ds_dict = persistences.load_json(file_path=tmp_ds_path)
        for entry_data in ds_dict.values():
            if "count" in entry_data:
                del entry_data["count"]
        persistences.save_json(file_path=tmp_ds_path, data_dict=ds_dict)
        return

    # RM STATS: gear
    if src_ds_path.name == "user-gear.json":
        print("PATCHING gear...")
        ds_dict = persistences.load_json(file_path=tmp_ds_path)
        stat_fields = [
            "stat_use",
            "stat_from",
            "stat_to",
            "stat_meters",
            "stat_km_str",
            "stat_seconds",
            "stat_duration_str",
        ]
        for entry_data in ds_dict.values():
            for field in stat_fields:
                if field in entry_data:
                    del entry_data[field]
        persistences.save_json(file_path=tmp_ds_path, data_dict=ds_dict)
        return

    # RM STATS: exercises
    if src_ds_path.name == "user-exercises.json":
        print("PATCHING exercises...")
        ds_dict = persistences.load_json(file_path=tmp_ds_path)
        for entry_data in ds_dict.values():
            if "count" in entry_data:
                del entry_data["count"]
        persistences.save_json(file_path=tmp_ds_path, data_dict=ds_dict)
        return

    # RM STATS: activity types
    if src_ds_path.name == "user-activity-types.json":
        print("PATCHING activity types...")
        ds_dict = persistences.load_json(file_path=tmp_ds_path)
        for entry_data in ds_dict.values():
            if "count" in entry_data:
                del entry_data["count"]
        persistences.save_json(file_path=tmp_ds_path, data_dict=ds_dict)
        return


@pytest.mark.skip("MyTraL tool - not a test")
@pytest.mark.parametrize(
    "src_ds_path",
    [
        # pathlib.Path(
        #     f"{_given.EXT_TEST_DATA_ROOT}/digitalization-1996-2023/"
        #     "data/ba16be59-83ee-4999-9b37-d2c49e454135/activities-1990.json"
        # ),
        # pathlib.Path(
        #     f"{_given.EXT_TEST_DATA_ROOT}/digitalization-1996-2023/"
        #     "wip-activities/activities-1992-paper-tsm.json"
        # ),
        pathlib.Path(
            f"{_given.EXT_TEST_DATA_ROOT}/digitalization-1996-2023/"
            "wip-activities/activities-1996-xls-and-paper.json"
        ),
    ],
)
@pytest.mark.mytral
def test_upgrade_activity_file_1_0_0_to_1_1_0(
    tmp_path: pathlib.Path, src_ds_path: pathlib.Path
):
    #
    # WHEN
    #
    _when_import_activity_file_1_0_0_to_1_1_0(
        src_ds_path=src_ds_path, dst_ds_dir_path=tmp_path
    )

    #
    # THEN
    #
    print(f"File converted to file://{tmp_path}")


@pytest.mark.skip("MyTraL tool - not a test")
@pytest.mark.mytral
def test_upgrade_1_0_0_to_1_1_0(tmp_path: pathlib.Path):
    """Import ``dvorka`` user v1.0.0 data from pythonanywhere/ to development/ as
    v1.1.0 data of a new user with a new UUID.

    """
    #
    # GIVEN
    #
    usr_dvorka_pa_uuid = "ba16be59-83ee-4999-9b37-d2c49e454135"
    new_usr_uuid = str(uuid.uuid4())
    new_usr_name = _given.given_random_name()
    new_usr_p = "040ba4cb5799777a1390dc523b34a1f2dae13ee4fcb913449dbfb2d820fa8f9a"  # 8a

    usr_base_path = pathlib.Path(
        f"{_given.EXT_TEST_DATA_ROOT}/pythonanywhere/data/{usr_dvorka_pa_uuid}"
    )
    dst_base_path = pathlib.Path(
        f"{_given.EXT_TEST_DATA_ROOT}/development/data/{new_usr_uuid}"
    )
    dst_base_path.mkdir(parents=True, exist_ok=True)

    #
    # WHEN
    #

    # gather year dataset names for user settings
    year_dataset_names = []

    # copy all .json files to temporary location
    tmp_ds_copy_path = tmp_path / "in-data"
    tmp_ds_copy_path.mkdir(parents=True, exist_ok=True)
    for src_ds_path in usr_base_path.glob("*.json"):
        _when_import_activity_file_1_0_0_to_1_1_0(
            src_ds_path=src_ds_path, dst_ds_dir_path=tmp_ds_copy_path
        )

    # process activities to YEAR centric datasets
    year_centric_ds_path = tmp_path / "year-centric-activities"
    year_centric_ds_path.mkdir(parents=True, exist_ok=True)
    test_tool_dataset.test_route_activities_to_year_datasets(
        tmp_path=year_centric_ds_path,
        src_ds_paths=[tmp_ds_copy_path],
    )

    # gather year dataset names from the generated files
    for year_ds_file in year_centric_ds_path.glob("activities-*.json"):
        # extract dataset name from file: activities-2024.json -> activities-2024
        dataset_name = year_ds_file.stem
        year_dataset_names.append(dataset_name)
    year_dataset_names.sort(reverse=True)
    print(f"Gathered year dataset names: {year_dataset_names}")

    # PATCH user settings with new user data and dataset names
    user_settings_path = tmp_ds_copy_path / "user-settings.json"
    if user_settings_path.exists():
        ds_dict = persistences.load_json(file_path=user_settings_path)
        ds_dict["user_id"] = new_usr_uuid
        ds_dict["user"] = new_usr_name
        ds_dict["password_enc"] = new_usr_p
        ds_dict["dataset_name"] = "lifelong"
        ds_dict["dataset_names"] = year_dataset_names
        persistences.save_json(file_path=user_settings_path, data_dict=ds_dict)
        print(
            f"  PATCHED user settings with new user ID, name, and "
            f"{len(year_dataset_names)} dataset names."
        )

    # copy processed datasets to final location
    for src_ds_path in year_centric_ds_path.glob("*.json"):
        dst_ds_path = dst_base_path / src_ds_path.name
        shutil.copyfile(src_ds_path, dst_ds_path)
        print(f"COPIED activities to: {dst_ds_path}")
    # copy settings files
    for src_ds_path in tmp_ds_copy_path.glob("user-*.json"):
        dst_ds_path = dst_base_path / src_ds_path.name
        shutil.copyfile(src_ds_path, dst_ds_path)
        print(f"COPIED settings to: {dst_ds_path}")

    #
    # THEN
    #

    print(f"NEW user {new_usr_name} created in: file://{dst_base_path}")
