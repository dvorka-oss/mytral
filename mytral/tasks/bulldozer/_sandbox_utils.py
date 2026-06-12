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
# along with this program.  If not, see <http://www.gnu.org/licenses/>.

"""Shared utilities for bulldozer sandbox blob processing.

Functions that were duplicated across ``strava_archive_import.py`` and
``polar_hrm_import.py`` are consolidated here to keep the import tasks DRY.
"""

import json
import pathlib
import uuid

from mytral.blobstore.models import BlobMetadata
from mytral.blobstore.models import BlobOwnerKind


class _PathEncoder(json.JSONEncoder):
    """JSON encoder that converts pathlib.Path objects to strings."""

    def default(self, o):
        if isinstance(o, pathlib.PurePath):
            return str(o)
        return super().default(o)


def _sandbox_blobs_dir(job_dir: pathlib.Path, user_id: str) -> pathlib.Path:
    """Return the sandbox blobstore root directory for a given job.

    Matches the internal layout of ``FilesystemBlobStore`` constructed with
    ``base_dir=MytralConfig(persistence_data_dir=job_dir/"work").user_data_dir``
    and ``blobs_subdir="blobs"``::

        job_dir / "work" / "data" / <user_id> / "blobs"
    """
    return job_dir / "work" / "data" / user_id / "blobs"


def _make_blob_metadata(
    user_id: str,
    activity_key: str,
    kind: str,
    file_name: str,
    original_file_name: str,
    extension: str,
    size_bytes: int,
    sha256: str,
    content_type: str = "application/octet-stream",
    name: str = "",
    description: str = "",
    keywords: list[str] | None = None,
    created_at: str = "",
    width: int = 0,
    height: int = 0,
    thumbnail_available: bool = False,
) -> BlobMetadata:
    """Build a ``BlobMetadata`` with a canonical dashless blob key.

    All call sites across Strava, Polar, and FIT imports use this single
    factory so that blob keys have a consistent format (UUID without dashes,
    matching ``ActivityBlobService._new_blob_key``).
    """
    blob_key = str(uuid.uuid4()).replace("-", "")
    return BlobMetadata(
        blob_key=blob_key,
        user_id=user_id,
        owner_kind=BlobOwnerKind.ACTIVITY.value,
        owner_key=activity_key,
        kind=kind,
        file_name=file_name,
        original_file_name=original_file_name,
        extension=extension,
        content_type=content_type,
        size_bytes=size_bytes,
        sha256=sha256,
        name=name,
        description=description,
        keywords=keywords or [],
        created_at=created_at,
        updated_at=created_at,
        width=width,
        height=height,
        thumbnail_available=thumbnail_available,
    )


def _split_evenly(items: list, num_chunks: int) -> list[list]:
    """Distribute items round-robin across *num_chunks* buckets.

    Returns only non-empty chunks.  When there are no items or fewer than
    two chunks are requested the whole list is returned as a single chunk.
    """
    if not items or num_chunks <= 1:
        return [items]
    chunks: list[list] = [[] for _ in range(num_chunks)]
    for i, item in enumerate(items):
        chunks[i % num_chunks].append(item)
    return [c for c in chunks if c]
