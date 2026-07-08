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

# Clean macOS app bundle and .dmg build artifacts

set -e

echo "Cleaning macOS .dmg build artifacts..."

# get script directory and project root
SCRIPT_DIR="$( cd "$( dirname "${BASH_SOURCE[0]}" )" && pwd )"
PROJECT_ROOT="$( cd "$SCRIPT_DIR/../.." && pwd )"

cd "$PROJECT_ROOT"

# remove PyInstaller build artifacts
rm -rvf build/macos-dmg/__pycache__
rm -f build/macos-dmg/mytral.spec
rm -f build/macos-dmg/mytral.icns

# remove the app bundle and the packaged .dmg
rm -rvf distro/desktop/MyTraL.app
rm -rvf distro/macos-dmg

echo "Clean complete!"
