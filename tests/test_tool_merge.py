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
from mytral import tools
from tests import _given


@pytest.mark.skip("MyTraL tool - not a test")
@pytest.mark.tool
def test_merge_all_2_main(tmp_path: pathlib.Path):
    """Development version of the tool to merge all JSON datasets to
    ``lifelong.json``. Replaced by ``mytral.tools.merge_datasets()``.

    """

    #
    # GIVEN
    #
    _, ds, profile = _given.given_test(
        config.MytralConfig(persistence_data_dir=tmp_path)
    )

    # datasets
    _given.given_test_datasets(
        profile=profile,
        ds=ds,
        datasets=[
            pathlib.Path(
                f"data/{commons.DEFAULT_USER_NAME}/dataset-layer-sick-sauna-m.json"
            ),
            pathlib.Path(f"data/{commons.DEFAULT_USER_NAME}/dataset-1996-10-xls.json"),
        ],
    )

    #
    # WHEN
    #

    # merge datasets to main
    tools.merge_datasets(
        user_id=profile.user_id,
        ds=ds,
        dataset_names=None,
    )

    #
    # THEN
    #
    print("MERGED datasets:")
    ds.list_activities(user_id=profile.user_id, dataset_name="lifelong")


@pytest.mark.skip("MyTraL tool - not a test")
@pytest.mark.tool
def test_join_strava_to_manual(tmp_path: pathlib.Path):
    """Merge given rich dataset (like Strava export) to another given dataset (like
    manually created one).

    """

    #
    # GIVEN
    #
    src_dataset = pathlib.Path("tests") / "data" / "dataset-join-src.json"
    dst_dataset = pathlib.Path("tests") / "data" / "dataset-join-dst.json"

    (_, ds, profile) = _given.given_test(
        test_config=config.MytralConfig(persistence_data_dir=tmp_path),
        user_id=_given.TEST_USER,
    )

    profile.dataset_name = dst_dataset.stem
    profile.dataset_names = []
    _given.given_test_datasets(
        profile=profile,
        ds=ds,
        datasets=[src_dataset, dst_dataset],
    )

    #
    # WHEN
    #

    tools.join_datasets(
        user_id=profile.user_id,
        src_dataset_name=src_dataset.stem,
        dst_dataset_name=dst_dataset.stem,
        ds=ds,
    )

    #
    # THEN
    #
    print(f"JOINED dataset {src_dataset} to {dst_dataset}:")
    ds.list_activities(user_id=profile.user_id, dataset_name=dst_dataset.stem)
