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
"""Upload validation for GPX files and activity photos."""

import io
import typing
import xml.etree.ElementTree

import defusedxml.ElementTree

from mytral.blobstore.exceptions import BlobValidationError

try:
    import PIL.Image  # type: ignore[import-untyped]
except ImportError:
    PIL = None  # type: ignore[assignment]

# GPX

GPX_ALLOWED_EXTENSIONS = {".gpx"}

GPX_ALLOWED_CONTENT_TYPES = {
    "application/gpx+xml",
    "application/xml",
    "text/xml",
    "application/octet-stream",
}

GPX_NAMESPACE_PREFIX = "http://www.topografix.com/GPX"

# PHOTO

PHOTO_ALLOWED_EXTENSIONS = {".jpg", ".jpeg", ".png", ".webp"}

PHOTO_EXTENSION_TO_CONTENT_TYPE = {
    ".jpg": "image/jpeg",
    ".jpeg": "image/jpeg",
    ".png": "image/png",
    ".webp": "image/webp",
}

# maps file extension to the Pillow format name reported by img.format
_PHOTO_EXTENSION_TO_PILLOW_FORMAT = {
    ".jpg": "JPEG",
    ".jpeg": "JPEG",
    ".png": "PNG",
    ".webp": "WEBP",
}

PHOTO_ALLOWED_CONTENT_TYPES = set(PHOTO_EXTENSION_TO_CONTENT_TYPE.values())

# METADATA

BLOB_NAME_MAX_LEN = 120
BLOB_DESCRIPTION_MAX_LEN = 1000
BLOB_KEYWORDS_MAX_COUNT = 20
BLOB_KEYWORD_MAX_LEN = 40


#
# GPX validation
#


def validate_gpx_extension(filename: str) -> str:
    """Validate and return the lowercase extension of a GPX filename.

    Parameters
    ----------
    filename : str
        Original upload filename.

    Returns
    -------
    str
        Lowercase extension including the leading dot.

    Raises
    ------
    BlobValidationError
        If the extension is not allowed.
    """
    lower = filename.lower()
    for ext in GPX_ALLOWED_EXTENSIONS:
        if lower.endswith(ext):
            return ext
    raise BlobValidationError(
        f"GPX file must have one of these extensions: "
        f"{', '.join(sorted(GPX_ALLOWED_EXTENSIONS))}. Got: '{filename}'."
    )


def validate_gpx_content_type(content_type: str, extension: str) -> None:
    """Validate that the content-type is acceptable for a GPX upload.

    Parameters
    ----------
    content_type : str
        MIME type from the upload.
    extension : str
        Already-validated file extension.

    Raises
    ------
    BlobValidationError
        If the content type is not allowed.
    """
    ct = (content_type or "").split(";")[0].strip().lower()
    if ct == "application/octet-stream" and extension != ".gpx":
        raise BlobValidationError(
            "application/octet-stream is only accepted for .gpx files."
        )
    if ct not in GPX_ALLOWED_CONTENT_TYPES:
        raise BlobValidationError(
            f"Unsupported content type for GPX: '{ct}'. "
            f"Accepted: {', '.join(sorted(GPX_ALLOWED_CONTENT_TYPES))}."
        )


def validate_gpx_size(size_bytes: int, max_bytes: int) -> None:
    """Validate that a GPX file does not exceed the size limit.

    Parameters
    ----------
    size_bytes : int
        Actual file size in bytes.
    max_bytes : int
        Maximum allowed size in bytes.

    Raises
    ------
    BlobValidationError
        If the file is too large.
    """
    if size_bytes > max_bytes:
        raise BlobValidationError(
            f"GPX file is too large: {size_bytes} bytes "
            f"(max {max_bytes // (1024 * 1024)} MiB)."
        )


def parse_gpx(data: bytes) -> tuple[int, int]:
    """Parse a GPX byte payload and return (track_count, track_point_count).

    Parameters
    ----------
    data : bytes
        Raw GPX file content.

    Returns
    -------
    tuple[int, int]
        ``(track_count, track_point_count)``

    Raises
    ------
    BlobValidationError
        If the data is not valid XML or not a GPX document.
    """
    try:
        root = defusedxml.ElementTree.fromstring(data)
    except (xml.etree.ElementTree.ParseError, ValueError) as exc:
        raise BlobValidationError(f"GPX file is not valid XML: {exc}") from exc

    tag = root.tag
    # tag is either plain "gpx" or namespace-qualified "{http://...}gpx"
    local = tag.split("}")[-1] if "}" in tag else tag
    if local.lower() != "gpx":
        raise BlobValidationError(f"File root element is '{local}', expected 'gpx'.")

    ns_prefix = ""
    if "}" in tag:
        ns_prefix = tag.split("}")[0] + "}"

    tracks = root.findall(f"{ns_prefix}trk")
    track_count = len(tracks)
    track_point_count = sum(len(trk.findall(f".//{ns_prefix}trkpt")) for trk in tracks)
    return track_count, track_point_count


