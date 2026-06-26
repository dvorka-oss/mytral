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

"""Refresh PAD.xml release fields from the single sources of truth.

Updates the release-specific fields of ``PAD.xml`` so the Portable Application
Description always matches the current release:

- ``Program_Version`` from ``mytral/version.py``,
- release date (``Program_Release_Month/Day/Year``) to today,
- ``Program_Change_Info`` and ``Program_Release_Status`` from ``CHANGELOG.md``,
- ``File_Size_*`` from the Windows installer in ``distro/windows/`` when present.

The script is cross-platform: it uses only the standard library and never shells
out, so it runs the same on Linux and Windows.  The file is edited in place with
targeted text replacements to preserve its hand-written formatting.
"""

import datetime
import pathlib
import re
import sys
from xml.sax import saxutils

ROOT = pathlib.Path(__file__).resolve().parent.parent
PAD_FILE = ROOT / "PAD.xml"
VERSION_FILE = ROOT / "mytral" / "version.py"
CHANGELOG_FILE = ROOT / "CHANGELOG.md"

# maps the changelog release marker (**major** / **minor** / **patch**) to a
# valid PAD Program_Release_Status value
RELEASE_STATUS = {
    "major": "Major Update",
    "minor": "Minor Update",
    "patch": "Minor Bug Fixes",
}

# PAD Program_Change_Info should stay concise; cap the generated summary
MAX_CHANGE_INFO_CHARS = 2000


def read_version() -> str:
    """Return the MyTraL version string from ``mytral/version.py``."""
    text = VERSION_FILE.read_text(encoding="utf-8")
    match = re.search(r'__version__\s*=\s*"([^"]+)"', text)
    if not match:
        sys.exit(f"ERROR: could not read __version__ from {VERSION_FILE}")
    return match.group(1)


def strip_markdown(line: str) -> str:
    """Reduce a Markdown bullet to plain, single-line text."""
    # [text](url) -> text
    line = re.sub(r"\[([^\]]+)\]\([^)]+\)", r"\1", line)
    line = line.replace("`", "").replace("**", "").replace("*", "")
    return re.sub(r"\s+", " ", line).strip()


def changelog_entry(version: str) -> tuple[str, str]:
    """Return (change summary, release status) for ``version`` from the changelog.

    The changelog section for the version is the block between its
    ``## [<version>]`` heading and the next ``## `` heading.  Bullet lines are
    flattened into a single ``"; "``-joined summary, and the ``**major/minor/
    patch**`` marker selects the PAD release status.
    """
    lines = CHANGELOG_FILE.read_text(encoding="utf-8").splitlines()

    start = next(
        (
            i
            for i, line in enumerate(lines)
            if line.startswith("## ") and f"[{version}]" in line
        ),
        None,
    )
    if start is None:
        sys.exit(f"ERROR: no changelog section found for version {version}")

    body = []
    for line in lines[start + 1 :]:
        if line.startswith("## "):
            break
        body.append(line)

    marker = re.search(r"\*\*(major|minor|patch)\*\*", "\n".join(body), re.IGNORECASE)
    release_type = marker.group(1).lower() if marker else version_release_type(version)
    status = RELEASE_STATUS.get(release_type, "Minor Update")

    bullets = collect_bullets(body)
    summary = "; ".join(bullets) or f"MyTraL {version} release."
    if len(summary) > MAX_CHANGE_INFO_CHARS:
        summary = summary[: MAX_CHANGE_INFO_CHARS - 1].rstrip() + "…"
    return summary, status


def collect_bullets(body: list[str]) -> list[str]:
    """Flatten a Markdown bullet list, joining wrapped continuation lines.

    A bullet starts with ``- `` and may wrap across following indented lines that
    are neither blank, a new bullet, nor a ``###`` sub-heading.
    """
    bullets: list[str] = []
    current: list[str] = []

    def flush() -> None:
        if current:
            bullets.append(strip_markdown(" ".join(current)))
            current.clear()

    for line in body:
        stripped = line.strip()
        if stripped.startswith("- "):
            flush()
            current.append(stripped[2:])
        elif current and stripped and not stripped.startswith("#"):
            current.append(stripped)
        else:
            flush()
    flush()
    return bullets


def version_release_type(version: str) -> str:
    """Infer major/minor/patch from a semantic version as a changelog fallback."""
    parts = (version.split(".") + ["0", "0", "0"])[:3]
    major, minor, patch = (int(p) if p.isdigit() else 0 for p in parts)
    if patch:
        return "patch"
    if minor:
        return "minor"
    return "major" if major else "minor"


def installer_size_bytes(version: str) -> int | None:
    """Return the Windows installer size in bytes, or None when not built.

    Looks for ``distro/windows/mytral-<version>-setup.exe`` (the Inno Setup
    output).  Works regardless of the host OS - the file is simply checked for
    existence so the size can also be refreshed on Linux if the artifact is
    present.
    """
    installer = ROOT / "distro" / "windows" / f"mytral-{version}-setup.exe"
    if not installer.is_file():
        return None
    return installer.stat().st_size


def set_tag(xml: str, tag: str, value: str) -> str:
    """Replace the text content of ``<tag>`` (open/close or self-closing form)."""
    escaped = saxutils.escape(value)
    paired = re.compile(rf"<{tag}>.*?</{tag}>", re.DOTALL)
    if paired.search(xml):
        return paired.sub(lambda _: f"<{tag}>{escaped}</{tag}>", xml, count=1)
    selfclosing = re.compile(rf"<{tag}\s*/>")
    if selfclosing.search(xml):
        return selfclosing.sub(lambda _: f"<{tag}>{escaped}</{tag}>", xml, count=1)
    sys.exit(f"ERROR: tag <{tag}> not found in {PAD_FILE}")


def main() -> None:
    version = read_version()
    today = datetime.date.today()
    change_info, release_status = changelog_entry(version)

    xml = PAD_FILE.read_text(encoding="utf-8")
    xml = set_tag(xml, "Program_Version", version)
    xml = set_tag(xml, "Program_Release_Month", f"{today.month:02d}")
    xml = set_tag(xml, "Program_Release_Day", f"{today.day:02d}")
    xml = set_tag(xml, "Program_Release_Year", f"{today.year}")
    xml = set_tag(xml, "Program_Release_Status", release_status)
    xml = set_tag(xml, "Program_Change_Info", change_info)

    size = installer_size_bytes(version)
    if size is not None:
        xml = set_tag(xml, "File_Size_Bytes", str(size))
        xml = set_tag(xml, "File_Size_K", f"{size / 1024:.2f}")
        xml = set_tag(xml, "File_Size_MB", f"{size / 1024 / 1024:.2f}")

    PAD_FILE.write_text(xml, encoding="utf-8")

    print(f"PAD.xml refreshed for MyTraL {version} ({today.isoformat()})")
    print(f"  release status: {release_status}")
    print(f"  change info:    {change_info[:80]}...")
    if size is not None:
        print(f"  installer size: {size} bytes ({size / 1024 / 1024:.2f} MB)")
    else:
        print("  installer size: unchanged (no Windows installer in distro/windows/)")
    print("DONE")


if __name__ == "__main__":
    main()
