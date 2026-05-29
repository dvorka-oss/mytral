# MyTraL: my trailing log
#
# Copyright (C) 2022-2026 Martin Dvorak <martin.dvorak@mindforger.com>
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

"""Integration tests for MinIO blob store backend.

These tests require a running MinIO server and the following environment
variables to be set:

    MYTRAL_BLOBSTORE_MINIO_ENDPOINT  e.g. localhost:9000
    MYTRAL_BLOBSTORE_MINIO_ACCESS_KEY
    MYTRAL_BLOBSTORE_MINIO_SECRET_KEY
    MYTRAL_BLOBSTORE_MINIO_BUCKET    (must already exist or be creatable)

If any variable is missing the entire module is skipped.
"""

import io
import os
import uuid

import pytest

from mytral.blobstore import exceptions
from mytral.blobstore import models

# skip logic

_REQUIRED_ENV = [
    "MYTRAL_BLOBSTORE_MINIO_ENDPOINT",
    "MYTRAL_BLOBSTORE_MINIO_ACCESS_KEY",
    "MYTRAL_BLOBSTORE_MINIO_SECRET_KEY",
    "MYTRAL_BLOBSTORE_MINIO_BUCKET",
]
_minio_available = all(os.environ.get(var) for var in _REQUIRED_ENV)

pytestmark = pytest.mark.skipif(
    not _minio_available,
    reason="MinIO environment variables not set; skipping MinIO integration tests.",
)


# helpers

_USER = "test_minio_user"
_ACTIVITY_KEY = "act-minio-001"


def _make_store():
    """Create a MinioBlobStore from environment variables."""
    # lazy import to avoid hard dependency when skipped
    from mytral.blobstore import minio_store  # noqa: PLC0415

    return minio_store.MinioBlobStore(
        endpoint=os.environ["MYTRAL_BLOBSTORE_MINIO_ENDPOINT"],
        access_key=os.environ["MYTRAL_BLOBSTORE_MINIO_ACCESS_KEY"],
        secret_key=os.environ["MYTRAL_BLOBSTORE_MINIO_SECRET_KEY"],
        bucket=os.environ["MYTRAL_BLOBSTORE_MINIO_BUCKET"],
        secure=os.environ.get("MYTRAL_BLOBSTORE_MINIO_SECURE", "false").lower()
        == "true",
    )


def _unique_key(prefix: str = "blob") -> str:
    return f"{prefix}-{uuid.uuid4().hex[:8]}"


def _gpx_metadata(blob_key: str) -> models.BlobMetadata:
    return models.BlobMetadata(
        blob_key=blob_key,
        user_id=_USER,
        owner_kind=models.BlobOwnerKind.ACTIVITY.value,
        owner_key=_ACTIVITY_KEY,
        kind=models.BlobKind.ACTIVITY_RECORDING.value,
        file_name="track.gpx",
        original_file_name="track.gpx",
        extension=".gpx",
        content_type="application/gpx+xml",
        size_bytes=64,
        sha256="abc",
        name="Test GPX",
        description="",
        keywords=["run"],
        created_at="2024-01-01T00:00:00",
        updated_at="2024-01-01T00:00:00",
        track_count=1,
        track_point_count=10,
    )


# tests


@pytest.mark.mytral
def test_minio_create_and_get_metadata():
    # GIVEN a MinIO store and GPX metadata
    store = _make_store()
    key = _unique_key("gpx")
    meta = _gpx_metadata(key)

    try:
        # WHEN creating a blob
        result = store.create_blob(meta, io.BytesIO(b"<gpx/>"))

        # THEN metadata is stored and retrievable
        assert result.blob_key == key
        fetched = store.get_blob_metadata(_USER, key)
        assert fetched.name == "Test GPX"
        assert fetched.keywords == ["run"]
    finally:
        if store.blob_exists(_USER, key):
            store.delete_blob(_USER, key)
    print("DONE minio_create_and_get_metadata")


@pytest.mark.mytral
def test_minio_open_blob_original():
    # GIVEN a blob stored in MinIO
    store = _make_store()
    key = _unique_key("gpx")
    meta = _gpx_metadata(key)
    content = b"<gpx>data</gpx>"

    try:
        store.create_blob(meta, io.BytesIO(content))

        # WHEN opening the original variant
        stream = store.open_blob(_USER, key, variant=models.BLOB_VARIANT_ORIGINAL)

        # THEN the data matches what was written
        assert stream.read() == content
    finally:
        if store.blob_exists(_USER, key):
            store.delete_blob(_USER, key)
    print("DONE minio_open_blob_original")


@pytest.mark.mytral
def test_minio_delete_removes_all_objects():
    # GIVEN a blob with a variant
    store = _make_store()
    key = _unique_key("gpx")
    meta = _gpx_metadata(key)
    store.create_blob(meta, io.BytesIO(b"<gpx/>"))
    store.write_blob_variant(_USER, key, models.BLOB_VARIANT_NORMALIZED, b"norm")

    # WHEN deleting the blob
    store.delete_blob(_USER, key)

    # THEN the blob no longer exists and metadata lookup raises
    assert not store.blob_exists(_USER, key)
    with pytest.raises(exceptions.BlobNotFoundError):
        store.get_blob_metadata(_USER, key)
    print("DONE minio_delete_removes_all_objects")


@pytest.mark.mytral
def test_minio_duplicate_create_raises():
    # GIVEN a blob that already exists
    store = _make_store()
    key = _unique_key("gpx")
    meta = _gpx_metadata(key)
    store.create_blob(meta, io.BytesIO(b"<gpx/>"))

    try:
        # WHEN creating the same blob again
        # THEN BlobConflictError is raised
        with pytest.raises(exceptions.BlobConflictError):
            store.create_blob(meta, io.BytesIO(b"<gpx/>"))
    finally:
        store.delete_blob(_USER, key)
    print("DONE minio_duplicate_create_raises")


@pytest.mark.mytral
def test_minio_update_metadata():
    # GIVEN a stored blob
    store = _make_store()
    key = _unique_key("gpx")
    meta = _gpx_metadata(key)
    store.create_blob(meta, io.BytesIO(b"<gpx/>"))

    try:
        # WHEN updating the metadata
        updated = store.update_blob_metadata(
            _USER, key, name="Updated", description="", keywords=["a", "b"]
        )

        # THEN the changes are reflected in a subsequent fetch
        assert updated.name == "Updated"
        refetched = store.get_blob_metadata(_USER, key)
        assert refetched.keywords == ["a", "b"]
    finally:
        if store.blob_exists(_USER, key):
            store.delete_blob(_USER, key)
    print("DONE minio_update_metadata")
