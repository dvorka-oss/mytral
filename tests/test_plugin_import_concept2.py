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
from mytral import plugins
from mytral.backends import entities
from mytral.integrations import concept2
from tests import _given

# path to the bundled test CSV (51 workout rows from the 2008/2009 season)
_DIR_TESTS = pathlib.Path(__file__).parent
_CONCEPT2_CSV = _DIR_TESTS / "data" / "import" / "concept2" / "concept2-season-2009.csv"

# alias for brevity
C2Plugin = concept2.Concept2ActivitiesImportPlugin


@pytest.mark.mytral
def test_import_concept2_csv(tmp_path: pathlib.Path):
    """Import a Concept2 CSV export and verify the resulting activities.

    Verifies that:
    - all rows are converted to ActivityEntity instances
    - each activity has the correct activity type (erg_row)
    - ranked workouts have intensity "race", unranked have "easy"
    - distance, duration and source fields are populated correctly
    """
    #
    # GIVEN
    #
    _, _, user_profile = _given.given_test(
        config.MytralConfig(persistence_data_dir=tmp_path),
        user_id="test_concept2_user",
    )
    c2_plugin = plugins.registry.get_plugin(C2Plugin.NAME)
    assert c2_plugin is not None, "Concept2 plugin not found in registry"

    output_path = tmp_path / "concept2-activities.json"

    #
    # WHEN
    #
    imported: list[entities.ActivityEntity] = c2_plugin.import_activities(
        datasets={C2Plugin.USE_TYPE_CONCEPT2_CSV: _CONCEPT2_CSV},
        user_profile=user_profile,
        output_path=output_path,
    )

    #
    # THEN
    #
    assert imported, "No activities were imported from the Concept2 CSV"
    assert isinstance(imported, list)

    # the test CSV has 51 data rows
    assert len(imported) == 51, f"Expected 51 activities, got {len(imported)}"

    print(f"\nImported {len(imported)} activitie(s) - DONE")

    # every activity must be an ActivityEntity with erg_row activity type
    for a in imported:
        assert isinstance(a, entities.ActivityEntity)
        assert a.activity_type_key == commons.AT_ROW_ERG, (
            f"Expected activity type '{commons.AT_ROW_ERG}', "
            f"got '{a.activity_type_key}'"
        )
        assert a.key, "Activity key must not be empty"
        assert a.name, "Activity name must not be empty"
        assert a.src == "concept2-import"
        assert a.src_key.startswith("concept2:")
        assert a.src_url.startswith("https://log.concept2.com/profile/log/")

    # check ranked / unranked intensity mapping
    ranked_activities = [a for a in imported if a.ranked]
    unranked_activities = [a for a in imported if not a.ranked]

    assert ranked_activities, "Expected at least one ranked activity in test data"
    assert unranked_activities, "Expected at least one unranked activity in test data"

    for a in ranked_activities:
        assert a.intensity == commons.INTENSITY_RACE, (
            f"Ranked activity '{a.name}' should have intensity 'race', "
            f"got '{a.intensity}'"
        )
    for a in unranked_activities:
        assert a.intensity == commons.INTENSITY_EASY, (
            f"Unranked activity '{a.name}' should have intensity 'easy', "
            f"got '{a.intensity}'"
        )

    # spot-check the very first row from the CSV (ID 8713196)
    first = imported[0]
    assert "5,000m row" in first.name
    assert first.distance == 5_000
    assert first.hours == 0
    assert first.minutes == 20
    assert first.seconds == 0
    assert first.kcal == 332
    assert first.when_year == 2008
    assert first.when_month == 12
    assert first.when_day == 11
    assert first.src_key == "concept2:8713196"
    assert "2:00.0/500m" in first.description
    assert "(BBC right" in first.description

    # verify output JSON was written
    assert output_path.exists(), "Output JSON file was not created"
    assert output_path.stat().st_size > 0, "Output JSON file is empty"

    print(f"Output JSON written to: {output_path} - DONE")
