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

import pytest

from mytral import security
from mytral import settings


def _profile_with_secrets() -> settings.UserProfile:
    """Build a profile carrying both Strava and Polar Flow secrets."""
    return settings.UserProfile(
        user_id="u1",
        user="tester",
        email="tester@example.com",
        password_enc="",
        dataset_name="default",
        dataset_names=["default"],
        height=1.8,
        strava_client_id="strava-client-id",
        strava_client_secret="strava-client-secret",
        polar_flow_client_id="polar-client-id",
        polar_flow_client_secret="polar-client-secret",
        polar_flow_access_token="polar-access-token-xyz",
        polar_flow_user_id="12345",
    )


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


@pytest.mark.mytral
def test_encrypt_profile_secrets_removes_plaintext_and_round_trips():
    # GIVEN a serialized profile holding Strava and Polar Flow secrets
    key = security.DEFAULT_ENC_KEY
    data = _profile_with_secrets().to_dict()

    # WHEN encrypting the profile secrets for persistence
    security.encrypt_profile_secrets(data, key)

    # THEN no plain-text secret survives anywhere in the serialized form
    blob = json.dumps(data)
    for secret in (
        "strava-client-secret",
        "polar-client-secret",
        "polar-access-token-xyz",
    ):
        assert secret not in blob
    polar = data[settings.UserProfile.KEY_POLAR_FLOW]
    assert settings.UserProfile.KEY_CLIENT_SECRET not in polar
    assert settings.UserProfile.KEY_ACCESS_TOKEN not in polar
    assert polar[settings.UserProfile.KEY_ACCESS_TOKEN_ENC]

    # AND decrypting on load restores the plain-text values transparently
    security.decrypt_profile_secrets(data, key)
    restored = settings.UserProfile.from_dict(data)
    assert restored.strava_client_secret == "strava-client-secret"
    assert restored.polar_flow_client_secret == "polar-client-secret"
    assert restored.polar_flow_access_token == "polar-access-token-xyz"
    assert restored.polar_flow_user_id == "12345"
    print("DONE - profile secrets encrypt at rest and round-trip on load")


@pytest.mark.mytral
def test_decrypt_profile_secrets_plaintext_migration_fallback():
    # GIVEN a legacy profile dict with a plain-text Polar secret and no *_enc key
    key = security.DEFAULT_ENC_KEY
    data = {
        settings.UserProfile.KEY_POLAR_FLOW: {
            settings.UserProfile.KEY_ACCESS_TOKEN: "legacy-plain-token",
        }
    }

    # WHEN decrypting (as done on load)
    security.decrypt_profile_secrets(data, key)

    # THEN the plain-text value is left untouched (transparent migration)
    polar = data[settings.UserProfile.KEY_POLAR_FLOW]
    assert polar[settings.UserProfile.KEY_ACCESS_TOKEN] == "legacy-plain-token"
    print("DONE - decrypt_profile_secrets falls back to plain-text values")


@pytest.mark.mytral
def test_encrypt_profile_secrets_handles_empty_secrets():
    # GIVEN a profile with no secrets set
    key = security.DEFAULT_ENC_KEY
    data = settings.UserProfile(
        user_id="u2",
        user="empty",
        email="empty@example.com",
        password_enc="",
        dataset_name="default",
        dataset_names=["default"],
        height=1.8,
    ).to_dict()

    # WHEN encrypting then decrypting
    security.encrypt_profile_secrets(data, key)
    security.decrypt_profile_secrets(data, key)

    # THEN empty secrets stay empty and no exception is raised
    restored = settings.UserProfile.from_dict(data)
    assert restored.polar_flow_access_token == ""
    assert restored.polar_flow_client_secret == ""
    assert restored.strava_client_secret == ""
    print("DONE - profile secret encryption handles empty secrets")
