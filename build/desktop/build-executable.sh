#!/bin/bash
# MyTraL: my training log
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

# Build MyTraL desktop executable using PyInstaller
#
# This script builds a single-file executable for the desktop version of MyTraL.
# It bundles Python, Flask, Waitress, FlaskWebGUI, and all dependencies into
# a standalone executable.

set -e  # exit on error

# colors for output
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
NC='\033[0m' # No Color

echo -e "${GREEN}================================================${NC}"
echo -e "${GREEN}MyTraL Desktop Executable Build${NC}"
echo -e "${GREEN}================================================${NC}"

# get script directory and project root
SCRIPT_DIR="$( cd "$( dirname "${BASH_SOURCE[0]}" )" && pwd )"
PROJECT_ROOT="$( cd "$SCRIPT_DIR/../.." && pwd )"
BUILD_DIR="$PROJECT_ROOT/build/desktop"
DIST_DIR="$PROJECT_ROOT/distro/desktop"

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
EXECUTABLE_NAME="mytral-${MYTRAL_VERSION}"
if [ -f "$DIST_DIR/$EXECUTABLE_NAME" ] || [ -f "$DIST_DIR/${EXECUTABLE_NAME}.exe" ]; then
    echo -e "${GREEN}================================================${NC}"
    echo -e "${GREEN}Build successful!${NC}"
    echo -e "${GREEN}================================================${NC}"
    echo -e "Executable: ${GREEN}$DIST_DIR/$EXECUTABLE_NAME${NC}"
    ls -lh "$DIST_DIR/$EXECUTABLE_NAME"* 2>/dev/null || true

    # create symlink without version for convenience
    ln -sf "$EXECUTABLE_NAME" "$DIST_DIR/mytral"
    echo -e "Symlink: ${GREEN}$DIST_DIR/mytral -> $EXECUTABLE_NAME${NC}"

    # generate .desktop file from template with version and exec path substituted
    DESKTOP_TEMPLATE="$BUILD_DIR/mytral.desktop.in"
    DESKTOP_OUT="$DIST_DIR/mytral.desktop"
    EXEC_PATH="$DIST_DIR/mytral"
    sed -e "s|@@MYTRAL_VERSION@@|${MYTRAL_VERSION}|g" \
        -e "s|@@EXEC_PATH@@|${EXEC_PATH}|g" \
        "$DESKTOP_TEMPLATE" > "$DESKTOP_OUT"
    echo -e "Desktop file: ${GREEN}$DESKTOP_OUT${NC}"
    echo -e ""
    echo -e "To install for the current user, run:"
    echo -e "  cp $EXEC_PATH ~/.local/bin/mytral"
    echo -e "  sed 's|${EXEC_PATH}|\$HOME/.local/bin/mytral|' $DESKTOP_OUT \\"
    echo -e "      > ~/.local/share/applications/mytral.desktop"
else
    echo -e "${RED}================================================${NC}"
    echo -e "${RED}Build failed!${NC}"
    echo -e "${RED}================================================${NC}"
    exit 1
fi
