#!/bin/bash
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

# Transform a BUILD-COPY snapcraft.yaml from the strict (default, committed) manifest
# into the classic variant for the downloadable, sideloaded GitHub Release snap.
#
# This is the single authoritative place for the strict -> classic edits (DRY). It must
# only ever be pointed at a build copy, never the committed snap/snapcraft.yaml.
#
# Usage: apply-classic.sh <path-to-build-copy-snapcraft.yaml>

set -e

YAML="$1"
if [ -z "$YAML" ] || [ ! -f "$YAML" ]; then
    echo "ERROR: apply-classic.sh needs a path to a snapcraft.yaml build copy" >&2
    exit 1
fi

# 1. confinement: strict -> classic (sideloadable, full host access)
sed -i 's|^confinement: strict$|confinement: classic|' "$YAML"

# 2. command: classic needs the ld.so wrapper instead of the strict launcher
sed -i 's|^    command: bin/mytral-strict$|    command: bin/mytral-wrapper|' "$YAML"

# 3. remove the strict-only env block (MYTRAL_DATA_DIR + MYTRAL_DESKTOP_BROWSER and their
#    comments); classic uses the XDG default ~/.local/share/mytral and the native window
sed -i '/# strict-only wiring/,/MYTRAL_DESKTOP_BROWSER:/d' "$YAML"

# 4. remove the apps.mytral plugs block (classic ignores interfaces); delete the 'plugs:'
#    line and the contiguous 6-space-indented list items that follow it
awk '
    /^    plugs:[[:space:]]*$/ { in_plugs = 1; next }
    in_plugs && /^      - / { next }
    in_plugs { in_plugs = 0 }
    { print }
' "$YAML" > "$YAML.tmp" && mv -f "$YAML.tmp" "$YAML"

echo "Applied classic-confinement transform to: $YAML"
