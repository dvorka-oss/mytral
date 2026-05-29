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
import dataclasses
import enum
import typing

from mytral.blobstore.exceptions import BlobValidationError


class BlobKind(enum.Enum):
    """Semantic category of a blob."""

    ACTIVITY_RECORDING = "activity_recording"
    ACTIVITY_PARQUET = "activity_parquet"
    ACTIVITY_PHOTO = "activity_photo"
    USER_AVATAR = "user_avatar"
    ACOACH_AVATAR = "acoach_avatar"
    GEAR_PHOTO = "gear_photo"
    EXERCISE_PHOTO = "exercise_photo"
    GOAL_PHOTO = "goal_photo"


class BlobOwnerKind(enum.Enum):
    """The domain entity that owns a blob."""

    ACTIVITY = "activity"
    USER = "user"
    ACOACH = "acoach"
    GEAR = "gear"
    EXERCISE = "exercise"
    GOAL = "goal"


# variant names for open_blob()
BLOB_VARIANT_ORIGINAL = "original"
BLOB_VARIANT_NORMALIZED = "normalized"
BLOB_VARIANT_THUMBNAIL = "thumbnail"


@dataclasses.dataclass
class BlobMetadata:
    """Backend-independent, JSON-serializable metadata for a single blob.

    Parameters
    ----------
    blob_key : str
        Globally unique identifier for this blob within the user's store.
    user_id : str
        Owning user identifier.
    owner_kind : str
        Domain owner kind (see BlobOwnerKind).
    owner_key : str
        Owner entity primary key (e.g. activity UUID).
    kind : str
        Blob semantic category (see BlobKind).
    file_name : str
        Normalized storage file name (no path, safe for all backends).
    original_file_name : str
        Original upload file name as provided by the user.
    extension : str
        File extension including leading dot, lowercase, e.g. ``.jpg``.
    content_type : str
        MIME content type.
    size_bytes : int
        Size of the original uploaded payload in bytes.
    sha256 : str
        Hex-encoded SHA-256 digest of the original uploaded payload.
    name : str
        Human-readable user-assigned name.
    description : str
        User-assigned description text.
    keywords : list[str]
        Normalized (lowercase, trimmed, deduplicated) keyword tags.
    created_at : str
        ISO-8601 creation timestamp (UTC).
    updated_at : str
        ISO-8601 last-updated timestamp (UTC).
    width : int
        Image width in pixels (photos only, 0 otherwise).
    height : int
        Image height in pixels (photos only, 0 otherwise).
    thumbnail_available : bool
        Whether a thumbnail variant was generated (photos only).
    normalized_format : str
        Format string of the normalized variant, e.g. ``jpeg`` (photos only).
    track_point_count : int
        Number of GPX track points parsed from the file (GPX only).
    track_count : int
        Number of GPX tracks parsed from the file (GPX only).
    summary_polyline : str | None
        Encoded polyline suitable for lightweight preview rendering.
    summary_bbox : tuple[float, float, float, float] | None
        Bounding box as ``(min_lat, min_lon, max_lat, max_lon)``.
    full_polyline : str | None
        Encoded polyline with full detail for the activity map.
    elevation_profile : list[tuple[float, float]] | None
        Simplified ``(distance_m, elevation_m)`` profile for detail chart.
    """

    blob_key: str
    user_id: str
    owner_kind: str
    owner_key: str
    kind: str

    file_name: str
    original_file_name: str
    extension: str
    content_type: str
    size_bytes: int
    sha256: str

    name: str
    description: str
    keywords: list[str]

    created_at: str
    updated_at: str

    width: int = 0
    height: int = 0
    thumbnail_available: bool = False
    normalized_format: str = ""

    track_point_count: int = 0
    track_count: int = 0
    summary_polyline: str | None = None
    summary_bbox: tuple[float, float, float, float] | None = None
    full_polyline: str | None = None
    elevation_profile: list[tuple[float, float]] | None = None

    def to_dict(self) -> dict:
        """Serialize to a plain dict suitable for JSON serialization."""
        return dataclasses.asdict(self)

    @staticmethod
    def from_dict(data: dict) -> "BlobMetadata":
        """Deserialize from a plain dict loaded from JSON."""
        summary_bbox = data.get("summary_bbox")
        if summary_bbox is not None:
            try:
                data["summary_bbox"] = (
                    float(summary_bbox[0]),
                    float(summary_bbox[1]),
                    float(summary_bbox[2]),
                    float(summary_bbox[3]),
                )
            except (IndexError, TypeError, ValueError) as exc:
                raise BlobValidationError(
                    f"Invalid summary_bbox in blob metadata: {exc}"
                ) from exc
        elevation_profile = data.get("elevation_profile")
        if elevation_profile is not None:
            try:
                data["elevation_profile"] = [
                    (float(point[0]), float(point[1])) for point in elevation_profile
                ]
            except (IndexError, TypeError, ValueError) as exc:
                raise BlobValidationError(
                    f"Invalid elevation_profile in blob metadata: {exc}"
                ) from exc
        return BlobMetadata(**data)


@dataclasses.dataclass
class BlobRecord:
    """Combines metadata with an optional binary data stream.

    This is a convenience type for callers that need to pass metadata and the
    raw content together (e.g., export pipelines, backup utilities).  The store
    itself returns ``BlobMetadata`` from most operations and populates
    ``data_stream`` only via ``open_blob()`` calls.

    Parameters
    ----------
    metadata : BlobMetadata
        Blob metadata.
    data_stream : typing.BinaryIO | None
        Readable binary stream of the blob content, or None.
    """

    metadata: BlobMetadata
    data_stream: typing.BinaryIO | None = None
