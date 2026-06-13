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

"""Shared XML helpers for GPX and TCX extractors."""


def _extract_namespace(root) -> str:
    """Extract the XML namespace prefix from a root element tag.

    Returns the namespace URI including braces (e.g.
    ``"{http://www.topografix.com/GPX/1/1}"``) or an empty string when the
    tag has no namespace.
    """
    if "}" in root.tag:
        return root.tag.split("}")[0] + "}"
    return ""
