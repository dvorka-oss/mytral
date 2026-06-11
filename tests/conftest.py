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
import os
import pathlib

import pytest

from tests import _given


@pytest.fixture(scope="session")
def mytral_user() -> str:
    """A test username."""
    return _given.TEST_USER


@pytest.fixture(scope="session")
def mytral_test_data_path() -> pathlib.Path | None:
    """Path to production-like data - comprehensive multi-user dataset. The dataset
    contains personal data, therefore it is not part of the repository.

    Returns
    -------
    pathlib.Path :
        Path to the test data directory. By default, it is `tests/data/`, but can be
        overridden by the `MYTRAL_TEST_DATA_DIR` environment variable.

    """
    env_val = os.getenv(_given.ENV_DIR_MYTRAL_TEST_DATA)

    return pathlib.Path(env_val) if env_val else None
