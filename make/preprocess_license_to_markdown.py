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
Preprocess the project LICENSE file to a Markdown documentation page.

This script:
1. Reads ./LICENSE (GNU Affero General Public License v3.0 plain text)
2. Generates ./docs/LICENSE.md with:
   - Summary of AGPL-3.0 permissions, conditions, and limitations
   - Full license text in a code block
"""

import sys
from pathlib import Path


def generate_markdown(license_text: str) -> str:
    """
    Generate Markdown content for the project license.

    Parameters
    ----------
    license_text : str
        full text of the GNU AGPL-3.0 license

    Returns
    -------
    str
        Markdown content
    """
    agpl_permissions = [
        "Commercial use",
        "Distribution",
        "Modification",
        "Patent use",
        "Private use",
    ]
    agpl_conditions = [
        "Disclose source",
        "License and copyright notice",
        "Network use is distribution",
        "Same license (AGPL-3.0)",
        "State changes",
    ]
    agpl_limitations = [
        "Liability",
        "Warranty",
    ]

    lines = []
    lines.append("# License\n")
    lines.append("MyTraL project is licensed under the GNU AGPL-3.0 license.\n")
    lines.append("## GNU AGPL-3.0\n")
    lines.append(
        "GNU Affero General Public License v3.0 - a strong copyleft license. "
        "Modifications to network-served software must be released under "
        "the same license.\n"
    )

    lines.append("### Permissions\n")
    for item in agpl_permissions:
        lines.append(f"* {item}")
    lines.append("")

    lines.append("### Conditions\n")
    for item in agpl_conditions:
        lines.append(f"* {item}")
    lines.append("")

    lines.append("### Limitations\n")
    for item in agpl_limitations:
        lines.append(f"* {item}")
    lines.append("")

    lines.append("### Official Text\n")
    lines.append(
        "* [Official AGPL-3.0 Text](https://www.gnu.org/licenses/agpl-3.0.html)\n"
    )

    lines.append("## Full License Text\n")
    lines.append("```")
    lines.append(license_text.strip())
    lines.append("```\n")

    return "\n".join(lines)


def main() -> None:
    """Main entry point for the script."""
    repo_root = Path(__file__).parent.parent
    license_file = repo_root / "LICENSE"
    output_file = repo_root / "docs" / "LICENSE.md"

    if not license_file.exists():
        print(f"Error: {license_file} not found")
        sys.exit(1)

    print(f"Processing project license from {license_file}...")

    license_text = license_file.read_text(encoding="utf-8")
    markdown_content = generate_markdown(license_text)
    output_file.write_text(markdown_content, encoding="utf-8")

    print(f"Done! Generated {output_file}")


if __name__ == "__main__":
    main()
