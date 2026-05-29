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
import uuid

import pytest

from mytral import persistences
from tests import _given


@pytest.mark.skip("MyTraL tool - not a test")
@pytest.mark.parametrize(
    "src_ds_paths",
    [
        [
            f"{_given.EXT_TEST_DATA_ROOT}/pythonanywhere/data"
            f"/ba16be59-83ee-4999-9b37-d2c49e454135/activities-2024-2025.json"
        ],
        [
            f"{_given.EXT_TEST_DATA_ROOT}/development/data"
            f"/ba16be59-83ee-4999-9b37-d2c49e454135/activities-2024-2025.json"
        ],
        [
            f"{_given.EXT_TEST_DATA_ROOT}/development/data"
            f"/ba16be59-83ee-4999-9b37-d2c49e454135"
        ],
    ],
)
@pytest.mark.tool
def test_route_activities_to_year_datasets(
    tmp_path: pathlib.Path, src_ds_paths: list[pathlib.Path]
):
    """Read given JSON dataset(s) and move it activities to the right
    activities-YYYY.json dataset.

    """
    #
    # GIVEN
    #

    if len(src_ds_paths) == 1 and pathlib.Path(src_ds_paths[0]).is_dir():
        src_ds_paths = list(pathlib.Path(src_ds_paths[0]).glob("activities-*.json"))
    else:
        new_src_ds_paths = []
        for src_ds_path in src_ds_paths:
            new_src_ds_paths.append(pathlib.Path(src_ds_path))
        src_ds_paths = new_src_ds_paths

    print(f"Processing datasets:\n{src_ds_paths}")

    # dict: filename -> list
    dst_ds_dicts = {}

    #
    # WHEN
    #
    for src_ds_path in src_ds_paths:
        src_ds_dict = persistences.load_json(file_path=src_ds_path)
        items = src_ds_dict.items() if isinstance(src_ds_dict, dict) else src_ds_dict
        for v in items:
            year = v.get("when_year")
            if year:
                ds_filename = f"activities-{year}.json"
            else:
                raise RuntimeError(f"Invalid year: '{year}'")
            if ds_filename not in dst_ds_dicts:
                dst_ds_dicts[ds_filename] = []

            # fresh key
            v["key"] = str(uuid.uuid4())
            dst_ds_dicts[ds_filename].append(v)

    # save them all
    print("\nSaving DATASETS...")
    for filename in dst_ds_dicts:
        dst_ds_path = tmp_path / filename
        persistences.save_json(file_path=dst_ds_path, data_dict=dst_ds_dicts[filename])
        print(f"  file://{dst_ds_path}")

    #
    # THEN
    #

    print("DONE")
