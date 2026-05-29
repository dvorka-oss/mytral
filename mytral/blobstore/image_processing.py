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
"""Image normalization and thumbnail generation using Pillow."""

import io

from mytral.blobstore.exceptions import BlobValidationError

try:
    import PIL.Image  # type: ignore[import-untyped]
    import PIL.ImageOps  # type: ignore[import-untyped]

    _PILLOW_AVAILABLE = True
except ImportError:
    PIL = None  # type: ignore[assignment]
    _PILLOW_AVAILABLE = False


def _require_pillow():
    """Return (PIL.Image, PIL.ImageOps), raise BlobValidationError when unavailable."""
    if not _PILLOW_AVAILABLE:
        raise BlobValidationError(
            "Pillow is required for photo processing. Install the blob-common "
            "dependency group: uv sync --group blob-common"
        )
    return PIL.Image, PIL.ImageOps


def normalize_avatar(
    data: bytes,
    extension: str,
    size_px: int = 200,
    jpeg_quality: int = 85,
) -> tuple[bytes, str, int, int]:
    """Normalize an avatar photo: center-crop to square, resize, strip EXIF.

    Parameters
    ----------
    data : bytes
        Raw image bytes.
    extension : str
        Source file extension (e.g. ``.jpg``). Output is always JPEG.
    size_px : int
        Output square size in pixels (width == height).
    jpeg_quality : int
        JPEG encoding quality (1-95).

    Returns
    -------
    tuple[bytes, str, int, int]
        ``(jpeg_bytes, "jpeg", size_px, size_px)``

    Raises
    ------
    BlobValidationError
        If Pillow is not installed or the image cannot be processed.
    """
    PIL_Image, PIL_ImageOps = _require_pillow()

    try:
        img = PIL_Image.open(io.BytesIO(data))
        img = img.convert("RGB") if img.mode not in ("RGB", "RGBA", "L") else img

        # auto-rotate from EXIF orientation, then drop metadata to protect user privacy
        img = PIL_ImageOps.exif_transpose(img)
        if isinstance(img.info, dict):
            img.info.pop("exif", None)

        # center-crop to square
        w, h = img.size
        side = min(w, h)
        left = (w - side) // 2
        top = (h - side) // 2
        img = img.crop((left, top, left + side, top + side))

        # resize to target square
        img = img.resize((size_px, size_px), PIL_Image.LANCZOS)

        # always encode as JPEG
        if img.mode == "RGBA":
            img = img.convert("RGB")

        buf = io.BytesIO()
        img.save(buf, format="JPEG", quality=jpeg_quality, optimize=True)
        return buf.getvalue(), "jpeg", size_px, size_px
    except BlobValidationError:
        raise
    except Exception as exc:
        raise BlobValidationError(f"Avatar normalization failed: {exc}") from exc


def normalize_photo(
    data: bytes,
    extension: str,
    max_dimension_px: int,
    jpeg_quality: int = 85,
) -> tuple[bytes, str, int, int]:
    """Normalize a photo: auto-rotate from EXIF, strip metadata, resize if needed.

    Parameters
    ----------
    data : bytes
        Raw image bytes.
    extension : str
        Source file extension (e.g. ``.jpg``).
    max_dimension_px : int
        Maximum width or height in pixels. Images larger than this are resized
        while preserving the aspect ratio.
    jpeg_quality : int
        JPEG encoding quality (1-95). Only applies to JPEG output.

    Returns
    -------
    tuple[bytes, str, int, int]
        ``(normalized_bytes, format_name, width, height)``

    Raises
    ------
    BlobValidationError
        If Pillow is not installed or the image cannot be processed.
    """
    PIL_Image, PIL_ImageOps = _require_pillow()

    try:
        img = PIL_Image.open(io.BytesIO(data))
        img = img.convert("RGB") if img.mode not in ("RGB", "RGBA", "L") else img

        # auto-rotate from EXIF orientation, then drop metadata to protect user privacy
        img = PIL_ImageOps.exif_transpose(img)
        if isinstance(img.info, dict):
            img.info.pop("exif", None)

        width, height = img.size
        if width > max_dimension_px or height > max_dimension_px:
            img.thumbnail((max_dimension_px, max_dimension_px), PIL_Image.LANCZOS)
            width, height = img.size

        ext_lower = extension.lower()
        if ext_lower in (".jpg", ".jpeg"):
            fmt = "JPEG"
            if img.mode == "RGBA":
                img = img.convert("RGB")
        elif ext_lower == ".png":
            fmt = "PNG"
        elif ext_lower == ".webp":
            fmt = "WEBP"
        else:
            fmt = "JPEG"
            if img.mode == "RGBA":
                img = img.convert("RGB")

        buf = io.BytesIO()
        if fmt == "JPEG":
            img.save(buf, format=fmt, quality=jpeg_quality, optimize=True)
        else:
            img.save(buf, format=fmt, optimize=True)
        return buf.getvalue(), fmt.lower(), width, height
    except BlobValidationError:
        raise
    except Exception as exc:
        raise BlobValidationError(f"Image normalization failed: {exc}") from exc


def generate_thumbnail(
    data: bytes,
    max_dimension_px: int,
    jpeg_quality: int = 82,
) -> bytes:
    """Generate a JPEG thumbnail from normalized image bytes.

    Parameters
    ----------
    data : bytes
        Normalized image bytes (already processed by normalize_photo).
    max_dimension_px : int
        Maximum width or height for the thumbnail.
    jpeg_quality : int
        JPEG encoding quality (1-95).

    Returns
    -------
    bytes
        JPEG thumbnail bytes.

    Raises
    ------
    BlobValidationError
        If Pillow is not installed or the thumbnail cannot be generated.
    """
    PIL_Image, PIL_ImageOps = _require_pillow()

    try:
        img = PIL_Image.open(io.BytesIO(data))
        img = img.convert("RGB")
        img.thumbnail((max_dimension_px, max_dimension_px), PIL_Image.LANCZOS)

        buf = io.BytesIO()
        img.save(buf, format="JPEG", quality=jpeg_quality, optimize=True)
        return buf.getvalue()
    except BlobValidationError:
        raise
    except Exception as exc:
        raise BlobValidationError(f"Thumbnail generation failed: {exc}") from exc
