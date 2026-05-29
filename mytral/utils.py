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
import hashlib
import os
import re

# environment variable values
ENV_VALUE_TRUE = "true"
ENV_VALUE_FALSE = "false"


def getenv_bool(name: str, default: bool = False) -> bool:
    """Read a boolean value from an environment variable.

    Treats ``"1"``, ``"true"``, and ``"yes"`` (case-insensitive) as ``True``,
    everything else (including an unset variable) as ``False``.

    ``bool(os.getenv(...))`` is intentionally avoided because it evaluates any
    non-empty string — including ``"false"`` and ``"0"`` — as ``True``.

    Parameters
    ----------
    name : str
        Environment variable name.
    default : bool
        Value to return when the variable is not set (default ``False``).

    Returns
    -------
    bool
        Parsed boolean value.

    """
    raw = os.getenv(name)
    if raw is None:
        return default
    return raw.lower() in {"1", ENV_VALUE_TRUE, ENV_VALUE_FALSE}


def is_uuid(s: str) -> bool:
    """Check whether the given string is a UUID.

    Parameters
    ----------
    s : str
        String to check.

    Returns
    -------
    bool :
        True if the string is a UUID, False otherwise.

    """
    uuid4hex = re.compile(
        "^[a-f0-9]{8}-?[a-f0-9]{4}-?4[a-f0-9]{3}-?[89ab][a-f0-9]{3}-?[a-f0-9]{12}",
        re.I,
    )
    match = uuid4hex.match(s)
    return bool(match)


def string_ellipsis(string: str, limit: int = 10, fragment: int = 4) -> str:
    if len(string) > limit:
        return f"{string[:fragment]}...{string[-fragment:]}"
    return string


def tag_to_color(tag: str) -> str:
    """Generate a consistent color for a tag using hash-based selection.

    Parameters
    ----------
    tag : str
        tag text to colorize

    Returns
    -------
    str
        Tabler CSS color name (e.g., 'blue', 'green', etc.)

    """
    colors = [
        "blue",
        "azure",
        "indigo",
        "purple",
        "pink",
        "red",
        "orange",
        "yellow",
        "lime",
        "green",
        "teal",
        "cyan",
    ]

    # use stable hash to ensure consistent colors across server restarts
    normalized_tag = tag.lower().strip()
    # md5 used only for color bucketing, not for security purposes
    tag_hash = int(
        hashlib.md5(normalized_tag.encode("utf-8"), usedforsecurity=False).hexdigest(),
        16,
    )
    color_index = tag_hash % len(colors)

    return colors[color_index]
