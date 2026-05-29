#!/bin/bash
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
