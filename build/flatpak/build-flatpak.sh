#!/bin/bash
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

# MyTraL Flatpak Package Build Script
#
# Builds the Flatpak app from the manifest and exports a single-file .flatpak
# bundle to distro/flatpak/.
#
# Prerequisites:
#   sudo apt install flatpak flatpak-builder
#   flatpak remote-add --if-not-exists --user flathub \
#       https://flathub.org/repo/flathub.flatpakrepo
#   flatpak install --user flathub \
#       org.freedesktop.Platform//24.08 org.freedesktop.Sdk//24.08
#
# Usage:
#   ./build/flatpak/build-flatpak.sh

set -e  # exit on error

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_ROOT="$(cd "$SCRIPT_DIR/../.." && pwd)"

APP_ID="fitness.mytral.Mytral"
MANIFEST="$PROJECT_ROOT/flatpak/$APP_ID.yaml"
METAINFO="$PROJECT_ROOT/flatpak/$APP_ID.metainfo.xml"
BUILD_DIR="$PROJECT_ROOT/build/flatpak/build-dir"
REPO_DIR="$PROJECT_ROOT/build/flatpak/repo"
OUT_DIR="$PROJECT_ROOT/distro/flatpak"

# read version from the single source of truth
MYTRAL_VERSION=$(grep -oP '(?<=__version__ = ")[^"]+' "$PROJECT_ROOT/mytral/version.py" || echo "dev")
echo "MyTraL version: $MYTRAL_VERSION"

# inject version into the metainfo release entry
sed -i -E "s|<release version=\"[^\"]+\"|<release version=\"$MYTRAL_VERSION\"|" "$METAINFO"

mkdir -p "$OUT_DIR"

echo "Building Flatpak app..."
flatpak-builder --force-clean --repo="$REPO_DIR" "$BUILD_DIR" "$MANIFEST"

echo "Exporting single-file bundle..."
BUNDLE="$OUT_DIR/mytral-$MYTRAL_VERSION.flatpak"
# --runtime-repo embeds where to fetch the freedesktop runtime:
#   * when a user installs this standalone .flatpak and
#     lacks org.freedesktop.Platform//24.08, flatpak offers to pull it from Flathub
#     instead of failing.
#    * user does NOT need Flathub pre-configured
flatpak build-bundle \
    --runtime-repo=https://dl.flathub.org/repo/flathub.flatpakrepo \
    "$REPO_DIR" "$BUNDLE" "$APP_ID"

echo "Flatpak bundle created: distro/flatpak/mytral-$MYTRAL_VERSION.flatpak"
