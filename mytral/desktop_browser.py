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
"""Desktop browser mode selection - side-effect-free so it is safe to unit-test."""

import os

# value of MYTRAL_DESKTOP_BROWSER that selects the portal browser mode (Snap strict /
# Flatpak sandboxes, where host browsers cannot be launched as a native window)
DESKTOP_BROWSER_PORTAL = "portal"


def use_portal_browser() -> bool:
    """Whether to open the UI via the default browser instead of a native window.

    Returns True when ``MYTRAL_DESKTOP_BROWSER`` is ``portal`` - the mode used by
    sandboxed packaging (Snap strict, Flatpak) that cannot exec a host browser. The UI
    then opens in the user's default browser via the desktop portal / ``xdg-open``.
    """
    return (
        os.environ.get("MYTRAL_DESKTOP_BROWSER", "").strip().lower()
        == DESKTOP_BROWSER_PORTAL
    )
