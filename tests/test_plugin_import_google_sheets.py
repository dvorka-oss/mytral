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
import pathlib
import shutil

import pytest

from mytral import cals
from mytral import commons
from mytral import config
from mytral import plugins
from mytral.backends import entities
from mytral.integrations import google_sheets
from tests import _given

# test datasets
_DIR_STRAVA_RAW_EXPORT = (
    f"{_given.EXT_TEST_DATA_ROOT}/digitalization-1996-2023/data-sources/dvorka"
    f"/strava.com"
)
_GSHEETS_ALL_YEARS_CSV = (
    _given.TEST_DATA_DIR / "import" / "google-sheets" / "gsheets-all-years-sample.csv"
)

# aliases
GSheetsPlugin = google_sheets.GoogleSheetsActivitiesImportPlugin

#
# Helpers
#


@pytest.mark.parametrize(
    "year,week,week_day",
    [
        (2024, 28, 0),  # Monday
        (2024, 28, 1),  # Tuesday
        (2024, 28, 2),  # Wednesday
        (2024, 28, 3),  # Thursday
        (2024, 28, 4),  # Friday
        (2024, 28, 5),  # Saturday
        (2024, 28, 6),  # Sunday
    ],
)
@pytest.mark.tool
def test_week_to_date_api(year, week, week_day):
    #
    # GIVEN
    #

    #
    # WHEN
    #
    r = cals.week_to_date(year=year, week=week, week_day=week_day)

    #
    # THEN
    print(r)


#
# Google Sheets all years plugin
#

AllYearsPlugin = google_sheets.GoogleSheetsAllYearsImportPlugin


@pytest.mark.mytral
def test_import_gdocs_all_years(tmp_path: pathlib.Path):
    """Import a Google Sheets all-years CSV and verify the resulting activities.

    Sample CSV contains two years:
    - 1999: running 300 km, rowing 100 km, bike 300 km, ski 100 km,
            swim 0:30:00, ukm 800 km  → 6 activities
    - 2000: running 400 km, rowing 0 (skipped), bike 400 km, ski 200 km,
            swim 1:00:00, ukm 1000 km → 5 activities
    Total: 11 activities.

    Verifies that:
    - all expected activities are created (activity types with 0 distance are skipped)
    - every activity is placed on January 1st of the correct year
    - activity type fields match the CSV columns
    - distance and src fields are populated correctly
    - rowing row with 0 distance is omitted for year 2000
    """
    #
    # GIVEN
    #
    _, _, user_profile = _given.given_test(
        config.MytralConfig(persistence_data_dir=tmp_path),
        user_id="test_gsheets_all_years_user",
    )
    all_years_plugin = plugins.registry.get_plugin(AllYearsPlugin.NAME)
    assert all_years_plugin is not None, "Google Sheets all-years plugin not found"

    output_path = tmp_path / "gsheets-all-years-activities.json"

    #
    # WHEN
    #
    imported: list[entities.ActivityEntity] = all_years_plugin.import_activities(
        datasets={
            AllYearsPlugin.USE_TYPE_GSHEETS_ALL_YEARS_CSV: _GSHEETS_ALL_YEARS_CSV
        },
        user_profile=user_profile,
        output_path=output_path,
    )

    #
    # THEN
    #
    assert imported, "No activities were imported from the all-years CSV"
    assert isinstance(imported, list)

    # 1999 has 6 activity types; 2000 has 5 (rowing=0 skipped)
    assert len(imported) == 11, f"Expected 11 activities, got {len(imported)}"

    print(f"\nImported {len(imported)} activitie(s) - DONE")

    # every activity must have a valid key, src, and January 1st date
    for a in imported:
        assert isinstance(a, entities.ActivityEntity)
        assert a.key, "Activity key must not be empty"
        assert a.name, "Activity name must not be empty"
        assert a.src == "gdocs-log-import-SUMMARY"
        assert a.when_month == 1
        assert a.when_day == 1
        assert a.when_year in (1999, 2000), f"Unexpected year: {a.when_year}"

    # collect activities by year
    acts_1999 = [a for a in imported if a.when_year == 1999]
    acts_2000 = [a for a in imported if a.when_year == 2000]
    assert len(acts_1999) == 6, f"Expected 6 activities for 1999, got {len(acts_1999)}"
    assert len(acts_2000) == 5, f"Expected 5 activities for 2000, got {len(acts_2000)}"

    # rowing (0 km) must not appear for year 2000
    activity_types_2000 = {a.activity_type_key for a in acts_2000}
    assert commons.AT_ROW not in activity_types_2000, "Rowing with 0 km must be skipped"

    # both years must contain the expected activity types
    activity_types_1999 = {a.activity_type_key for a in acts_1999}
    assert activity_types_1999 == {
        commons.AT_RUN,
        commons.AT_ROW,
        commons.AT_RIDE,
        commons.AT_SKI_F,
        commons.AT_SWIM,
        "ukm",
    }, f"Unexpected activity types for 1999: {activity_types_1999}"

    # spot-check 1999 running: 300 km → 300 000 m
    running_1999 = next(a for a in acts_1999 if a.activity_type_key == commons.AT_RUN)
    assert running_1999.distance == 300_000
    assert running_1999.activity_type_key == commons.AT_RUN
    assert running_1999.when_year == 1999
    print(
        f"1999 running: dist={running_1999.distance} m, "
        f"dur={running_1999.hours}h{running_1999.minutes:02}m{running_1999.seconds:02}s"
        f" - DONE"
    )

    # spot-check 1999 swimming: 0:30:00 → 1800 s → 1200 m
    swim_1999 = next(a for a in acts_1999 if a.activity_type_key == commons.AT_SWIM)
    assert swim_1999.distance == 1_200
    print(f"1999 swim: dist={swim_1999.distance} m - DONE")

    # spot-check 2000 ukm: 1000 km → 1 000 000 m
    ukm_2000 = next(a for a in acts_2000 if a.activity_type_key == "ukm")
    assert ukm_2000.distance == 1_000_000
    print(f"2000 ukm: dist={ukm_2000.distance} m - DONE")

    # verify output JSON was written
    assert output_path.exists(), "Output JSON file was not created"
    assert output_path.stat().st_size > 0, "Output JSON file is empty"

    print(f"Output JSON written to: {output_path} - DONE")


