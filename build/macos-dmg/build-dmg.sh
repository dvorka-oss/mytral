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

# Package the MyTraL.app bundle into a distributable .dmg using hdiutil.
#
# Must run on macOS - relies on `hdiutil` which is only available on macOS.
# Prerequisite: build/macos-dmg/build-app.sh (or `make distro-desktop-build-macos`)
# must have already produced distro/desktop/MyTraL.app.

set -e  # exit on error

RED='\033[0;31m'
GREEN='\033[0;32m'
NC='\033[0m' # No Color

if [ "$(uname -s)" != "Darwin" ]; then
    echo -e "${RED}ERROR: this script must run on macOS (found: $(uname -s)).${NC}"
    exit 1
fi

# get script directory and project root
SCRIPT_DIR="$( cd "$( dirname "${BASH_SOURCE[0]}" )" && pwd )"
PROJECT_ROOT="$( cd "$SCRIPT_DIR/../.." && pwd )"
APP_BUNDLE="$PROJECT_ROOT/distro/desktop/MyTraL.app"
DIST_DIR="$PROJECT_ROOT/distro/macos-dmg"

cd "$PROJECT_ROOT"

# get MyTraL version
MYTRAL_VERSION=$(uv run python -c "import sys; sys.path.insert(0, 'mytral'); import version; print(version.__version__)" 2>/dev/null || echo "dev")
echo -e "${GREEN}Packaging MyTraL version: ${MYTRAL_VERSION}${NC}"

# verify the app bundle was built first
if [ ! -d "$APP_BUNDLE" ]; then
    echo -e "${RED}ERROR: App bundle not found: $APP_BUNDLE${NC}"
    echo -e "${RED}Run 'make distro-desktop-build-macos' first.${NC}"
    exit 1
fi

mkdir -p "$DIST_DIR"
DMG_FILE="$DIST_DIR/mytral-${MYTRAL_VERSION}.dmg"

# stage the app bundle alongside an Applications symlink for drag-to-install
STAGING_DIR=$(mktemp -d)/mytral-dmg
mkdir -p "$STAGING_DIR"
cp -R "$APP_BUNDLE" "$STAGING_DIR/"
ln -s /Applications "$STAGING_DIR/Applications"

echo "Creating disk image..."
rm -f "$DMG_FILE"
hdiutil create -volname "MyTraL" -srcfolder "$STAGING_DIR" -ov -format UDZO "$DMG_FILE"

rm -rf "$(dirname "$STAGING_DIR")"

if [ -f "$DMG_FILE" ]; then
    echo -e "${GREEN}================================================${NC}"
    echo -e "${GREEN}Build successful!${NC}"
    echo -e "${GREEN}================================================${NC}"
    echo -e "DMG: ${GREEN}$DMG_FILE${NC}"
    ls -lh "$DMG_FILE"
else
    echo -e "${RED}================================================${NC}"
    echo -e "${RED}Build failed!${NC}"
    echo -e "${RED}================================================${NC}"
    exit 1
fi
