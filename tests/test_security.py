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

from mytral import security


@pytest.mark.mytral
def test_hash_password_returns_bcrypt_hash():
    # GIVEN a plain-text password
    password = "correct-horse-battery-staple"

    # WHEN hashing it
    result = security.hash_password(password)

    # THEN the result is a bcrypt hash
    assert result.startswith("$2b$") or result.startswith("$2a$")
    print("DONE - hash_password returns bcrypt hash")


@pytest.mark.mytral
def test_hash_password_empty_returns_empty():
    # GIVEN an empty password
    password = ""

    # WHEN hashing it
    result = security.hash_password(password)

    # THEN an empty string is returned
    assert result == ""
    print("DONE - hash_password returns empty string for empty input")


@pytest.mark.mytral
def test_verify_password_bcrypt_correct():
    # GIVEN a bcrypt-hashed password
    password = "correct-horse-battery-staple"
    stored = security.hash_password(password)

    # WHEN verifying with the correct plain-text password
    result = security.verify_password(password, stored)

    # THEN verification succeeds
    assert result is True
    print("DONE - verify_password succeeds for correct bcrypt password")


@pytest.mark.mytral
def test_verify_password_bcrypt_wrong():
    # GIVEN a bcrypt-hashed password
    password = "correct-horse-battery-staple"
    stored = security.hash_password(password)

    # WHEN verifying with a wrong password
    result = security.verify_password("wrong-password", stored)

    # THEN verification fails
    assert result is False
    print("DONE - verify_password fails for wrong bcrypt password")


@pytest.mark.mytral
def test_verify_password_empty_inputs():
    # GIVEN empty plain and stored hash values
    stored = security.hash_password("some-password")

    # WHEN verifying with empty plain or empty stored hash
    result_empty_plain = security.verify_password("", stored)
    result_empty_hash = security.verify_password("some-password", "")

    # THEN both return False
    assert result_empty_plain is False
    assert result_empty_hash is False
    print("DONE - verify_password returns False for empty inputs")