#
# Google Sheets plugins
#


@pytest.mark.skip("MyTraL tool - not a test")
@pytest.mark.parametrize(
    "year",
    [
        2023,
        2022,
        2021,
        2020,
        2019,
        2018,
        2017,
        2016,
        2015,
        2014,
        2013,  # Strava data: 2023 - 2013
        2012,  # ONLY comments from Google Sheets - km/hour/kg from paper OR totals
        2011,  # ONLY comments from Google Sheets - km/hour/kg from paper OR totals
        # TODO 2010, # ONLY comments from Google Sheets - km/hour/* from paper OR totals
    ],
)
@pytest.mark.tool
def test_import_year(tmp_path: pathlib.Path, year: int):
    #
    # GIVEN
    #
    import_gsheets_csv_path: pathlib.Path = pathlib.Path(
        f"{_given.EXT_TEST_DATA_ROOT}/digitalization-1996-2023/data-sources/dvorka/"
        f"google-sheets/Running & Rowing & Biking Log - {year}.csv"
    )
    import_strava_json_path: pathlib.Path = pathlib.Path(
        f"{_DIR_STRAVA_RAW_EXPORT}/strava-raw-export-20240608-18h45m20s.json"
    )
    mytral_data_dir: pathlib.Path = pathlib.Path(
        f"{_given.EXT_TEST_DATA_ROOT}/digitalization-1996-2023"
    )
    user_id = "ba16be59-83ee-4999-9b37-d2c49e454135"

    print(
        f"Importing datasets:"
        f"\n  CSV : {import_gsheets_csv_path}"
        f"\n  JSON: {import_strava_json_path}"
    )

    # clone input/production data to test's work dir
    test_data_dir: pathlib.Path = tmp_path / "test_data_dir"
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
        f"activities-{year}.json"
    )

    #
    # WHEN
    #

    # plugins registry
    gsheets_plugin = plugins.registry.get_plugin(GSheetsPlugin.NAME)

    # import
    activities = gsheets_plugin.import_activities(
        datasets={
            GSheetsPlugin.USE_TYPE_GSHEETS_CSV: import_gsheets_csv_path,
            GSheetsPlugin.USE_TYPE_STRAVA_JSON: import_strava_json_path,
        },
        user_profile=user_profile,
        output_path=result_path,
        # january_1st_name="🔴 GENERATED do not edit",
        # january_1st_description=(
        #     "DO NOT EDIT - this year activities were imported from the export "
        #     "Google Sheets training log and Strava activities. Import method will "
        #     "be incrementally improved and this year REWRITTEN - your changes "
        #     "would be LOST."
        # ),
    )

    #
    # THEN
    #
    print(f"\nImported {len(activities)} activitie(s)")
    assert activities
    assert isinstance(activities, list)

    print("\nImported activities saved to:")
    print(f"  file://{result_path}")
