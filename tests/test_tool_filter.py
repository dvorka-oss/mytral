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

from mytral import app_logger
from mytral import commons
from mytral import config
from mytral import tools
from tests import _given


@pytest.mark.skip("MyTraL tool - not a test")
@pytest.mark.tool
def test_filter_dataset(tmp_path: pathlib.Path):
    """Filter dataset to contain only specific activities from given range."""

    #
    # GIVEN
    #

    dataset_name = "dataset-2024-05-13--2024-12-31-manual-thrombosis"
    do_extract = False
    filter_newer_str = "2024-05-11"  # including this date
    filter_older_str = "2024-12-31"  # including this date

    _, ds, profile = _given.given_test(
        config.MytralConfig(persistence_data_dir=tmp_path),
        user_id=commons.DEFAULT_USER_NAME,
    )

    #
    # WHEN
    #

    filtered_dataset_path = tools.filter_date_range_dataset(
        user_id=profile.user_id,
        ds=ds,
        filter_newer_str=filter_newer_str,
        filter_older_str=filter_older_str,
        src_dataset_name=dataset_name,
        do_extract=do_extract,
    )

    #
    # THEN
    #

    app_logger.info(f"Filtered dataset saved to:\n  file://{filtered_dataset_path}")
