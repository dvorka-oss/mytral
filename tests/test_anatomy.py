# MyTraL: my training log
#
# Copyright (C) 2015-2026 Martin Dvorak <martin.dvorak@mindforger.com>
#
# This program is free software: you can redistribute it and/or modify
# it under the terms of the GNU Affero General Public License as published by
# the Free Software Foundation, either version 3 of the License, or
# (at your option) any later version.
#
# This program is distributed in the hope that it will be useful,
# but WITHOUT ANY WARRANTY; without even the implied warranty of
# MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the
# GNU Affero General Public License for more details.
#
# You should have received a copy of the GNU Affero General Public License
# along with this program. If not, see <http://www.gnu.org/licenses/>.
"""Tests for the anatomical mannequin geometry and the render_mannequin macro."""

import pytest

from mytral import anatomy
from mytral import muscle_groups
from mytral import routes
from mytral import settings

# the 3 picker-only part-ids the legacy macro exposed but the symptom
# region map does not validate (kept for backward compatibility)
_PICKER_ONLY_PART_IDS = {"front-abs", "front-obliques-l", "front-obliques-r"}


def _all_regions():
    return list(anatomy.FRONT_REGIONS) + list(anatomy.BACK_REGIONS)


def _render(**kwargs):
    template = routes.flask_app.jinja_env.get_template("macros/mannequin.html")
    return str(template.module.render_mannequin(**kwargs))


@pytest.mark.mytral
def test_anatomy_muscle_keys_are_canonical():
    # GIVEN the generated anatomy regions
    regions = _all_regions()
    # WHEN inspecting each region's muscle key
    # THEN it is either None (joint / silhouette) or a canonical muscle key
    for region in regions:
        assert (
            region.muscle_key is None
            or region.muscle_key in muscle_groups.MUSCLE_GROUP_BY_KEY
        ), region.part_id
    print("DONE: anatomy muscle keys are canonical")


@pytest.mark.mytral
def test_anatomy_covers_all_body_part_ids():
    # GIVEN the 60 part-ids the injury / sickness system depends on
    expected = set(settings._ALL_BODY_PART_IDS) | _PICKER_ONLY_PART_IDS
    # WHEN collecting the part-ids the geometry emits
    emitted = {region.part_id for region in _all_regions()}
    # THEN the geometry covers exactly that set (no orphaned injuries)
    assert emitted == expected, {
        "missing": sorted(expected - emitted),
        "unexpected": sorted(emitted - expected),
    }
    print("DONE: anatomy covers all 60 body-part ids")


@pytest.mark.mytral
def test_anatomy_includes_every_muscle_group():
    # GIVEN the 16 canonical muscle keys
    keys = set(muscle_groups.MUSCLE_GROUP_KEYS)
    # WHEN collecting muscle keys present in the geometry
    present = {r.muscle_key for r in _all_regions() if r.muscle_key}
    # THEN every muscle group is drawn at least once
    assert keys.issubset(present), sorted(keys - present)
    print("DONE: anatomy includes every muscle group")


@pytest.mark.mytral
def test_anatomy_outlines_and_paths_present():
    # GIVEN the geometry
    # WHEN inspecting outlines and region paths
    # THEN the silhouettes are present and every region has at least one path
    assert anatomy.FRONT_OUTLINE.startswith("M")
    assert anatomy.BACK_OUTLINE.startswith("M")
    for region in _all_regions():
        assert region.paths, region.part_id
    print("DONE: anatomy outlines and paths present")


@pytest.mark.mytral
def test_render_mannequin_display_highlights_muscle():
    # GIVEN a display-mode call highlighting quads at intensity 3
    html = _render(
        mode="display",
        highlights={"quads": "state-active intensity-3"},
        picker_id="t",
    )
    # WHEN / THEN the quads groups carry the heatmap class
    assert 'data-muscle-key="quads"' in html
    assert "state-active intensity-3" in html
    print("DONE: display mode highlights muscle")


@pytest.mark.mytral
def test_render_mannequin_injury_paints_only_injured_part():
    # GIVEN an injury-mode call for a single body part
    html = _render(
        mode="injury",
        injury_highlights={"front-knee-l"},
        picker_id="t",
    )
    # WHEN / THEN exactly that part is painted as injured
    assert 'data-part-id="front-knee-l"' in html
    assert html.count("body-injured") == 1
    print("DONE: injury mode paints only the injured part")


@pytest.mark.mytral
def test_render_mannequin_pickers_emit_inputs():
    # GIVEN picker and body_picker mode calls
    picker = _render(mode="picker", selected=["pecs"], picker_id="t")
    body = _render(
        mode="body_picker", selected_body_parts=["front-chest"], picker_id="t"
    )
    # WHEN / THEN the hidden inputs the CRUD blueprints read are present
    assert 'name="muscle_groups"' in picker
    assert 'name="muscle_groups_secondary"' in picker
    assert 'name="body_parts"' in body
    print("DONE: pickers emit the expected hidden inputs")
