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

import pytest

from tests import _given

# production data directory
_PDD = f"{_given.TEST_USER_HOME}/p/mytral/git/my-training-log-data-PRODUCTION"


@pytest.mark.skip("MyTraL tool - not a test: upgrade dict to list format")
@pytest.mark.parametrize(
    "source_dir",
    [
        pathlib.Path(
            f"{_given.EXT_TEST_DATA_ROOT}/development"
            f"/data/ba16be59-83ee-4999-9b37-d2c49e454135"
        ),
        pathlib.Path(
            f"{_given.EXT_TEST_DATA_ROOT}/development"
            f"/data/444f1e55-7953-4eaf-a393-41f2f9c28cf3"
        ),
        pathlib.Path(
            f"{_given.EXT_TEST_DATA_ROOT}/digitalization-1996-2023"
            f"/data/ba16be59-83ee-4999-9b37-d2c49e454135"
        ),
        pathlib.Path(
            f"{_PDD}/pythonanywhere/data/ba16be59-83ee-4999-9b37-d2c49e454135"
        ),
    ],
)
@pytest.mark.tool
def test_upgrade_dict_to_list_format(tmp_path: pathlib.Path, source_dir: pathlib.Path):
    """Upgrade all JSON files from dict to list format.

    This tool upgrades the following files:
    - activities-*.json (all years)
    - user-activity-types.json
    - user-exercises.json
    - user-gear.json
    - user-goals.json
    - user-laps.json
    - user-outfits.json
    - user-symptoms.json

    The upgraded files are saved to tmp_path with the same filenames.
    """
    #
    # GIVEN
    #

    # Define patterns for files to upgrade
    file_patterns = [
        "activities-*.json",
        "user-activity-types.json",
        "user-exercises.json",
        "user-gear.json",
        "user-goals.json",
        "user-laps.json",
        "user-outfits.json",
        "user-symptoms.json",
    ]

    # Files to skip (already in correct format or special handling)
    skip_files = [
        "user-settings.json",
        "user-gear-strava.json",
    ]

    all_files = []
    for pattern in file_patterns:
        all_files.extend(source_dir.glob(pattern))

    # Filter out skipped files
    files_to_process = [f for f in all_files if f.name not in skip_files]

    assert files_to_process, f"No files found to upgrade in {source_dir}"

    print(f"\nUpgrading {len(files_to_process)} files from {source_dir}")
    print(f"Output directory: {tmp_path}")

    #
    # WHEN
    #

    total_files_processed = 0
    total_entries_converted = 0

    for file_path in files_to_process:
        print(f"\nProcessing {file_path.name}...")

        with open(file_path, "r") as f:
            data = json.load(f)

        # Check if already in list format
        if isinstance(data, list):
            print("  DONE Already in list format, copying as-is")
            output_file = tmp_path / file_path.name
            with open(output_file, "w") as f:
                json.dump(data, f, indent=4)
            total_files_processed += 1
            continue

        # Convert from dict to list format
        if isinstance(data, dict):
            entries_count = len(data)

            # Convert: extract values (which contain the 'key' attribute)
            list_data = list(data.values())

            # Verify all entries have 'key' attribute
            for i, entry in enumerate(list_data):
                if "key" not in entry:
                    raise ValueError(
                        f"Entry {i} in {file_path.name} missing 'key' attribute"
                    )

            # Save to output
            output_file = tmp_path / file_path.name
            with open(output_file, "w") as f:
                json.dump(list_data, f, indent=4)

            print(f"  DONE Converted {entries_count} entries from dict to list")
            total_files_processed += 1
            total_entries_converted += entries_count
        else:
            raise ValueError(f"Unexpected data type in {file_path.name}: {type(data)}")

    #
    # THEN
    #

    print(f"\n{'=' * 60}")
    print("UPGRADE COMPLETE")
    print(f"{'=' * 60}")
    print(f"Files processed: {total_files_processed}")
    print(f"Entries converted: {total_entries_converted}")
    print(f"Output directory: {tmp_path}")
    print(f"{'=' * 60}")

    # Verify output
    assert total_files_processed > 0, "No files were processed"

    # Verify all output files are in list format
    for file_path in files_to_process:
        output_file = tmp_path / file_path.name
        assert output_file.exists(), f"Output file not created: {output_file.name}"

        with open(output_file, "r") as f:
            output_data = json.load(f)

        assert isinstance(output_data, list), (
            f"{output_file.name} should be a list, got {type(output_data)}"
        )

        # Verify all entries have 'key' attribute
        for i, entry in enumerate(output_data):
            assert "key" in entry, (
                f"Entry {i} in {output_file.name} missing 'key' attribute"
            )

    print("\nDONE All files verified successfully")
    print(f"\nTo use upgraded files, copy from:\n  {tmp_path}\nto:\n  {source_dir}")


