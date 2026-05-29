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
"""Integration tests for AWS S3 blob store backend.

These tests require real AWS credentials and the following environment
variables to be set:

    MYTRAL_BLOBSTORE_S3_BUCKET
    MYTRAL_BLOBSTORE_S3_REGION        (e.g. us-east-1)
    AWS_ACCESS_KEY_ID
    AWS_SECRET_ACCESS_KEY

An optional ``MYTRAL_BLOBSTORE_S3_ENDPOINT_URL`` can override the S3 endpoint
(useful with LocalStack or MinIO in S3-compatibility mode).

If any required variable is missing the entire module is skipped.
"""

import io
import os
import uuid

import pytest

from mytral.blobstore import exceptions
from mytral.blobstore import models

# skip logic

_REQUIRED_ENV = [
    "MYTRAL_BLOBSTORE_S3_BUCKET",
    "MYTRAL_BLOBSTORE_S3_REGION",
    "AWS_ACCESS_KEY_ID",
    "AWS_SECRET_ACCESS_KEY",
]
_s3_available = all(os.environ.get(var) for var in _REQUIRED_ENV)

pytestmark = pytest.mark.skipif(
    not _s3_available,
    reason="AWS S3 environment variables not set; skipping S3 integration tests.",
)


# helpers

_USER = "test_s3_user"
_ACTIVITY_KEY = "act-s3-001"


def _make_store():
    """Create an S3BlobStore from environment variables."""
    from mytral.blobstore import s3_store  # noqa: PLC0415

    return s3_store.S3BlobStore(
        bucket=os.environ["MYTRAL_BLOBSTORE_S3_BUCKET"],
        region=os.environ["MYTRAL_BLOBSTORE_S3_REGION"],
        endpoint_url=os.environ.get("MYTRAL_BLOBSTORE_S3_ENDPOINT_URL"),
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
        name="Test GPX S3",
        description="",
        keywords=["s3"],
        created_at="2024-01-01T00:00:00",
        updated_at="2024-01-01T00:00:00",
        track_count=1,
        track_point_count=5,
    )


# tests


@pytest.mark.mytral
def test_s3_create_and_get_metadata():
    # GIVEN an S3 store and GPX metadata
    store = _make_store()
    key = _unique_key("gpx")
    meta = _gpx_metadata(key)

    try:
        # WHEN creating a blob
        result = store.create_blob(meta, io.BytesIO(b"<gpx/>"))

        # THEN metadata is stored and retrievable
        assert result.blob_key == key
        fetched = store.get_blob_metadata(_USER, key)
        assert fetched.name == "Test GPX S3"
        assert fetched.keywords == ["s3"]
    finally:
        if store.blob_exists(_USER, key):
            store.delete_blob(_USER, key)
    print("DONE s3_create_and_get_metadata")


@pytest.mark.mytral
def test_s3_open_blob_original():
    # GIVEN a blob stored in S3
    store = _make_store()
    key = _unique_key("gpx")
    meta = _gpx_metadata(key)
    content = b"<gpx>s3_data</gpx>"

    try:
        store.create_blob(meta, io.BytesIO(content))

        # WHEN opening the original variant
        stream = store.open_blob(_USER, key, variant=models.BLOB_VARIANT_ORIGINAL)

        # THEN the data matches what was written
        assert stream.read() == content
    finally:
        if store.blob_exists(_USER, key):
            store.delete_blob(_USER, key)
    print("DONE s3_open_blob_original")


@pytest.mark.mytral
def test_s3_delete_removes_all_objects():
    # GIVEN a blob with a variant stored in S3
    store = _make_store()
    key = _unique_key("gpx")
    meta = _gpx_metadata(key)
    store.create_blob(meta, io.BytesIO(b"<gpx/>"))
    store.write_blob_variant(_USER, key, models.BLOB_VARIANT_NORMALIZED, b"norm")

    # WHEN deleting the blob
    store.delete_blob(_USER, key)

    # THEN the blob no longer exists
    assert not store.blob_exists(_USER, key)
    with pytest.raises(exceptions.BlobNotFoundError):
        store.get_blob_metadata(_USER, key)
    print("DONE s3_delete_removes_all_objects")


@pytest.mark.mytral
def test_s3_duplicate_create_raises():
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
    print("DONE s3_duplicate_create_raises")


@pytest.mark.mytral
def test_s3_update_metadata():
    # GIVEN a stored blob
    store = _make_store()
    key = _unique_key("gpx")
    meta = _gpx_metadata(key)
    store.create_blob(meta, io.BytesIO(b"<gpx/>"))

    try:
        # WHEN updating the metadata
        updated = store.update_blob_metadata(
            _USER, key, name="S3 Updated", description="", keywords=["x", "y"]
        )

        # THEN the changes are reflected in a subsequent fetch
        assert updated.name == "S3 Updated"
        refetched = store.get_blob_metadata(_USER, key)
        assert refetched.keywords == ["x", "y"]
    finally:
        if store.blob_exists(_USER, key):
            store.delete_blob(_USER, key)
    print("DONE s3_update_metadata")
