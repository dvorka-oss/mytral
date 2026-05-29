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
Preprocess license files from licenses/ directory to a single Markdown file.

This script:
1. Reads all .txt files in ./licenses/
2. Identifies library names and license types
3. Groups libraries by license type
4. Generates ./docs/LICENSES.md with a table of contents and full license texts
"""

import sys
from pathlib import Path


def get_library_name(file_path: Path) -> str:
    """
    Get library name from filename.

    Parameters
    ----------
    file_path : Path
        path to the license file

    Returns
    -------
    str
        formatted library name
    """
    stem = file_path.stem
    # special cases
    if stem == "flask-license":
        return "Flask"
    if stem == "w3.css":
        return "W3.CSS"
    if stem == "tabler":
        return "Tabler"

    # default: replace dashes with spaces and title case
    return stem.replace("-", " ").title()


def get_license_type(content: str) -> str:
    """
    Identify license type from the content.

    Parameters
    ----------
    content : str
        full text of the license

    Returns
    -------
    str
        identified license type
    """
    lines = [line.strip() for line in content.splitlines() if line.strip()]
    if not lines:
        return "Other"

    # check first few lines
    header = " ".join(lines[:3]).lower()

    if "mit" in header:
        return "MIT License"
    if "bsd" in header and "3-clause" in header:
        return "BSD 3-Clause License"
    if "apache" in header:
        return "Apache License 2.0"
    if "zope" in header or "zpl" in header:
        return "ZPL 2.1"
    if "unlicense" in header or "public domain" in header:
        return "Public Domain"
    if "isc" in header:
        return "ISC License"
    if "font awesome" in header:
        return "Font Awesome License"
    if "w3.css" in header or "w3schools" in header:
        return "Free to Use"
    if "gnu" in header or "gpl" in header:
        return "GPL or similar"
    if "python software foundation" in header or "psfl" in header:
        return "Python Software Foundation License"

    return "Other"


def generate_markdown(groups: dict[str, list[tuple[str, str]]]) -> str:
    """
    Generate Markdown content from grouped licenses.

    Parameters
    ----------
    groups : dict
        license types mapping to lists of (library_name, content) tuples

    Returns
    -------
    str
        complete Markdown content
    """
    lines = []
    lines.append("# 3rd Party Licenses\n")
    lines.append(
        "MyTraL is built on the shoulders of excellent open source projects. "
        "This page provides full attribution and license texts for all "
        "third-party dependencies used in the application. License files "
        "are stored in the `licenses/` directory of the source repository.\n"
    )

    # table of contents
    lines.append("## Table of Contents\n")
    sorted_types = sorted(groups.keys())
    for ltype in sorted_types:
        anchor = ltype.lower().replace(" ", "-").replace(".", "").replace("/", "")
        lines.append(f"* [{ltype}](#{anchor})")
    lines.append("")

    # license sections
    for ltype in sorted_types:
        anchor = ltype.lower().replace(" ", "-").replace(".", "").replace("/", "")
        lines.append(f"## {ltype}\n")
        lines.append(f"The following components are licensed under the {ltype}:\n")

        # sort libraries within the group
        libs = sorted(groups[ltype], key=lambda x: x[0].lower())

        for lib_name, _ in libs:
            lines.append(f"* **{lib_name}**")
        lines.append("")

        for lib_name, content in libs:
            lines.append(f"### {lib_name} License Text\n")
            lines.append("```")
            # ensure content ends with a newline and doesn't have trailing whitespace
            cleaned_content = content.strip()
            lines.append(cleaned_content)
            lines.append("```\n")

    return "\n".join(lines)


def main() -> None:
    """Main entry point for the script."""
    repo_root = Path(__file__).parent.parent
    licenses_dir = repo_root / "licenses"
    output_file = repo_root / "docs" / "LICENSES.md"

    if not licenses_dir.exists():
        print(f"Error: {licenses_dir} not found")
        sys.exit(1)

    print(f"Processing licenses from {licenses_dir}...")

    groups: dict[str, list[tuple[str, str]]] = {}

    for file_path in licenses_dir.glob("*.txt"):
        content = file_path.read_text(encoding="utf-8")
        ltype = get_license_type(content)
        lib_name = get_library_name(file_path)

        if ltype not in groups:
            groups[ltype] = []
        groups[ltype].append((lib_name, content))

    count = sum(len(v) for v in groups.values())
    print(f"  Found {count} licenses in {len(groups)} categories.")

    markdown_content = generate_markdown(groups)
    output_file.write_text(markdown_content, encoding="utf-8")

    print(f"Done! Generated {output_file}")


if __name__ == "__main__":
    main()
