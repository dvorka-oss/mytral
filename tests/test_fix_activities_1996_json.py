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


@pytest.mark.mytral
def test_convert_activities_1996_list_to_dict():
    """Convert activities-1996.json from list to dict where key is activity's key."""
    #
    # GIVEN
    #

    source_file = pathlib.Path(".VIBE_ATTIC/activities-1996.json")
    if not source_file.exists():
        pytest.skip(f"File {source_file} does not exist")

    with open(source_file, "r") as f:
        activities_list = json.load(f)

    print(f"\nProcessing {source_file}")
    print(f"Found {len(activities_list)} activities in list format")

    #
    # WHEN
    #

    activities_dict = {}
    for activity in activities_list:
        activity_key = activity.get("key")
        if not activity_key:
            raise ValueError(f"Activity without 'key' field found: {activity}")

        if activity_key in activities_dict:
            raise ValueError(f"Duplicate activity key found: {activity_key}")

        activities_dict[activity_key] = activity

    output_file = source_file.with_name("activities-1996-fixed.json")
    with open(output_file, "w") as f:
        json.dump(activities_dict, f, indent=2)

    print(f"Converted {len(activities_dict)} activities to dict format")
    print(f"Output file: {output_file}")

    #
    # THEN
    #

    assert len(activities_dict) == len(activities_list), (
        "Number of activities should match"
    )

    with open(output_file, "r") as f:
        verified_data = json.load(f)

    assert isinstance(verified_data, dict), "Output should be a dictionary"

    for key, activity in verified_data.items():
        assert activity["key"] == key, (
            f"Activity key mismatch: {key} != {activity['key']}"
        )

    print(f"SUCCESS: Converted {len(activities_dict)} activities from list to dict")
    print("All activities have matching keys")
