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
import io
import pathlib

import pytest

from mytral.blobstore import exceptions
from mytral.blobstore import filesystem
from mytral.blobstore import models

# helpers

_USER = "user_fs_test"
_ACTIVITY_KEY = "act-001"


def _gpx_metadata(blob_key: str = "gpx-0001") -> models.BlobMetadata:
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
        size_bytes=128,
        sha256="abc123",
        name="Morning run",
        description="Easy 5 km",
        keywords=["run", "morning"],
        created_at="2024-01-01T08:00:00",
        updated_at="2024-01-01T08:00:00",
        track_count=1,
        track_point_count=42,
    )


def _photo_metadata(blob_key: str = "photo-0001") -> models.BlobMetadata:
    return models.BlobMetadata(
        blob_key=blob_key,
        user_id=_USER,
        owner_kind=models.BlobOwnerKind.ACTIVITY.value,
        owner_key=_ACTIVITY_KEY,
        kind=models.BlobKind.ACTIVITY_PHOTO.value,
        file_name="photo.jpg",
        original_file_name="IMG_0001.jpg",
        extension=".jpg",
        content_type="image/jpeg",
        size_bytes=2048,
        sha256="def456",
        name="Summit view",
        description="View from the top",
        keywords=["mountain"],
        created_at="2024-01-01T10:00:00",
        updated_at="2024-01-01T10:00:00",
        width=1920,
        height=1080,
    )


def _make_store(tmp_path: pathlib.Path) -> filesystem.FilesystemBlobStore:
    return filesystem.FilesystemBlobStore(base_dir=tmp_path)


# create_blob


@pytest.mark.mytral
def test_create_blob_gpx(tmp_path: pathlib.Path):
    # GIVEN a filesystem store and GPX metadata
    store = _make_store(tmp_path)
    meta = _gpx_metadata()
    data = b"<gpx></gpx>"

    # WHEN creating a blob
    result = store.create_blob(meta, io.BytesIO(data))

    # THEN the metadata is returned and blob exists on disk
    assert result.blob_key == meta.blob_key
    assert store.blob_exists(_USER, meta.blob_key)
    print("DONE create_blob_gpx")


@pytest.mark.mytral
def test_create_blob_photo(tmp_path: pathlib.Path):
    # GIVEN a filesystem store and photo metadata
    store = _make_store(tmp_path)
    meta = _photo_metadata()
    data = b"\xff\xd8\xff" + b"\x00" * 20  # minimal jpeg-like bytes

    # WHEN creating a blob
    result = store.create_blob(meta, io.BytesIO(data))

    # THEN metadata is stored and file exists
    assert result.blob_key == meta.blob_key
    assert store.blob_exists(_USER, meta.blob_key)
    print("DONE create_blob_photo")


@pytest.mark.mytral
def test_create_blob_duplicate_raises(tmp_path: pathlib.Path):
    # GIVEN a blob already stored
    store = _make_store(tmp_path)
    meta = _gpx_metadata()
    store.create_blob(meta, io.BytesIO(b"<gpx/>"))

    # WHEN creating the same blob again
    # THEN BlobConflictError is raised
    with pytest.raises(exceptions.BlobConflictError):
        store.create_blob(meta, io.BytesIO(b"<gpx/>"))
    print("DONE create_blob_duplicate_raises")


# get_blob_metadata


@pytest.mark.mytral
def test_get_blob_metadata_returns_stored_meta(tmp_path: pathlib.Path):
    # GIVEN a blob stored with known metadata
    store = _make_store(tmp_path)
    meta = _gpx_metadata()
    store.create_blob(meta, io.BytesIO(b"<gpx/>"))

    # WHEN fetching metadata
    fetched = store.get_blob_metadata(_USER, meta.blob_key)

    # THEN all fields match
    assert fetched.blob_key == meta.blob_key
    assert fetched.name == meta.name
    assert fetched.keywords == meta.keywords
    assert fetched.track_count == meta.track_count
    print("DONE get_blob_metadata_returns_stored_meta")


