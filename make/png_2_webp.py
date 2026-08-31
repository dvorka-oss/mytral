#!/usr/bin/env python3
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
"""
Convert PNG image(s) to WEBP.

Usage:
  uv run python make/png-2-webp.py <path-to-file-or-directory> [--quality N] [--keep]

  <path-to-file-or-directory>  a single .png file, or a directory to convert
                                every .png file found in it (recursively)
  --quality N                  WEBP quality, 0-100 (default: 85)
  --keep                       keep the source .png file (default: delete it
                                after a successful conversion)
"""

import argparse
import sys
from pathlib import Path

from PIL import Image

DEFAULT_QUALITY = 85


def convert_png_to_webp(png_path: Path, quality: int, keep: bool) -> None:
    """Convert a single PNG file to WEBP alongside it."""
    webp_path = png_path.with_suffix(".webp")
    image = Image.open(png_path)
    image.save(webp_path, "WEBP", quality=quality)

    png_size = png_path.stat().st_size
    webp_size = webp_path.stat().st_size
    print(
        f"  {png_path.name} -> {webp_path.name}  "
        f"{png_size // 1024} KB -> {webp_size // 1024} KB"
    )

    if not keep:
        png_path.unlink()


def find_png_files(target: Path) -> list[Path]:
    """Resolve a file-or-directory argument to a list of .png files."""
    if target.is_file():
        return [target]
    return sorted(target.rglob("*.png"))


def main() -> None:
    parser = argparse.ArgumentParser(description="Convert PNG image(s) to WEBP.")
    parser.add_argument("path", type=Path, help="PNG file or directory to convert")
    parser.add_argument(
        "--quality",
        type=int,
        default=DEFAULT_QUALITY,
        help=f"WEBP quality, 0-100 (default: {DEFAULT_QUALITY})",
    )
    parser.add_argument(
        "--keep",
        action="store_true",
        help="keep the source .png file instead of deleting it",
    )
    args = parser.parse_args()

    if not args.path.exists():
        print(f"ERROR: path not found: {args.path}", file=sys.stderr)
        sys.exit(1)

    png_files = find_png_files(args.path)
    if not png_files:
        print(f"ERROR: no .png files found under: {args.path}", file=sys.stderr)
        sys.exit(1)

    print(f"Converting {len(png_files)} PNG file(s) to WEBP...")
    for png_path in png_files:
        convert_png_to_webp(png_path, args.quality, args.keep)
    print("DONE")


if __name__ == "__main__":
    main()