@pytest.mark.skip("MyTraL tool - not a test: remove STATS fields from settings")
@pytest.mark.parametrize(
    "source_dir",
    [
        pathlib.Path(
            f"{_given.EXT_TEST_DATA_ROOT}/development"
            f"/data/ba16be59-83ee-4999-9b37-d2c49e454135"
        ),
        pathlib.Path(
            f"{_given.EXT_TEST_DATA_ROOT}/development"
            f"/data/444f1e55-7953-4eaf-a393-41f2f9c28cf3"
        ),
        pathlib.Path(
            f"{_given.EXT_TEST_DATA_ROOT}/digitalization-1996-2023"
            f"/data/ba16be59-83ee-4999-9b37-d2c49e454135"
        ),
        pathlib.Path(
            f"{_PDD}/pythonanywhere/data/ba16be59-83ee-4999-9b37-d2c49e454135"
        ),
    ],
)
@pytest.mark.tool
def test_remove_settings_stats_fields(tmp_path: pathlib.Path, source_dir: pathlib.Path):
    """Remove STATS fields (like count) from user-*.json files in given dataset dir."""
    #
    # GIVEN
    #

    stats_fields = [
        "count",
        "stat_use",
        "stat_from",
        "stat_to",
        "stat_meters",
        "stat_km_str",
        "stat_seconds",
        "stat_duration_str",
    ]

    settings_files = list(source_dir.glob("user-*.json"))
    assert settings_files, f"No settings files found in {source_dir}"

    print(f"\n  Processing {len(settings_files)} settings files from {source_dir}")

    #
    # WHEN
    #

    total_entries = 0
    total_stats_fields_removed = 0

    for f in settings_files:
        print(f"Processing {f.name}...")
        if "user-settings.json" in str(f) or "user-gear-strava.json" in str(f):
            print(f"  Skipping {f}")
            continue

        with open(f, "r") as f:
            data = json.load(f)

        entries_processed = 0
        stats_fields_removed = 0

        for entry_key, entry_data in data.items():
            entries_processed += 1

            for field in stats_fields:
                if field in entry_data:
                    del entry_data[field]
                    stats_fields_removed += 1

        total_entries += entries_processed
        total_stats_fields_removed += stats_fields_removed

        output_file = tmp_path / f.name
        print(f"  Saving {output_file}")
        with open(output_file, "w") as f:
            json.dump(data, f, indent=4)

        print(
            f"  Processed {entries_processed} entries, removed {stats_fields_removed} "
            f"stats fields"
        )

    #
    # THEN
    #

    print(f"\nTotal: {total_entries} entries processed")
    print(f"Total: {total_stats_fields_removed} stats fields removed")
    print(f"Output directory: {tmp_path}")

    assert total_entries > 0, "No entries were processed"


@pytest.mark.skip("MyTraL tool - not a test: remove SOCIAL fields from activities")
@pytest.mark.parametrize(
    "source_dir",
    [
        pathlib.Path(
            f"{_given.EXT_TEST_DATA_ROOT}/development"
            f"/data/ba16be59-83ee-4999-9b37-d2c49e454135"
        ),
        pathlib.Path(
            f"{_given.EXT_TEST_DATA_ROOT}/development"
            f"/data/444f1e55-7953-4eaf-a393-41f2f9c28cf3"
        ),
        pathlib.Path(
            f"{_given.EXT_TEST_DATA_ROOT}/digitalization-1996-2023"
            f"/data/ba16be59-83ee-4999-9b37-d2c49e454135"
        ),
        pathlib.Path(
            f"{_given.EXT_TEST_DATA_ROOT}/pythonanywhere"
            f"/data/ba16be59-83ee-4999-9b37-d2c49e454135"
        ),
        pathlib.Path(
            f"{_PDD}/pythonanywhere/data/ba16be59-83ee-4999-9b37-d2c49e454135"
        ),
    ],
)
@pytest.mark.tool
def test_remove_social_fields(tmp_path: pathlib.Path, source_dir: pathlib.Path):
    """Remove social_* fields from activity JSON files.

    This test upgrades activity JSON files by removing all social_* fields
    that are no longer part of the ActivityEntity model.
    """
    #
    # GIVEN
    #

    social_fields = [
        "social_achievements",
        "social_kudos",
        "social_comments",
        "social_photos",
        "social_athletes",
        "social_prs",
    ]

    activity_files = list(source_dir.glob("activities-*.json"))
    assert activity_files, f"No activity files found in {source_dir}"

    print(f"\nProcessing {len(activity_files)} activity files from {source_dir}")

    #
    # WHEN
    #

    total_activities = 0
    total_social_fields_removed = 0

    for activity_file in activity_files:
        print(f"Processing {activity_file.name}...")

        with open(activity_file, "r") as f:
            data = json.load(f)

        activities_processed = 0
        social_fields_removed = 0

        items = data.items() if isinstance(data, dict) else data
        for activity_data in items:
            activities_processed += 1

            for field in social_fields:
                if field in activity_data:
                    del activity_data[field]
                    social_fields_removed += 1

        total_activities += activities_processed
        total_social_fields_removed += social_fields_removed

        output_file = tmp_path / activity_file.name
        with open(output_file, "w") as f:
            json.dump(data, f, indent=4)

        print(
            f"  Processed {activities_processed} activities, "
            f"removed {social_fields_removed} social fields"
        )

    #
    # THEN
    #

    print(f"\nTotal: {total_activities} activities processed")
    print(f"Total: {total_social_fields_removed} social fields removed")
    print(f"Output directory: {tmp_path}")

    assert total_activities > 0, "No activities were processed"

    output_files = list(tmp_path.glob("activities-*.json"))
    assert len(output_files) == len(activity_files), (
        f"Expected {len(activity_files)} output files, got {len(output_files)}"
    )

    for output_file in output_files:
        with open(output_file, "r") as f:
            data = json.load(f)

        items = data.items() if isinstance(data, dict) else data
        for activity_data in items:
            for field in social_fields:
                assert field not in activity_data, (
                    f"Social field '{field}' still present in {output_file.name}"
                )

    print("SUCCESS: All social fields removed and verified")