@pytest.mark.mytral
def test_get_blob_metadata_missing_raises(tmp_path: pathlib.Path):
    # GIVEN an empty store
    store = _make_store(tmp_path)

    # WHEN fetching a non-existent blob
    # THEN BlobNotFoundError is raised
    with pytest.raises(exceptions.BlobNotFoundError):
        store.get_blob_metadata(_USER, "nonexistent-key")
    print("DONE get_blob_metadata_missing_raises")


# list_blobs


@pytest.mark.mytral
def test_list_blobs_returns_all_for_owner(tmp_path: pathlib.Path):
    # GIVEN two blobs for the same activity
    store = _make_store(tmp_path)
    gpx = _gpx_metadata("gpx-001")
    photo = _photo_metadata("photo-001")
    store.create_blob(gpx, io.BytesIO(b"<gpx/>"))
    store.create_blob(photo, io.BytesIO(b"\xff\xd8"))

    # WHEN listing blobs for the activity
    results = store.list_blobs(
        user_id=_USER,
        owner_kind=models.BlobOwnerKind.ACTIVITY.value,
        owner_key=_ACTIVITY_KEY,
    )

    # THEN both blobs are returned
    keys = {r.blob_key for r in results}
    assert "gpx-001" in keys
    assert "photo-001" in keys
    print("DONE list_blobs_returns_all_for_owner")


@pytest.mark.mytral
def test_list_blobs_empty_owner_returns_empty(tmp_path: pathlib.Path):
    # GIVEN an empty store
    store = _make_store(tmp_path)

    # WHEN listing blobs for an owner with none
    results = store.list_blobs(
        user_id=_USER,
        owner_kind=models.BlobOwnerKind.ACTIVITY.value,
        owner_key="no-such-activity",
    )

    # THEN the result is empty
    assert results == []
    print("DONE list_blobs_empty_owner_returns_empty")


# open_blob


@pytest.mark.mytral
def test_open_blob_returns_original_bytes(tmp_path: pathlib.Path):
    # GIVEN a stored blob with known content
    store = _make_store(tmp_path)
    meta = _gpx_metadata()
    content = b"<gpx>test content</gpx>"
    store.create_blob(meta, io.BytesIO(content))

    # WHEN opening the blob stream
    stream = store.open_blob(_USER, meta.blob_key, variant=models.BLOB_VARIANT_ORIGINAL)

    # THEN the returned bytes match the original
    assert stream.read() == content
    print("DONE open_blob_returns_original_bytes")


@pytest.mark.mytral
def test_open_blob_missing_raises(tmp_path: pathlib.Path):
    # GIVEN an empty store
    store = _make_store(tmp_path)

    # WHEN opening a non-existent blob
    # THEN BlobNotFoundError is raised
    with pytest.raises(exceptions.BlobNotFoundError):
        store.open_blob(_USER, "ghost-key", variant=models.BLOB_VARIANT_ORIGINAL)
    print("DONE open_blob_missing_raises")


@pytest.mark.mytral
def test_open_blob_missing_variant_raises(tmp_path: pathlib.Path):
    # GIVEN a stored blob without thumbnail variant
    store = _make_store(tmp_path)
    meta = _gpx_metadata()
    store.create_blob(meta, io.BytesIO(b"<gpx/>"))

    # WHEN requesting the thumbnail variant that was never written
    # THEN BlobNotFoundError is raised
    with pytest.raises(exceptions.BlobNotFoundError):
        store.open_blob(_USER, meta.blob_key, variant=models.BLOB_VARIANT_THUMBNAIL)
    print("DONE open_blob_missing_variant_raises")


# write_blob_variant


