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

"""Tests for FIT recording import plugin and FIT summary extraction.

Covers three FIT files from a next-generation device (\"wingman\") that
exercises the parser's tolerance of unknown field IDs and non-standard
message sizes — the same tolerance that the ``recordings/__init__.py``
monkeypatch provides for string decoding.
"""

import datetime
import pathlib

import pytest

from mytral import commons
from mytral.recordings import fit_extractor
from mytral.recordings.models import RecordingSummary

_DIR_TESTS = pathlib.Path(__file__).parent
_FIT_DIR = _DIR_TESTS / "data" / "import" / "fit"

# paths to the three next-gen-device FIT files
_FIT_HIKING = _FIT_DIR / "ng-device-wingman-hiking.fit"
_FIT_INDOOR = _FIT_DIR / "ng-device-wingman-indoor.fit"
_FIT_RUNNING = _FIT_DIR / "ng-device-wingman-running.fit"


def _extract(path: pathlib.Path) -> RecordingSummary:
    """Read a FIT file from disk and return its activity summary."""
    data = path.read_bytes()
    return fit_extractor.extract_fit_summary(data)


@pytest.mark.mytral
def test_fit_summary_hiking():
    """Extract summary from a next-gen-device hiking FIT file.

    Verifies that the parser tolerates unknown field IDs and non-standard
    message sizes while still extracting the core session fields correctly.
    """
    #
    # GIVEN
    #
    assert _FIT_HIKING.is_file(), f"Test FIT file not found: {_FIT_HIKING}"

    #
    # WHEN
    #
    summary = _extract(_FIT_HIKING)

    #
    # THEN
    #
    assert isinstance(summary, RecordingSummary)
    assert summary.activity_type_key == commons.AT_HIKE, (
        f"Expected hike, got {summary.activity_type_key}"
    )
    assert summary.when == datetime.datetime(2023, 5, 19, 8, 49, 12)
    assert summary.hours == 10
    assert summary.minutes == 17
    assert summary.seconds == 53
    assert summary.distance == 23129
    assert summary.kcal == 2614
    assert summary.avg_hr == 91
    assert summary.max_hr == 135
    assert summary.elevation_gain == 566

    # the next-gen device emits uint16-max (65535) for power and
    # implausibly high speed values — the parser faithfully returns
    # whatever the FIT session message contains
    assert summary.avg_watts == 65535.0
    assert summary.max_watts == 65535.0

    print("DONE: FIT hiking summary extracted")


@pytest.mark.mytral
def test_fit_summary_indoor():
    """Extract summary from a next-gen-device indoor workout FIT file.

    Indoor activities have zero distance and no elevation — the parser
    should still return valid HR and kcal data.
    """
    #
    # GIVEN
    #
    assert _FIT_INDOOR.is_file(), f"Test FIT file not found: {_FIT_INDOOR}"

    #
    # WHEN
    #
    summary = _extract(_FIT_INDOOR)

    #
    # THEN
    #
    assert isinstance(summary, RecordingSummary)
    # indoor workout with unrecognized sport → falls back to "workout"
    assert summary.activity_type_key == commons.AT_WORKOUT, (
        f"Expected workout, got {summary.activity_type_key}"
    )
    assert summary.when == datetime.datetime(2022, 6, 1, 21, 12, 51)
    assert summary.hours == 0
    assert summary.minutes == 38
    assert summary.seconds == 17
    assert summary.distance == 0
    assert summary.kcal == 529
    assert summary.avg_hr == 152
    assert summary.max_hr == 179
    assert summary.elevation_gain == 0

    print("DONE: FIT indoor summary extracted")


@pytest.mark.mytral
def test_fit_summary_running():
    """Extract summary from a next-gen-device short running FIT file."""
    #
    # GIVEN
    #
    assert _FIT_RUNNING.is_file(), f"Test FIT file not found: {_FIT_RUNNING}"

    #
    # WHEN
    #
    summary = _extract(_FIT_RUNNING)

    #
    # THEN
    #
    assert isinstance(summary, RecordingSummary)
    assert summary.activity_type_key == commons.AT_RUN, (
        f"Expected run, got {summary.activity_type_key}"
    )
    assert summary.when == datetime.datetime(2024, 3, 16, 14, 54, 21)
    assert summary.hours == 0
    assert summary.minutes == 1
    assert summary.seconds == 57
    assert summary.distance == 373
    assert summary.kcal == 16
    assert summary.avg_hr == 113
    assert summary.max_hr == 118
    assert summary.elevation_gain == 1

    print("DONE: FIT running summary extracted")


@pytest.mark.mytral
def test_fit_summary_all_three_files_return_valid_data():
    """Smoke test: all three next-gen-device FIT files parse without error.

    The primary goal is to ensure that the monkeypatched fit_tool string
    decoder and the parser's tolerance of unknown fields keep working
    for FIT files produced by newer Garmin devices.
    """
    #
    # GIVEN
    #
    fit_files = sorted(
        p for p in _FIT_DIR.glob("ng-device-wingman*.fit") if p.is_file()
    )
    assert len(fit_files) == 3, (
        f"Expected 3 wingman FIT files, found {len(fit_files)}: {fit_files}"
    )

    #
    # WHEN
    #
    summaries: list[RecordingSummary] = []
    for fit_path in fit_files:
        summaries.append(_extract(fit_path))

    #
    # THEN
    #
    assert len(summaries) == 3
    for i, summary in enumerate(summaries):
        assert isinstance(summary, RecordingSummary), (
            f"File {fit_files[i].name} did not return a RecordingSummary"
        )
        assert summary.activity_type_key, (
            f"File {fit_files[i].name} has no activity_type_key"
        )
        assert summary.when is not None, f"File {fit_files[i].name} has no timestamp"

    print(f"DONE: all {len(summaries)} wingman FIT files parsed successfully")
