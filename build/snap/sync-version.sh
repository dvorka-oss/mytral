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

# Syncs snap/snapcraft.yaml's version field to mytral/version.py (single source
# of truth). Run before any build that reads snap/snapcraft.yaml directly
# (e.g. the GH Actions snapcore/action-build step, which builds straight from
# the checked-out manifest rather than via build-snap.sh's build copy).

set -e

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_ROOT="$(cd "$SCRIPT_DIR/../.." && pwd)"

# read version from the single source of truth (grep avoids importing the full package)
MYTRAL_VERSION=$(grep -oP '(?<=__version__ = ")[^"]+' "$PROJECT_ROOT/mytral/version.py" || echo "dev")

echo "MyTraL version: $MYTRAL_VERSION"
sed -i "s/^version: .*/version: '$MYTRAL_VERSION'/" "$PROJECT_ROOT/snap/snapcraft.yaml"
echo "DONE"
