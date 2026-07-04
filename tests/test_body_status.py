# MyTraL: my training log
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
import pytest

from mytral import settings as user_settings
from mytral.blueprints import health_uri_space
from mytral.settings import UserSymptoms


def _empty_symptoms() -> UserSymptoms:
    return UserSymptoms(symptoms=[])


@pytest.mark.mytral
def test_body_parts_mapping():
    """Test BODY_PARTS_BY_REGION constant has all necessary parts."""
    # GIVEN
    expected_parts = [
        "head",
        "neck",
        "shoulder_left",
        "shoulder_right",
        "chest",
        "upper_back",
        "lower_back",
        "knee_left",
        "knee_right",
    ]

    # WHEN
    # THEN
    for part in expected_parts:
        assert part in user_settings.BODY_PARTS_BY_REGION
        assert len(user_settings.BODY_PARTS_BY_REGION[part]) > 0


@pytest.mark.mytral
def test_validate_body_part_ids_filters_unknown_ids():
    # GIVEN a mix of valid ids, an unknown id, and garbage input
    submitted = ["front-thigh-r", "not-a-real-part", "back-ankle-l", ""]

    # WHEN validating
    validated = user_settings.validate_body_part_ids(submitted)

    # THEN only the known ids survive, in order
    assert validated == ["front-thigh-r", "back-ankle-l"]
    print("DONE: validate_body_part_ids filters unknown ids")


@pytest.mark.mytral
def test_validate_body_part_ids_accepts_abs_and_obliques():
    # GIVEN the abs/obliques ids the mannequin picker can submit
    submitted = ["front-abs", "front-obliques-l", "front-obliques-r"]

    # WHEN validating
    validated = user_settings.validate_body_part_ids(submitted)

    # THEN none of them are silently dropped
    assert validated == submitted
    print("DONE: validate_body_part_ids accepts abs and obliques")


@pytest.mark.mytral
def test_map_injuries_to_body_parts_with_sides():
    """Test mapping injuries to body parts with left/right sides."""
    # GIVEN
    injuries = [
        {"symptom": "pain", "body_part": "knee", "side": "left", "health": 80},
        {"symptom": "ache", "body_part": "shoulder", "side": "right", "health": 90},
    ]

    # WHEN
    highlights = health_uri_space._build_body_highlights(injuries, _empty_symptoms())

    # THEN
    assert "front-knee-l" in highlights
    assert "back-knee-l" in highlights
    assert "front-shoulder-r" in highlights
    assert "back-shoulder-r" in highlights
    print(f"Test passed: highlights = {highlights}")


@pytest.mark.mytral
def test_map_injuries_to_body_parts_without_sides():
    """Test mapping injuries to body parts without sides."""
    # GIVEN
    injuries = [
        {"symptom": "headache", "body_part": "head", "side": "", "health": 70},
        {"symptom": "back pain", "body_part": "lower_back", "side": "", "health": 60},
    ]

    # WHEN
    highlights = health_uri_space._build_body_highlights(injuries, _empty_symptoms())

    # THEN
    assert "front-head" in highlights
    assert "back-head" in highlights
    assert "back-lower" in highlights
    print(f"Test passed: highlights = {highlights}")


@pytest.mark.mytral
def test_map_injuries_empty_list():
    """Test mapping empty injuries list."""
    # GIVEN
    injuries = []

    # WHEN
    highlights = health_uri_space._build_body_highlights(injuries, _empty_symptoms())

    # THEN
    assert len(highlights) == 0
    print("Test passed: empty injuries list returns empty highlights")


@pytest.mark.mytral
def test_map_injuries_unknown_body_part():
    """Test mapping injuries with unknown body part."""
    # GIVEN
    injuries = [
        {"symptom": "pain", "body_part": "unknown_part", "side": "", "health": 50},
    ]

    # WHEN
    highlights = health_uri_space._build_body_highlights(injuries, _empty_symptoms())

    # THEN
    assert len(highlights) == 0
    print("Test passed: unknown body part returns no highlights")
