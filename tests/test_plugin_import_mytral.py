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

from mytral import config
from mytral import plugins
from mytral import settings
from mytral.backends import entities
from mytral.integrations import imytral
from tests import _given

_DIR_DATA = pathlib.Path(__file__).parent / "data" / "import" / "mytral"

MPlugin = imytral.MyTraLImportPlugin


@pytest.mark.mytral
def test_import_mytral_activities_json(tmp_path: pathlib.Path):
    """Import MyTraL activities JSON and verify deserialized entities.

    Verifies that:
    - all records are converted to ActivityEntity instances
    - activity type and description fields are populated correctly
    """
    #
    # GIVEN
    #
    _, _, user_profile = _given.given_test(
        config.MytralConfig(persistence_data_dir=tmp_path),
        user_id="test_mytral_activities_user",
    )
    plugin = plugins.registry.get_plugin(MPlugin.NAME)
    assert plugin is not None, "MyTraL import plugin not found in registry"

    #
    # WHEN
    #
    result = plugin.import_entities(
        datasets={MPlugin.USE_TYPE_JSON: _DIR_DATA / "mytral-activities.json"},
        user_profile=user_profile,
    )

    #
    # THEN
    #
    assert plugins.MytralEntityType.ACTIVITIES in result
    imported = result[plugins.MytralEntityType.ACTIVITIES]
    assert len(imported) == 2, f"Expected 2 activities, got {len(imported)}"

    activity_type_keys = {a.activity_type_key for a in imported}
    assert "run" in activity_type_keys
    assert "ride" in activity_type_keys

    assert all(isinstance(a, entities.ActivityEntity) for a in imported)
    print(f"\nImported {len(imported)} activitie(s) - DONE")


@pytest.mark.mytral
def test_import_mytral_activity_types_json(tmp_path: pathlib.Path):
    """Import MyTraL activity types JSON and verify deserialized entities.

    Verifies that:
    - all records are converted to ActivityType instances
    - name and key fields are populated correctly
    """
    #
    # GIVEN
    #
    _, _, user_profile = _given.given_test(
        config.MytralConfig(persistence_data_dir=tmp_path),
        user_id="test_mytral_activity_types_user",
    )
    plugin = plugins.registry.get_plugin(MPlugin.NAME)

    #
    # WHEN
    #
    result = plugin.import_entities(
        datasets={MPlugin.USE_TYPE_JSON: _DIR_DATA / "mytral-activity-types.json"},
        user_profile=user_profile,
    )

    #
    # THEN
    #
    assert plugins.MytralEntityType.ACTIVITY_TYPES in result
    imported = result[plugins.MytralEntityType.ACTIVITY_TYPES]
    assert len(imported) == 2, f"Expected 2 activity types, got {len(imported)}"

    names = {at.name for at in imported}
    assert "Running" in names

    assert all(isinstance(at, settings.ActivityType) for at in imported)
    print(f"\nImported {len(imported)} activity type(s) - DONE")


@pytest.mark.mytral
def test_import_mytral_components_json(tmp_path: pathlib.Path):
    """Import MyTraL component templates JSON and verify deserialized entities.

    Verifies that:
    - all records are converted to ComponentTemplate instances
    - default_service_km is populated correctly
    """
    #
    # GIVEN
    #
    _, _, user_profile = _given.given_test(
        config.MytralConfig(persistence_data_dir=tmp_path),
        user_id="test_mytral_components_user",
    )
    plugin = plugins.registry.get_plugin(MPlugin.NAME)

    #
    # WHEN
    #
    result = plugin.import_entities(
        datasets={MPlugin.USE_TYPE_JSON: _DIR_DATA / "mytral-components.json"},
        user_profile=user_profile,
    )

    #
    # THEN
    #
    assert plugins.MytralEntityType.COMPONENTS in result
    imported = result[plugins.MytralEntityType.COMPONENTS]
    assert len(imported) == 2, f"Expected 2 component templates, got {len(imported)}"

    names = {ct.name for ct in imported}
    assert "Drive chain" in names

    first = next(c for c in imported if c.name == "Drive chain")
    assert first.default_service_km == 3000

    assert all(isinstance(ct, settings.ComponentTemplate) for ct in imported)
    print(f"\nImported {len(imported)} component template(s) - DONE")