@pytest.mark.mytral
def test_write_and_open_variant(tmp_path: pathlib.Path):
    # GIVEN a blob created without a thumbnail variant
    store = _make_store(tmp_path)
    meta = _photo_metadata()
    store.create_blob(meta, io.BytesIO(b"normalized_data"))
    thumb_data = b"thumbnail_jpeg_data"

    # WHEN writing the thumbnail variant
    store.write_blob_variant(
        _USER, meta.blob_key, models.BLOB_VARIANT_THUMBNAIL, thumb_data
    )

    # THEN opening the thumbnail variant returns the written data
    stream = store.open_blob(
        _USER, meta.blob_key, variant=models.BLOB_VARIANT_THUMBNAIL
    )
    assert stream.read() == thumb_data
    print("DONE write_and_open_variant")


# update_blob_metadata


@pytest.mark.mytral
def test_update_blob_metadata_persists_changes(tmp_path: pathlib.Path):
    # GIVEN a stored blob
    store = _make_store(tmp_path)
    meta = _gpx_metadata()
    store.create_blob(meta, io.BytesIO(b"<gpx/>"))

    # WHEN updating name and keywords
    updated = store.update_blob_metadata(
        _USER,
        meta.blob_key,
        name="Updated name",
        description="New description",
        keywords=["new", "tags"],
    )
    # THEN the changes are persisted
    assert updated.name == "Updated name"
    assert updated.description == "New description"
    assert updated.keywords == ["new", "tags"]
    refetched = store.get_blob_metadata(_USER, meta.blob_key)
    assert refetched.name == "Updated name"
    print("DONE update_blob_metadata_persists_changes")


@pytest.mark.mytral
def test_update_blob_metadata_missing_raises(tmp_path: pathlib.Path):
    # GIVEN an empty store
    store = _make_store(tmp_path)

    # WHEN updating a non-existent blob
    # THEN BlobNotFoundError is raised
    with pytest.raises(exceptions.BlobNotFoundError):
        store.update_blob_metadata(
            _USER, "ghost-key", name="X", description="", keywords=[]
        )
    print("DONE update_blob_metadata_missing_raises")


@pytest.mark.mytral
def test_update_blob_metadata_persists_gpx_map_fields(tmp_path: pathlib.Path):
    # GIVEN a stored GPX blob metadata
    store = _make_store(tmp_path)
    meta = _gpx_metadata("gpx-map-001")
    store.create_blob(meta, io.BytesIO(b"<gpx/>"))

    # WHEN updating map-related metadata fields
    updated = store.update_blob_metadata(
        _USER,
        meta.blob_key,
        name=meta.name,
        description=meta.description,
        keywords=meta.keywords,
        track_count=2,
        track_point_count=321,
        summary_polyline="_p~iF~ps|U_ulLnnqC_mqEnnq`@",
        summary_bbox=(50.0, 14.0, 50.2, 14.2),
        full_polyline="_p~iF~ps|U_ulLnnqC_mqEnnq`@",
        elevation_profile=[(0.0, 210.0), (1234.5, 230.0)],
    )

    # THEN map fields are persisted and retrievable
    assert updated.track_count == 2
    assert updated.track_point_count == 321
    assert updated.summary_polyline is not None
    assert updated.summary_bbox == (50.0, 14.0, 50.2, 14.2)
    assert updated.full_polyline is not None
    assert updated.elevation_profile == [(0.0, 210.0), (1234.5, 230.0)]
    fetched = store.get_blob_metadata(_USER, meta.blob_key)
    assert fetched.track_point_count == 321
    assert fetched.summary_polyline == "_p~iF~ps|U_ulLnnqC_mqEnnq`@"
    assert fetched.elevation_profile == [(0.0, 210.0), (1234.5, 230.0)]
    print("DONE update_blob_metadata_persists_gpx_map_fields")


# delete_blob


@pytest.mark.mytral
def test_delete_blob_removes_all_files(tmp_path: pathlib.Path):
    # GIVEN a stored blob with a thumbnail variant
    store = _make_store(tmp_path)
    meta = _photo_metadata()
    store.create_blob(meta, io.BytesIO(b"img"))
    store.write_blob_variant(
        _USER, meta.blob_key, models.BLOB_VARIANT_THUMBNAIL, b"thumb"
    )
    assert store.blob_exists(_USER, meta.blob_key)

    # WHEN deleting the blob
    store.delete_blob(_USER, meta.blob_key)

    # THEN the blob no longer exists and no directory remnants remain
    assert not store.blob_exists(_USER, meta.blob_key)
    with pytest.raises(exceptions.BlobNotFoundError):
        store.get_blob_metadata(_USER, meta.blob_key)
    print("DONE delete_blob_removes_all_files")


