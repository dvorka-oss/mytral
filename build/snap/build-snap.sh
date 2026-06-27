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

# MyTraL Snap Package Build Script
#
# Copies the project to a temp build directory, injects snap/ config, and runs snapcraft.
#
# Prerequisites:
#   sudo snap install snapcraft --classic
#   sudo snap install lxd
#   sudo lxd init --auto
#   sudo usermod -aG lxd $USER
#
# Usage:
#   ./build/snap/build-snap.sh              # LXD build (default, isolated)
#   ./build/snap/build-snap.sh --destructive-mode  # host build (requires sudo for build packages)

set -e  # exit on error

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_ROOT="$(cd "$SCRIPT_DIR/../.." && pwd)"
BUILD_DIR="$PROJECT_ROOT/build/snap"
PROJECT_BUILD_DIR="$BUILD_DIR/project"

# read version from the single source of truth (grep avoids importing the full package)
MYTRAL_VERSION=$(grep -oP '(?<=__version__ = ")[^"]+' "$PROJECT_ROOT/mytral/version.py" || echo "dev")

echo "MyTraL version: $MYTRAL_VERSION"

# inject version into snapcraft.yaml before copying to build dir
SNAPCRAFT_YAML="$PROJECT_ROOT/snap/snapcraft.yaml"
sed -i "s/^version: .*/version: '$MYTRAL_VERSION'/" "$SNAPCRAFT_YAML"

# clean previous temp build
echo "Cleaning previous build..."
rm -rf "$PROJECT_BUILD_DIR"
rm -rf "$PROJECT_ROOT/parts" "$PROJECT_ROOT/prime" "$PROJECT_ROOT/stage" 2>/dev/null || true

# create build directory
echo "Creating build directory at $PROJECT_BUILD_DIR..."
mkdir -p "$PROJECT_BUILD_DIR"

# copy project source, excluding artifacts and unwanted directories
echo "Copying project files..."
rsync -a --exclude='.git' \
         --exclude='.venv' \
         --exclude='__pycache__' \
         --exclude='.pytest_cache' \
         --exclude='.ruff_cache' \
         --exclude='.idea' \
         --exclude='build/snap/project' \
         --exclude='*.snap' \
         "$PROJECT_ROOT/" "$PROJECT_BUILD_DIR/"

# build
echo "Building Snap package..."
cd "$PROJECT_BUILD_DIR"
mkdir -p "$PROJECT_ROOT/distro/snap"

# clean stale LXD container state to avoid hard-link errors on rebuild
snapcraft clean 2>/dev/null || true

# snapcraft 9: 'snapcraft pack' runs the full lifecycle (pull→build→stage→prime→pack)
snapcraft pack "$@"

# move snap to output location
SNAP_FILE=$(ls mytral_*.snap 2>/dev/null | head -1)
if [ -n "$SNAP_FILE" ]; then
    mv -f "$SNAP_FILE" "$PROJECT_ROOT/distro/snap/${SNAP_FILE}"
    echo "Snap package created: distro/snap/${SNAP_FILE}"
else
    echo "ERROR: No .snap file found after build"
    exit 1
fi
