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

from mytral import commons
from mytral import config
from mytral import plugins
from mytral.integrations import google_sheets
from tests import _given

# aliases
GSheetsRacesPlugin = google_sheets.GoogleSheetsRacesImportPlugin


@pytest.mark.skip
@pytest.mark.skipif(
    _given.ENV_DIR_MYTRAL_TEST_DATA not in os.environ,
    reason="Test data directory environment variable not set",
)
@pytest.mark.mytral
def test_import_gdocs_races(tmp_path: pathlib.Path, mytral_test_data_path):
    #
    # GIVEN
    #

    if mytral_test_data_path is None:
        pytest.skip("MYTRAL_TEST_DATA_DIR environment variable not set")

    _, ds = _given.given_ds(
        test_config=config.MytralConfig(persistence_data_dir=tmp_path)
    )
    user_id = commons.DEFAULT_USER_NAME
    ds.register_new_user(user_name=user_id, user_id=user_id)
    user_profile = ds.profile(user_id)

    races_csv = (
        mytral_test_data_path
        / "digitalization-1996-2023"
        / "data-sources"
        / "dvorka"
        / "google-sheets"
        / "Running & Rowing & Biking Log - Races.csv"
    )
    result_path = tmp_path / "imported-activities.json"

    #
    # WHEN
    #

    # plugins registry
    gsheets_plugin = plugins.registry.get_plugin(GSheetsRacesPlugin.NAME)

    # import
    activities = gsheets_plugin.import_activities(
        datasets={
            GSheetsRacesPlugin.USE_TYPE_GSHEETS_CSV: races_csv,
        },
        user_profile=user_profile,
        output_path=result_path,
    )

    #
    # THEN
    #
    print(f"\nImported {len(activities)} activities")
    assert activities
    assert isinstance(activities, list)

    print("\nImported activities saved to:")
    print(f"  file://{result_path}")