@pytest.mark.mytral
def test_delete_blob_missing_raises(tmp_path: pathlib.Path):
    # GIVEN an empty store
    store = _make_store(tmp_path)

    # WHEN deleting a non-existent blob
    # THEN BlobNotFoundError is raised
    with pytest.raises(exceptions.BlobNotFoundError):
        store.delete_blob(_USER, "ghost-key")
    print("DONE delete_blob_missing_raises")


@pytest.mark.mytral
def test_delete_blob_no_parent_relics(tmp_path: pathlib.Path):
    # GIVEN a single blob in an activity
    store = _make_store(tmp_path)
    meta = _gpx_metadata("gpx-solo")
    store.create_blob(meta, io.BytesIO(b"<gpx/>"))
    blob_parent = (
        tmp_path / _USER / "blobs" / "activities" / _ACTIVITY_KEY / "recordings"
    )
    assert blob_parent.exists()

    # WHEN deleting the blob
    store.delete_blob(_USER, "gpx-solo")

    # THEN the blob directory is fully removed (no relic directories)
    blob_dir = blob_parent / "gpx-solo"
    assert not blob_dir.exists()
    print("DONE delete_blob_no_parent_relics")


# blob_exists


@pytest.mark.mytral
def test_blob_exists_returns_false_for_missing(tmp_path: pathlib.Path):
    # GIVEN an empty store
    store = _make_store(tmp_path)

    # WHEN checking existence of a non-existent blob
    result = store.blob_exists(_USER, "no-such-key")

    # THEN the result is False
    assert result is False
    print("DONE blob_exists_returns_false_for_missing")


@pytest.mark.mytral
def test_blob_exists_returns_true_after_create(tmp_path: pathlib.Path):
    # GIVEN a blob that has been created
    store = _make_store(tmp_path)
    meta = _gpx_metadata()
    store.create_blob(meta, io.BytesIO(b"<gpx/>"))

    # WHEN checking existence
    result = store.blob_exists(_USER, meta.blob_key)

    # THEN the result is True
    assert result is True
    print("DONE blob_exists_returns_true_after_create")


# multi-user isolation


@pytest.mark.mytral
def test_users_blobs_are_isolated(tmp_path: pathlib.Path):
    # GIVEN two users each creating a blob with the same key
    store = _make_store(tmp_path)
    meta_a = _gpx_metadata("shared-key")
    meta_a.user_id = "user_a"  # type: ignore[misc]
    meta_b = _gpx_metadata("shared-key")
    meta_b.user_id = "user_b"  # type: ignore[misc]

    # need separate metadata objects with different user_ids
    meta_a = models.BlobMetadata(
        blob_key="shared-key",
        user_id="user_a",
        owner_kind=models.BlobOwnerKind.ACTIVITY.value,
        owner_key=_ACTIVITY_KEY,
        kind=models.BlobKind.ACTIVITY_RECORDING.value,
        file_name="a.gpx",
        original_file_name="a.gpx",
        extension=".gpx",
        content_type="application/gpx+xml",
        size_bytes=10,
        sha256="aaaa",
        name="A track",
        description="",
        keywords=[],
        created_at="2024-01-01T00:00:00",
        updated_at="2024-01-01T00:00:00",
    )
    meta_b = models.BlobMetadata(
        blob_key="shared-key",
        user_id="user_b",
        owner_kind=models.BlobOwnerKind.ACTIVITY.value,
        owner_key=_ACTIVITY_KEY,
        kind=models.BlobKind.ACTIVITY_RECORDING.value,
        file_name="b.gpx",
        original_file_name="b.gpx",
        extension=".gpx",
        content_type="application/gpx+xml",
        size_bytes=10,
        sha256="bbbb",
        name="B track",
        description="",
        keywords=[],
        created_at="2024-01-01T00:00:00",
        updated_at="2024-01-01T00:00:00",
    )

    # WHEN both users create blobs with the same blob_key
    store.create_blob(meta_a, io.BytesIO(b"data_a"))
    store.create_blob(meta_b, io.BytesIO(b"data_b"))

    # THEN each user sees their own data and not the other's
    result_a = store.get_blob_metadata("user_a", "shared-key")
    result_b = store.get_blob_metadata("user_b", "shared-key")
    assert result_a.name == "A track"
    assert result_b.name == "B track"
    stream_a = store.open_blob(
        "user_a", "shared-key", variant=models.BLOB_VARIANT_ORIGINAL
    )
    stream_b = store.open_blob(
        "user_b", "shared-key", variant=models.BLOB_VARIANT_ORIGINAL
    )
    assert stream_a.read() == b"data_a"
    assert stream_b.read() == b"data_b"
    print("DONE users_blobs_are_isolated")