def validate_gpx(
    filename: str,
    content_type: str,
    data: bytes,
    max_bytes: int,
) -> tuple[str, int, int]:
    """Full validation pipeline for a GPX upload.

    Parameters
    ----------
    filename : str
        Original upload filename.
    content_type : str
        MIME type from the upload.
    data : bytes
        File payload.
    max_bytes : int
        Maximum allowed size in bytes.

    Returns
    -------
    tuple[str, int, int]
        ``(extension, track_count, track_point_count)``

    Raises
    ------
    BlobValidationError
        On any validation failure.
    """
    ext = validate_gpx_extension(filename)
    validate_gpx_content_type(content_type, ext)
    validate_gpx_size(len(data), max_bytes)
    track_count, track_point_count = parse_gpx(data)
    return ext, track_count, track_point_count


#
# Photo validation
#


def validate_photo_extension(filename: str) -> str:
    """Validate and return the lowercase extension of a photo filename.

    Parameters
    ----------
    filename : str
        Original upload filename.

    Returns
    -------
    str
        Lowercase extension including the leading dot.

    Raises
    ------
    BlobValidationError
        If the extension is not allowed.
    """
    lower = filename.lower()
    for ext in PHOTO_ALLOWED_EXTENSIONS:
        if lower.endswith(ext):
            return ext
    raise BlobValidationError(
        f"Photo must have one of these extensions: "
        f"{', '.join(sorted(PHOTO_ALLOWED_EXTENSIONS))}. Got: '{filename}'."
    )


def validate_photo_size(size_bytes: int, max_bytes: int) -> None:
    """Validate that a photo does not exceed the size limit.

    Parameters
    ----------
    size_bytes : int
        Actual file size in bytes.
    max_bytes : int
        Maximum allowed size in bytes.

    Raises
    ------
    BlobValidationError
        If the file is too large.
    """
    if size_bytes > max_bytes:
        raise BlobValidationError(
            f"Photo is too large: {size_bytes} bytes "
            f"(max {max_bytes // (1024 * 1024)} MiB)."
        )


def validate_photo_decode(data: bytes, extension: str = "") -> tuple[int, int]:
    """Attempt to decode image data with Pillow to confirm it is a valid image.

    Also verifies that the actual image format (as reported by Pillow) matches
    the declared file extension when ``extension`` is provided.

    Parameters
    ----------
    data : bytes
        Raw image bytes.
    extension : str
        Lowercase file extension including the leading dot (e.g. ``.jpg``).
        When provided, the Pillow-detected format is checked against it.

    Returns
    -------
    tuple[int, int]
        ``(width, height)`` in pixels.

    Raises
    ------
    BlobValidationError
        If Pillow is not installed, the data cannot be decoded, or the actual
        image format does not match the declared extension.
    """
    if PIL is None:
        raise BlobValidationError(
            "Pillow is required for photo upload. Install the blob-common dependency "
            "group: uv sync --group blob-common"
        )

    try:
        img = PIL.Image.open(io.BytesIO(data))
        img.verify()
    except Exception as exc:
        raise BlobValidationError(f"Photo cannot be decoded: {exc}") from exc

    # reopen for size and format verification since verify() closes the file
    try:
        img2 = PIL.Image.open(io.BytesIO(data))
        detected_format = (img2.format or "").upper()
        if extension:
            expected_format = _PHOTO_EXTENSION_TO_PILLOW_FORMAT.get(extension.lower())
            if expected_format and detected_format != expected_format:
                raise BlobValidationError(
                    f"File content is {detected_format} but extension '{extension}' "
                    f"expects {expected_format}. Upload the correct file type."
                )
        return img2.width, img2.height
    except BlobValidationError:
        raise
    except Exception as exc:
        raise BlobValidationError(f"Photo size could not be read: {exc}") from exc


def validate_photo(
    filename: str,
    data: bytes,
    max_bytes: int,
) -> tuple[str, int, int]:
    """Full validation pipeline for a photo upload.

    Parameters
    ----------
    filename : str
        Original upload filename.
    data : bytes
        File payload.
    max_bytes : int
        Maximum allowed size in bytes.

    Returns
    -------
    tuple[str, int, int]
        ``(extension, width, height)``

    Raises
    ------
    BlobValidationError
        On any validation failure.
    """
    ext = validate_photo_extension(filename)
    validate_photo_size(len(data), max_bytes)
    width, height = validate_photo_decode(data, extension=ext)
    return ext, width, height


#
# Recording validation
#

RECORDING_ALLOWED_EXTENSIONS: frozenset[str] = frozenset({".fit", ".gpx", ".hrm"})
RECORDING_MAX_BYTES: int = 64 * 1024 * 1024  # 64 MiB


