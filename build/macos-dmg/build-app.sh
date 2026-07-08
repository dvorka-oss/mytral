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

# Build the MyTraL macOS app bundle (MyTraL.app) using PyInstaller.
#
# Must run on macOS - relies on `sips`/`iconutil` (icon conversion) which are
# only available on macOS, and produces a native arm64 app bundle when run on
# an Apple Silicon Mac (or GitHub's macos-latest runner).

set -e  # exit on error

# colors for output
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
NC='\033[0m' # No Color

echo -e "${GREEN}================================================${NC}"
echo -e "${GREEN}MyTraL macOS App Bundle Build${NC}"
echo -e "${GREEN}================================================${NC}"

if [ "$(uname -s)" != "Darwin" ]; then
    echo -e "${RED}ERROR: this script must run on macOS (found: $(uname -s)).${NC}"
    exit 1
fi

# get script directory and project root
SCRIPT_DIR="$( cd "$( dirname "${BASH_SOURCE[0]}" )" && pwd )"
PROJECT_ROOT="$( cd "$SCRIPT_DIR/../.." && pwd )"
BUILD_DIR="$PROJECT_ROOT/build/macos-dmg"
DIST_DIR="$PROJECT_ROOT/distro/desktop"
LOGO_PNG="$PROJECT_ROOT/media/logo/mytral-logo-transparent-bg-320x320.png"

echo "Project root: $PROJECT_ROOT"
echo "Build dir: $BUILD_DIR"
echo "Dist dir: $DIST_DIR"

# change to project root
cd "$PROJECT_ROOT"

# get MyTraL version
MYTRAL_VERSION=$(uv run python -c "import sys; sys.path.insert(0, 'mytral'); import version; print(version.__version__)" 2>/dev/null || echo "dev")
echo -e "${GREEN}Building MyTraL version: ${MYTRAL_VERSION}${NC}"

# install desktop dependencies via uv dependency group
echo -e "${GREEN}Installing desktop dependencies...${NC}"
uv sync --group desktop

# check if pyinstaller is available (sanity check after sync)
if ! uv run python -c "import PyInstaller" 2>/dev/null; then
    echo -e "${RED}PyInstaller not available after uv sync. Check pyproject.toml desktop group.${NC}"
    exit 1
fi

# generate mytral.icns from the MyTraL logo if it doesn't exist yet
ICNS_FILE="$BUILD_DIR/mytral.icns"
if [ ! -f "$ICNS_FILE" ]; then
    echo -e "${YELLOW}Generating mytral.icns from ${LOGO_PNG}...${NC}"
    ICONSET_DIR=$(mktemp -d)/mytral.iconset
    mkdir -p "$ICONSET_DIR"
    for spec in "16 icon_16x16" "32 icon_16x16@2x" "32 icon_32x32" "64 icon_32x32@2x" \
                "128 icon_128x128" "256 icon_128x128@2x" "256 icon_256x256" \
                "512 icon_256x256@2x" "512 icon_512x512" "1024 icon_512x512@2x"; do
        SIZE=$(echo "$spec" | cut -d' ' -f1)
        OUT_NAME=$(echo "$spec" | cut -d' ' -f2)
        sips -z "$SIZE" "$SIZE" "$LOGO_PNG" --out "$ICONSET_DIR/$OUT_NAME.png" > /dev/null
    done
    iconutil -c icns "$ICONSET_DIR" -o "$ICNS_FILE"
    rm -rf "$(dirname "$ICONSET_DIR")"
    echo -e "Icon: ${GREEN}$ICNS_FILE${NC}"
fi

# create spec file if it doesn't exist
SPEC_FILE="$BUILD_DIR/mytral.spec"
if [ ! -f "$SPEC_FILE" ]; then
    echo -e "${YELLOW}Creating PyInstaller spec file...${NC}"
    "$SCRIPT_DIR/create-spec.sh" "$MYTRAL_VERSION"
fi

# verify spec file exists
if [ ! -f "$SPEC_FILE" ]; then
    echo -e "${RED}ERROR: Spec file was not created at $SPEC_FILE${NC}"
    exit 1
fi

echo "Using spec file: $SPEC_FILE"

# run PyInstaller
echo -e "${GREEN}Running PyInstaller...${NC}"
uv run pyinstaller "$SPEC_FILE" \
    --clean \
    --noconfirm \
    --distpath "$DIST_DIR"

# check if build succeeded
if [ -d "$DIST_DIR/MyTraL.app" ]; then
    echo -e "${GREEN}================================================${NC}"
    echo -e "${GREEN}Build successful!${NC}"
    echo -e "${GREEN}================================================${NC}"
    echo -e "App bundle: ${GREEN}$DIST_DIR/MyTraL.app${NC}"
    du -sh "$DIST_DIR/MyTraL.app" 2>/dev/null || true
else
    echo -e "${RED}================================================${NC}"
    echo -e "${RED}Build failed!${NC}"
    echo -e "${RED}================================================${NC}"
    exit 1
fi