# adversarial / security tests


@pytest.mark.mytral
def test_path_traversal_in_user_id_raises(tmp_path: pathlib.Path):
    # GIVEN a filesystem store
    store = _make_store(tmp_path)

    # WHEN a user_id containing path-traversal characters is supplied
    # THEN a ValueError is raised before any disk access
    with pytest.raises(ValueError, match="path component"):
        store.get_blob_metadata("../other_user", "blob-001")
    print("DONE path_traversal_in_user_id_raises")


@pytest.mark.mytral
def test_path_traversal_in_blob_key_raises(tmp_path: pathlib.Path):
    # GIVEN a filesystem store
    store = _make_store(tmp_path)

    # WHEN a blob_key containing a forward-slash is supplied
    # THEN a ValueError is raised
    with pytest.raises(ValueError, match="path component"):
        store.get_blob_metadata(_USER, "../../etc/passwd")
    print("DONE path_traversal_in_blob_key_raises")


@pytest.mark.mytral
def test_path_traversal_backslash_in_blob_key_raises(tmp_path: pathlib.Path):
    # GIVEN a filesystem store
    store = _make_store(tmp_path)

    # WHEN a blob_key containing a backslash is supplied
    # THEN a ValueError is raised (backslash is a Windows path separator and rejected
    # defensively even on Linux to avoid misuse on mixed-OS deployments)
    with pytest.raises(ValueError, match="path component"):
        store.get_blob_metadata(_USER, "blob\\..\\secret")
    print("DONE path_traversal_backslash_in_blob_key_raises")


@pytest.mark.mytral
def test_corrupt_metadata_json_raises(tmp_path: pathlib.Path):
    # GIVEN a blob directory whose metadata.json is corrupt
    store = _make_store(tmp_path)
    meta = _gpx_metadata()
    store.create_blob(meta, io.BytesIO(b"<gpx/>"))
    blob_dir = store._blob_dir_from_key(_USER, meta.blob_key)
    (blob_dir / "metadata.json").write_text("NOT_VALID_JSON")

    # WHEN fetching metadata for that blob
    # THEN an appropriate exception is raised (not a bare crash)
    with pytest.raises(Exception):
        store.get_blob_metadata(_USER, meta.blob_key)
    print("DONE corrupt_metadata_json_raises")


@pytest.mark.mytral
def test_cross_user_access_raises(tmp_path: pathlib.Path):
    # GIVEN user_a has a blob and user_b tries to read it
    store = _make_store(tmp_path)
    meta = _gpx_metadata()
    store.create_blob(meta, io.BytesIO(b"<gpx/>"))

    # WHEN user_b requests the blob that belongs to user_a
    # THEN a BlobNotFoundError is raised (no data leakage)
    with pytest.raises(exceptions.BlobNotFoundError):
        store.get_blob_metadata("user_b", meta.blob_key)
    print("DONE cross_user_access_raises")
