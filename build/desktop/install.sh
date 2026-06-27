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

# MyTraL Desktop Application Installer
#
# This script installs the MyTraL desktop executable to the system

set -e

# colors
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
RED='\033[0;31m'
NC='\033[0m'

echo -e "${GREEN}MyTraL Desktop Installer${NC}"
echo "================================"

# get script directory and project root
SCRIPT_DIR="$( cd "$( dirname "${BASH_SOURCE[0]}" )" && pwd )"
PROJECT_ROOT="$( cd "$SCRIPT_DIR/../.." && pwd )"

# get MyTraL version
MYTRAL_VERSION=$(cd "$PROJECT_ROOT" && python3 -c "import sys; sys.path.insert(0, 'mytral'); import version; print(version.__version__)" 2>/dev/null || echo "dev")

# check if versioned executable exists, fallback to symlink
EXECUTABLE_VERSIONED="$PROJECT_ROOT/distro/desktop/mytral-${MYTRAL_VERSION}"
EXECUTABLE_SYMLINK="$PROJECT_ROOT/distro/desktop/mytral"

if [ -f "$EXECUTABLE_VERSIONED" ]; then
    EXECUTABLE="$EXECUTABLE_VERSIONED"
    echo "Found versioned executable: mytral-${MYTRAL_VERSION}"
elif [ -f "$EXECUTABLE_SYMLINK" ]; then
    EXECUTABLE="$EXECUTABLE_SYMLINK"
    echo "Found executable: mytral"
else
    echo -e "${RED}Error: Executable not found${NC}"
    echo "Expected: $EXECUTABLE_VERSIONED or $EXECUTABLE_SYMLINK"
    echo "Please build the executable first: make distro-desktop-build"
    exit 1
fi

# determine installation directory
if [ -w "/usr/local/bin" ]; then
    INSTALL_DIR="/usr/local/bin"
else
    INSTALL_DIR="$HOME/.local/bin"
    mkdir -p "$INSTALL_DIR"
fi

echo "Installation directory: $INSTALL_DIR"

# copy executable
echo "Copying executable..."
cp "$EXECUTABLE" "$INSTALL_DIR/mytral"
chmod +x "$INSTALL_DIR/mytral"

# install desktop file (Linux only)
if [ -d "$HOME/.local/share/applications" ]; then
    echo "Installing desktop launcher..."
    cp "$SCRIPT_DIR/mytral.desktop" "$HOME/.local/share/applications/"
    # update Exec path in desktop file
    sed -i "s|Exec=/usr/local/bin/mytral|Exec=$INSTALL_DIR/mytral|" "$HOME/.local/share/applications/mytral.desktop"
fi

echo -e "${GREEN}================================${NC}"
echo -e "${GREEN}Installation complete!${NC}"
echo -e "${GREEN}================================${NC}"
echo ""
echo "MyTraL desktop installed to: $INSTALL_DIR/mytral"
echo ""
echo "To run MyTraL desktop:"
echo "  $INSTALL_DIR/mytral"
echo ""
if [ "$INSTALL_DIR" = "$HOME/.local/bin" ]; then
    echo -e "${YELLOW}Note: Make sure $HOME/.local/bin is in your PATH${NC}"
    echo "Add this to your ~/.bashrc or ~/.zshrc:"
    echo '  export PATH="$HOME/.local/bin:$PATH"'
    echo ""
fi