@pytest.mark.mytral
def test_import_mytral_exercises_json(tmp_path: pathlib.Path):
    """Import MyTraL exercises JSON and verify deserialized entities.

    Verifies that:
    - all records are converted to Exercise instances
    - muscle_groups are populated correctly
    """
    #
    # GIVEN
    #
    _, _, user_profile = _given.given_test(
        config.MytralConfig(persistence_data_dir=tmp_path),
        user_id="test_mytral_exercises_user",
    )
    plugin = plugins.registry.get_plugin(MPlugin.NAME)

    #
    # WHEN
    #
    result = plugin.import_entities(
        datasets={MPlugin.USE_TYPE_JSON: _DIR_DATA / "mytral-exercises.json"},
        user_profile=user_profile,
    )

    #
    # THEN
    #
    assert plugins.MytralEntityType.EXERCISES in result
    imported = result[plugins.MytralEntityType.EXERCISES]
    assert len(imported) == 2, f"Expected 2 exercises, got {len(imported)}"

    names = {ex.name for ex in imported}
    assert "Push-up" in names

    pushup = next(ex for ex in imported if ex.name == "Push-up")
    assert "pecs" in pushup.muscle_groups

    assert all(isinstance(ex, settings.Exercise) for ex in imported)
    print(f"\nImported {len(imported)} exercise(s) - DONE")


@pytest.mark.mytral
def test_import_mytral_gear_json(tmp_path: pathlib.Path):
    """Import MyTraL gear JSON and verify deserialized entities.

    Verifies that:
    - all records are converted to Gear instances
    - vendor and activity type fields are populated correctly
    """
    #
    # GIVEN
    #
    _, _, user_profile = _given.given_test(
        config.MytralConfig(persistence_data_dir=tmp_path),
        user_id="test_mytral_gear_user",
    )
    plugin = plugins.registry.get_plugin(MPlugin.NAME)

    #
    # WHEN
    #
    result = plugin.import_entities(
        datasets={MPlugin.USE_TYPE_JSON: _DIR_DATA / "mytral-gear.json"},
        user_profile=user_profile,
    )

    #
    # THEN
    #
    assert plugins.MytralEntityType.GEARS in result
    imported = result[plugins.MytralEntityType.GEARS]
    assert len(imported) == 2, f"Expected 2 gear items, got {len(imported)}"

    vendors = {g.vendor for g in imported}
    assert "Nike" in vendors

    shoes = next(g for g in imported if g.vendor == "Nike")
    assert shoes.activity_type_key == "run"
    assert shoes.retired is False

    assert all(isinstance(g, settings.Gear) for g in imported)
    print(f"\nImported {len(imported)} gear item(s) - DONE")


@pytest.mark.mytral
def test_import_mytral_goals_json(tmp_path: pathlib.Path):
    """Import MyTraL goals JSON and verify deserialized entities.

    Verifies that:
    - all records are converted to Goal instances
    - urgency and importance fields are populated correctly
    """
    #
    # GIVEN
    #
    _, _, user_profile = _given.given_test(
        config.MytralConfig(persistence_data_dir=tmp_path),
        user_id="test_mytral_goals_user",
    )
    plugin = plugins.registry.get_plugin(MPlugin.NAME)

    #
    # WHEN
    #
    result = plugin.import_entities(
        datasets={MPlugin.USE_TYPE_JSON: _DIR_DATA / "mytral-goals.json"},
        user_profile=user_profile,
    )

    #
    # THEN
    #
    assert plugins.MytralEntityType.GOALS in result
    imported = result[plugins.MytralEntityType.GOALS]
    assert len(imported) == 2, f"Expected 2 goals, got {len(imported)}"

    names = {g.name for g in imported}
    assert "Sub-4h marathon" in names

    marathon = next(g for g in imported if g.name == "Sub-4h marathon")
    assert marathon.urgency == pytest.approx(0.8)
    assert marathon.importance == pytest.approx(0.9)
    assert marathon.done is False

    assert all(isinstance(g, settings.Goal) for g in imported)
    print(f"\nImported {len(imported)} goal(s) - DONE")


