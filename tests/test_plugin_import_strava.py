# MyTraL: my trailing log
#
# Copyright (C) 2022-2026 Martin Dvorak <martin.dvorak@mindforger.com>
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

import pytest

from mytral import config
from mytral import plugins
from mytral.backends import entities
from mytral.integrations import strava
from tests import _given

_DIR_STRAVA_RAW_EXPORT = (
    f"{_given.EXT_TEST_DATA_ROOT}/digitalization-1996-2023/data-sources/dvorka"
    f"/strava.com"
)

# aliases
StravaActivitiesPlugin = strava.StravaActivitiesImportPlugin


@pytest.mark.skip("MyTraL tool - not a test")
@pytest.mark.parametrize(
    "import_strava_json_path,mytral_data_dir,user_id",
    [
        (
            pathlib.Path(
                f"{_DIR_STRAVA_RAW_EXPORT}/strava-raw-export-20240608-18h45m20s.json"
            ),
            pathlib.Path(f"{_given.EXT_TEST_DATA_ROOT}/digitalization-1996-2023"),
            "ba16be59-83ee-4999-9b37-d2c49e454135",
        ),
    ],
)
@pytest.mark.tool
def test_raw_import(
    tmp_path: pathlib.Path,
    import_strava_json_path: pathlib.Path,
    mytral_data_dir: pathlib.Path,
    user_id,
):
    #
    # GIVEN
    #

    print(f"Importing Strava dataset:\n  raw JSON: {import_strava_json_path}")

    # clone input/production data to test's work dir
    test_data_dir: pathlib.Path = tmp_path
    shutil.copytree(
        src=mytral_data_dir,
        dst=test_data_dir,
    )

    _, u_ds, user_profile = _given.given_test(
        config.MytralConfig(persistence_data_dir=test_data_dir),
        user_id=user_id,
    )

    result_path: pathlib.Path = pathlib.Path(
        f"{mytral_data_dir}/data/ba16be59-83ee-4999-9b37-d2c49e454135/"
        f"activities-{2023}.json"
    )

    #
    # WHEN
    #

    # plugins registry
    strava_plugin = plugins.registry.get_plugin(StravaActivitiesPlugin.NAME)

    # import
    activities: list[entities.ActivityEntity] = strava_plugin.import_activities(
        datasets={
            StravaActivitiesPlugin.USE_TYPE_STRAVA_JSON: import_strava_json_path,
        },
        user_profile=user_profile,
        output_path=result_path,
    )

    #
    # THEN
    #
    print("\nImported activities:")
    assert activities
    assert isinstance(activities, list)
    activities_dicts = [a.to_dict() for a in activities]
    print(json.dumps(activities_dicts, indent=2))

    print(f"\nImported activities ({len(activities)}) save to:")
    print(f"  file://{result_path}")


@pytest.mark.mytral
def test_strava_mapping_corrections():
    # GIVEN
    from mytral import commons
    from mytral.integrations import icommons

    # WHEN
    backcountry_mapping = icommons.STRAVA_TO_MYTRAL_AT.get("backcountryski")
    ebike_mapping = icommons.STRAVA_TO_MYTRAL_AT.get("ebikeride")

    # THEN
    assert backcountry_mapping == commons.AT_SKI_BACKCOUNTRY
    assert ebike_mapping == commons.AT_RIDE_E
    print("DONE: Strava mapping corrections verified")
