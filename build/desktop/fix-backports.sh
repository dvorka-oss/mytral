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

# Quick fix for backports import error

set -e

cd ${HOME}/p/mytral/git/my-training-log

echo "=== MyTraL Desktop - Backports Fix ==="
echo ""

# Clean old build
echo "1. Cleaning old build..."
make distro-desktop-clean 2>/dev/null || true
rm -f build/desktop/mytral.spec

# Install missing dependencies
echo ""
echo "2. Installing dependencies..."
uv pip install backports.functools-lru-cache
uv pip install importlib-metadata importlib-resources

# Rebuild
echo ""
echo "3. Rebuilding executable..."
make distro-desktop-build

echo ""
echo "=== Build Complete ==="
echo ""
echo "Test with: ./distro/desktop/mytral"
