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
"""Tests for mytral.blobstore.validation.validate_recording."""

import pytest

from mytral.blobstore.exceptions import BlobValidationError
from mytral.blobstore.validation import RECORDING_ALLOWED_EXTENSIONS
from mytral.blobstore.validation import validate_recording


@pytest.mark.mytral
def test_validate_recording_fit_ok():
    """Test validate_recording accepts a valid FIT file."""
    # GIVEN
    filename = "activity.fit"
    # FIT magic: bytes 8-11 must be b".FIT"
    data = b"\x0e\x10\x44\x08" + b"\x00" * 4 + b".FIT" + b"\x00" * 100

    # WHEN
    ext = validate_recording(filename=filename, data=data)

    # THEN
    assert ext == ".fit"
    print("validate_recording FIT ok: DONE")


@pytest.mark.mytral
def test_validate_recording_gpx_ok():
    """Test validate_recording accepts a valid GPX file."""
    # GIVEN
    filename = "track.gpx"
    data = b'<?xml version="1.0"?><gpx/>'

    # WHEN
    ext = validate_recording(filename=filename, data=data)

    # THEN
    assert ext == ".gpx"
    print("validate_recording GPX ok: DONE")


@pytest.mark.mytral
def test_validate_recording_hrm_ok():
    """Test validate_recording accepts a valid HRM file."""
    # GIVEN
    filename = "exercise.hrm"
    data = b"[Params]\r\nVersion=106\r\n"

    # WHEN
    ext = validate_recording(filename=filename, data=data)

    # THEN
    assert ext == ".hrm"
    print("validate_recording HRM ok: DONE")


@pytest.mark.mytral
def test_validate_recording_unsupported_extension():
    """Test validate_recording rejects an unsupported extension."""
    # GIVEN
    filename = "workout.tcx"
    data = b"<xml/>" * 20

    # WHEN / THEN
    with pytest.raises(BlobValidationError, match="Unsupported recording extension"):
        validate_recording(filename=filename, data=data)
    print("validate_recording unsupported extension: DONE")


@pytest.mark.mytral
def test_validate_recording_empty_data():
    """Test validate_recording rejects empty file."""
    # GIVEN
    filename = "empty.fit"
    data = b""

    # WHEN / THEN
    with pytest.raises(BlobValidationError, match="empty"):
        validate_recording(filename=filename, data=data)
    print("validate_recording empty data: DONE")


@pytest.mark.mytral
def test_validate_recording_too_large():
    """Test validate_recording rejects oversized file."""
    # GIVEN
    filename = "big.fit"
    max_bytes = 100
    data = b"x" * (max_bytes + 1)

    # WHEN / THEN
    with pytest.raises(BlobValidationError, match="exceeds the maximum"):
        validate_recording(filename=filename, data=data, max_bytes=max_bytes)
    print("validate_recording too large: DONE")


@pytest.mark.mytral
def test_validate_recording_empty_filename():
    """Test validate_recording rejects empty filename."""
    # GIVEN
    filename = ""
    data = b"somedata"

    # WHEN / THEN
    with pytest.raises(BlobValidationError, match="empty"):
        validate_recording(filename=filename, data=data)
    print("validate_recording empty filename: DONE")


@pytest.mark.mytral
def test_recording_allowed_extensions_set():
    """Test RECORDING_ALLOWED_EXTENSIONS contains expected values."""
    # GIVEN / WHEN / THEN
    assert ".fit" in RECORDING_ALLOWED_EXTENSIONS
    assert ".gpx" in RECORDING_ALLOWED_EXTENSIONS
    assert ".hrm" in RECORDING_ALLOWED_EXTENSIONS
    assert ".tcx" not in RECORDING_ALLOWED_EXTENSIONS
    print("RECORDING_ALLOWED_EXTENSIONS content: DONE")
