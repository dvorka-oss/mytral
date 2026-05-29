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
import json
import pathlib
import shutil
import time

import msgpack
import pytest

from mytral import commons
from mytral import config
from tests import _given


@pytest.mark.skip(reason="This is benchmark, not a test.")
@pytest.mark.benchmark
def test_bench_json(tmp_path: pathlib.Path):
    """Benchmark of the JSON loading - lifelong.json

    Loaded lifelong.json:

      0.0484 seconds
      9030840B
      5017 entries

    Saved lifelong.json:

      0.1326 seconds

    CONCLUSION:

    - JSON loading / saving is NOT the bottleneck and/or expensive operation.

    """
    #
    # GIVEN
    #
    lifelong_path = (
        _given.EXT_TEST_DATA_ROOT
        / "development"
        / "data"
        / "ba16be59-83ee-4999-9b37-d2c49e454135"
        / "activities-2024.json"
    )

    #
    # WHEN
    #
    print(f"\nLoading {lifelong_path.absolute()}")
    start_time = time.perf_counter()
    with open(lifelong_path, "r") as file:
        lifelong_dict = json.load(file)
    end_time = time.perf_counter()
    load_duration = end_time - start_time

    save_path = tmp_path / "lifelong.json"
    print(f"\nSaving {save_path.absolute()}")
    start_time = time.perf_counter()
    with open(save_path, "w") as file:
        json.dump(lifelong_dict, file)
    end_time = time.perf_counter()
    save_duration = end_time - start_time

    #
    # THEN
    #
    print(
        f"Loaded {lifelong_path}:"
        f"\n  {load_duration:.4f} seconds"
        f"\n  {lifelong_path.stat().st_size / 1000}kB"
        f"\n  {len(lifelong_dict)} entries"
    )
    print(
        f"Saved {save_path}:"
        f"\n  {save_duration:.4f}s"
        f"\n  {save_path.stat().st_size / 1000}kB"
    )


@pytest.mark.skip(reason="This is benchmark, not a test.")
@pytest.mark.skipif(
    not (_given.EXT_TEST_DATA_ROOT / "development").exists(),
    reason="Test data not available",
)
@pytest.mark.mytral
def test_bench_json_dataset(tmp_path: pathlib.Path):
    """Test creation ond use of the JSON user dataset on the filesystem."""
    #
    # GIVEN
    #

    linux_local_data_dir = tmp_path / ".local"
    linux_local_data_dir.mkdir(parents=True, exist_ok=True)

    # dataset_name = "lifelong"
    dataset_name = "lifelong"

    lifelong_path = (
        _given.EXT_TEST_DATA_ROOT
        / "development"
        / "data"
        / "ba16be59-83ee-4999-9b37-d2c49e454135"
        / "activities-2024.json"
    )

    user_id = commons.DEFAULT_USER_NAME
    ds, user_ds, profile = _given.given_test(
        config.MytralConfig(persistence_data_dir=tmp_path),
        user_id=user_id,
    )

    user_dir = user_ds.user_dir(user_id)
    shutil.copy(
        src=lifelong_path,
        dst=user_dir / lifelong_path.name,
    )
    lifelong_activities = user_ds.list_activities(
        user_id=user_id, dataset_name=dataset_name
    )

    #
    # WHEN
    #

    user_ds._activities_dataset.persistence_sparse = True
    user_ds.update_activities(
        user_id=user_id,
        dataset_name="lifelong_copy",
        activities=lifelong_activities,
    )

    # TODO COPY raw dataset to user profile
    # TODO LOAD & SAVE dataset

    # TODO COPY raw dataset to user profile
    # TODO LOAD & SAVE dataset

    # TODO COPY raw dataset to user profile
    # TODO LOAD & SAVE dataset

    #
    # THEN
    #
    assert ds


@pytest.mark.skip(reason="This is benchmark, not a test.")
@pytest.mark.skipif(
    not (_given.EXT_TEST_DATA_ROOT / "development").exists(),
    reason="Test data not available",
)
@pytest.mark.mytral
def test_bench_msgpack(tmp_path: pathlib.Path):
    """Msgpack lifelong test:

    Loaded:
      9 138 427 B
    Saved :
      5 058 295 B
      0.0196s

    Conclusion:

      50% saved size
      10x faster save

    .tgz compression:

      620 107 B ... 6.78% > 14x more

    """
    #
    # GIVEN
    #
    lifelong_path = (
        _given.EXT_TEST_DATA_ROOT
        / "development"
        / "data"
        / "ba16be59-83ee-4999-9b37-d2c49e454135"
        / "activities-2024.json"
    )

    print(f"\nLoading {lifelong_path.absolute()}")
    with open(lifelong_path, "r") as file:
        lifelong_dict = json.load(file)

    save_path = tmp_path / "lifelong.json"

    #
    # WHEN
    #
    start_time = time.perf_counter()
    with open(save_path, "wb") as f:
        msgpack.pack(lifelong_dict, f)
    print(f"Successfully wrote dictionary to '{save_path}'.")
    end_time = time.perf_counter()
    save_duration = end_time - start_time

    print(f"Loaded:\n  {lifelong_path.stat().st_size}B")
    print(f"Saved :\n  {save_path.stat().st_size}B\n  {save_duration:.4f}s")
