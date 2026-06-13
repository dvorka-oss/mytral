# MyTraL: my trailing log
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

import base64
import hashlib

import bcrypt
from cryptography.fernet import Fernet

from mytral import settings

# default encryption key DEVELOPMENT ONLY:
# - MUST be overridden in production via MYTRAL_ENCRYPTION_KEY
# - generated with: Fernet.generate_key().decode()
DEFAULT_ENC_KEY = "b3BlbnNzaC1rZXktdjEAAAAA_DEFAULT_MYTRAL_DEV_KEY_CHANGE_ME=="


def _ensure_valid_fernet_key(raw_key: str) -> bytes:
    """Pad/convert raw key string to valid 32-byte Fernet key.

    Parameters
    ----------
    raw_key : str
        Raw key string.

    Returns
    -------
    bytes
        Valid Fernet key bytes.
    """
    # normalize padding: strip any existing `=` then re-add the exact amount
    # needed so that len is a multiple of 4.  This correctly handles keys that
    # are already properly padded (e.g. from Fernet.generate_key()) as well as
    # keys with missing or excess padding.
    try:
        unpadded = raw_key.rstrip("=")
        padded = unpadded + "=" * (-len(unpadded) % 4)
        key_bytes = base64.urlsafe_b64decode(padded)
        if len(key_bytes) == 32:
            return base64.urlsafe_b64encode(key_bytes)
    except Exception:
        pass
    # derive 32 bytes from the key string using SHA-256
    key_bytes = hashlib.sha256(raw_key.encode()).digest()
    return base64.urlsafe_b64encode(key_bytes)


def encrypt(plaintext: str, key: str) -> str:
    """Encrypt a string using Fernet symmetric encryption.

    Parameters
    ----------
    plaintext : str
        The string to encrypt.
    key : str
        Encryption key (base64url-encoded 32-byte key, or any string).

    Returns
    -------
    str
        Encrypted string (base64url-encoded).
    """
    if not plaintext:
        return plaintext
    fernet = Fernet(_ensure_valid_fernet_key(key))
    return fernet.encrypt(plaintext.encode()).decode()


def decrypt(ciphertext: str, key: str) -> str:
    """Decrypt a string encrypted with encrypt().

    Parameters
    ----------
    ciphertext : str
        The encrypted string.
    key : str
        Encryption key (must match the key used to encrypt).

    Returns
    -------
    str
        Decrypted plaintext string.

    Raises
    ------
    ValueError
        If decryption fails (wrong key or corrupted data).
    """
    if not ciphertext:
        return ciphertext
    try:
        fernet = Fernet(_ensure_valid_fernet_key(key))
        return fernet.decrypt(ciphertext.encode()).decode()
    except Exception as ex:
        raise ValueError(f"Decryption failed: {ex}") from ex


def hash_password(password: str) -> str:
    """Hash password using bcrypt with a random salt.

    Parameters
    ----------
    password : str
        Plain-text password.

    Returns
    -------
    str
        bcrypt hash string (includes algorithm, cost, and salt).

    """
    if not password:
        return ""
    hashed = bcrypt.hashpw(password.encode("utf-8"), bcrypt.gensalt())
    return hashed.decode("utf-8")


def verify_password(plain: str, stored_hash: str) -> bool:
    """Verify a plain-text password against a stored hash.

    Parameters
    ----------
    plain : str
        Plain-text password submitted by the user.
    stored_hash : str
        Password hash stored in the user profile (bcrypt format).

    Returns
    -------
    bool
        True if the password matches, False otherwise.

    """
    if not plain or not stored_hash:
        return False

    try:
        return bcrypt.checkpw(plain.encode("utf-8"), stored_hash.encode("utf-8"))
    except Exception:
        return False


#
# Strava security
#


def decrypt_strava_secrets(profile_dict: dict, enc_key: str) -> None:
    """Decrypt encrypted Strava client secrets in a profile dict (in-place).

    Reads ``client_id_enc`` / ``client_secret_enc`` and writes the decrypted
    values back as ``client_id`` / ``client_secret`` so the rest of the code
    can use plain-text values transparently.  Falls back to any existing
    plain-text values for backward-compatibility (migration path).
    """
    strava = profile_dict.get(settings.UserProfile.KEY_STRAVA, {})
    for enc_field, plain_field in (
        (settings.UserProfile.KEY_CLIENT_ID_ENC, settings.UserProfile.KEY_CLIENT_ID),
        (
            settings.UserProfile.KEY_CLIENT_SECRET_ENC,
            settings.UserProfile.KEY_CLIENT_SECRET,
        ),
    ):
        enc_val = strava.get(enc_field, "")
        if enc_val:
            try:
                strava[plain_field] = decrypt(enc_val, enc_key)
            except ValueError:
                # key mismatch or corrupt value – fall back to whatever is stored
                pass


def encrypt_strava_secrets(data_dict: dict, enc_key: str) -> None:
    """Encrypt Strava client secrets in a serialisation dict (in-place).

    Reads plain-text ``client_id`` / ``client_secret`` from the ``strava``
    sub-dict, writes encrypted copies under ``client_id_enc`` /
    ``client_secret_enc``, and removes the plain-text keys so they are never
    written to disk.
    """
    strava = data_dict.get(settings.UserProfile.KEY_STRAVA, {})
    for plain_field, enc_field in (
        (settings.UserProfile.KEY_CLIENT_ID, settings.UserProfile.KEY_CLIENT_ID_ENC),
        (
            settings.UserProfile.KEY_CLIENT_SECRET,
            settings.UserProfile.KEY_CLIENT_SECRET_ENC,
        ),
    ):
        plain_val = strava.pop(plain_field, "")
        strava[enc_field] = encrypt(plain_val, enc_key) if plain_val else ""
