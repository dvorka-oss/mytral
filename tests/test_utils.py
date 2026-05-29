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
import pytest

from mytral import utils


@pytest.mark.parametrize(
    "s,expected",
    [
        ("c0defa8d-1198-4a62-b506-0bc945282113", True),
        ("strava-gear-id:12345", False),
        ("", False),
    ],
)
def test_is_uuid(s: str, expected: bool):
    assert expected == utils.is_uuid(s)


@pytest.mark.mytral
def test_tag_to_color():
    # GIVEN
    tag1 = "upper body"
    tag2 = "strength"
    tag3 = "compound"

    # WHEN
    color1 = utils.tag_to_color(tag1)
    color2 = utils.tag_to_color(tag2)
    color3 = utils.tag_to_color(tag3)

    # THEN
    assert color1 in [
        "blue",
        "azure",
        "indigo",
        "purple",
        "pink",
        "red",
        "orange",
        "yellow",
        "lime",
        "green",
        "teal",
        "cyan",
    ]
    assert color2 in [
        "blue",
        "azure",
        "indigo",
        "purple",
        "pink",
        "red",
        "orange",
        "yellow",
        "lime",
        "green",
        "teal",
        "cyan",
    ]
    assert color3 in [
        "blue",
        "azure",
        "indigo",
        "purple",
        "pink",
        "red",
        "orange",
        "yellow",
        "lime",
        "green",
        "teal",
        "cyan",
    ]

    # Test consistency
    assert utils.tag_to_color(tag1) == color1
    assert utils.tag_to_color(tag2) == color2
    assert utils.tag_to_color(tag3) == color3

    # Test case insensitivity
    assert utils.tag_to_color("Upper Body") == color1
    assert utils.tag_to_color("UPPER BODY") == color1

    print(f"DONE: tag '{tag1}' -> '{color1}'")
    print(f"DONE: tag '{tag2}' -> '{color2}'")
    print(f"DONE: tag '{tag3}' -> '{color3}'")