def validate_recording(
    filename: str,
    data: bytes,
    max_bytes: int = RECORDING_MAX_BYTES,
) -> str:
    """Validate a recording upload (FIT / GPX / HRM).

    Parameters
    ----------
    filename : str
        Original upload filename.
    data : bytes
        File payload.
    max_bytes : int
        Maximum allowed size in bytes.

    Returns
    -------
    str
        Lowercase file extension (e.g. ``".fit"``).

    Raises
    ------
    BlobValidationError
        On any validation failure.
    """
    if not filename:
        raise BlobValidationError("Recording filename must not be empty.")

    ext = "." + filename.rsplit(".", 1)[-1].lower() if "." in filename else ""
    if ext not in RECORDING_ALLOWED_EXTENSIONS:
        raise BlobValidationError(
            f"Unsupported recording extension '{ext}'. "
            f"Allowed: {sorted(RECORDING_ALLOWED_EXTENSIONS)}."
        )
    if len(data) == 0:
        raise BlobValidationError("Recording file is empty.")
    if len(data) > max_bytes:
        raise BlobValidationError(
            f"Recording file exceeds the maximum allowed size of "
            f"{max_bytes // (1024 * 1024)} MiB."
        )

    # magic-byte checks
    if ext == ".fit":
        if len(data) < 12 or data[8:12] != b".FIT":
            raise BlobValidationError(
                "File does not appear to be a valid FIT file (bad magic bytes)."
            )
    elif ext == ".gpx":
        # strip optional UTF-8 BOM before checking the XML declaration
        payload = data.lstrip(b"\xef\xbb\xbf").lstrip()
        if not (payload.startswith(b"<?xml") or payload.startswith(b"<gpx")):
            raise BlobValidationError(
                "File does not appear to be a valid GPX file (missing XML header)."
            )
    elif ext == ".hrm":
        if b"[Params]" not in data:
            raise BlobValidationError(
                "File does not appear to be a valid Polar HRM file "
                "(missing [Params] section)."
            )

    return ext


#
# Metadata validation
#


def validate_blob_metadata(
    name: str,
    description: str,
    keywords_raw: str | list[str],
) -> tuple[str, str, list[str]]:
    """Validate and normalize blob user metadata fields.

    Parameters
    ----------
    name : str
        User-supplied name.
    description : str
        User-supplied description.
    keywords_raw : str | list[str]
        Keywords as a comma-separated string or an already-split list.

    Returns
    -------
    tuple[str, str, list[str]]
        ``(name, description, keywords)`` after validation and normalization.

    Raises
    ------
    BlobValidationError
        If any field exceeds its length limit.
    """
    name = name.strip()
    description = description.strip()

    if len(name) > BLOB_NAME_MAX_LEN:
        raise BlobValidationError(
            f"Name too long: {len(name)} chars (max {BLOB_NAME_MAX_LEN})."
        )
    if len(description) > BLOB_DESCRIPTION_MAX_LEN:
        raise BlobValidationError(
            f"Description too long: {len(description)} chars "
            f"(max {BLOB_DESCRIPTION_MAX_LEN})."
        )

    if isinstance(keywords_raw, str):
        raw_list: list[str] = [k for k in keywords_raw.split(",") if k.strip()]
    else:
        raw_list = list(keywords_raw)

    keywords: list[str] = []
    seen: set[str] = set()
    for kw in raw_list:
        kw_norm = kw.strip().lower()
        if not kw_norm:
            continue
        if len(kw_norm) > BLOB_KEYWORD_MAX_LEN:
            raise BlobValidationError(
                f"Keyword '{kw_norm}' is too long: {len(kw_norm)} chars "
                f"(max {BLOB_KEYWORD_MAX_LEN})."
            )
        if kw_norm not in seen:
            seen.add(kw_norm)
            keywords.append(kw_norm)

    if len(keywords) > BLOB_KEYWORDS_MAX_COUNT:
        raise BlobValidationError(
            f"Too many keywords: {len(keywords)} (max {BLOB_KEYWORDS_MAX_COUNT})."
        )

    return name, description, keywords


def read_stream_to_bytes(stream: typing.BinaryIO, max_bytes: int) -> bytes:
    """Read up to max_bytes from a binary stream.

    Parameters
    ----------
    stream : typing.BinaryIO
        Readable binary stream.
    max_bytes : int
        Maximum bytes to read. If the stream has more data, raises an error.

    Returns
    -------
    bytes
        The bytes read.

    Raises
    ------
    BlobValidationError
        If the stream exceeds max_bytes.
    """
    data = stream.read(max_bytes + 1)
    if len(data) > max_bytes:
        raise BlobValidationError(
            f"Upload exceeds maximum allowed size of {max_bytes // (1024 * 1024)} MiB."
        )
    return data