@pytest.mark.mytral
def test_import_mytral_laps_json(tmp_path: pathlib.Path):
    """Import MyTraL laps JSON and verify deserialized entities.

    Verifies that:
    - all records are converted to Lap instances
    - default_distance and default_duration are populated correctly
    """
    #
    # GIVEN
    #
    _, _, user_profile = _given.given_test(
        config.MytralConfig(persistence_data_dir=tmp_path),
        user_id="test_mytral_laps_user",
    )
    plugin = plugins.registry.get_plugin(MPlugin.NAME)

    #
    # WHEN
    #
    result = plugin.import_entities(
        datasets={MPlugin.USE_TYPE_JSON: _DIR_DATA / "mytral-laps.json"},
        user_profile=user_profile,
    )

    #
    # THEN
    #
    assert plugins.MytralEntityType.LAPS in result
    imported = result[plugins.MytralEntityType.LAPS]
    assert len(imported) == 2, f"Expected 2 laps, got {len(imported)}"

    names = {lap.name for lap in imported}
    assert "400m" in names

    lap_400 = next(lap for lap in imported if lap.name == "400m")
    assert lap_400.default_distance == 400
    assert lap_400.default_duration == 90

    assert all(isinstance(lap, settings.Lap) for lap in imported)
    print(f"\nImported {len(imported)} lap(s) - DONE")


@pytest.mark.mytral
def test_import_mytral_outfits_json(tmp_path: pathlib.Path):
    """Import MyTraL outfits JSON and verify deserialized entities.

    Verifies that:
    - all records are converted to Outfit instances
    - activity_type field is populated correctly
    """
    #
    # GIVEN
    #
    _, _, user_profile = _given.given_test(
        config.MytralConfig(persistence_data_dir=tmp_path),
        user_id="test_mytral_outfits_user",
    )
    plugin = plugins.registry.get_plugin(MPlugin.NAME)

    #
    # WHEN
    #
    result = plugin.import_entities(
        datasets={MPlugin.USE_TYPE_JSON: _DIR_DATA / "mytral-outfits.json"},
        user_profile=user_profile,
    )

    #
    # THEN
    #
    assert plugins.MytralEntityType.OUTFITS in result
    imported = result[plugins.MytralEntityType.OUTFITS]
    assert len(imported) == 2, f"Expected 2 outfits, got {len(imported)}"

    names = {o.name for o in imported}
    assert "Summer running kit" in names

    summer = next(o for o in imported if o.name == "Summer running kit")
    assert summer.activity_type == "run"

    assert all(isinstance(o, settings.Outfit) for o in imported)
    print(f"\nImported {len(imported)} outfit(s) - DONE")


@pytest.mark.mytral
def test_import_mytral_symptoms_json(tmp_path: pathlib.Path):
    """Import MyTraL symptoms JSON and verify deserialized entities.

    Verifies that:
    - all records are converted to Symptom instances
    - body_parts field is populated correctly
    """
    #
    # GIVEN
    #
    _, _, user_profile = _given.given_test(
        config.MytralConfig(persistence_data_dir=tmp_path),
        user_id="test_mytral_symptoms_user",
    )
    plugin = plugins.registry.get_plugin(MPlugin.NAME)

    #
    # WHEN
    #
    result = plugin.import_entities(
        datasets={MPlugin.USE_TYPE_JSON: _DIR_DATA / "mytral-symptoms.json"},
        user_profile=user_profile,
    )

    #
    # THEN
    #
    assert plugins.MytralEntityType.SYMPTOMS in result
    imported = result[plugins.MytralEntityType.SYMPTOMS]
    assert len(imported) == 2, f"Expected 2 symptoms, got {len(imported)}"

    names = {s.name for s in imported}
    assert "Left knee pain" in names

    knee = next(s for s in imported if s.name == "Left knee pain")
    assert "left_knee" in knee.body_parts

    assert all(isinstance(s, settings.Symptom) for s in imported)
    print(f"\nImported {len(imported)} symptom(s) - DONE")
