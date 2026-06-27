#!/usr/bin/env bash
#
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

# MyTraL Docker Debian image builder.
#
# Creates a Docker image with MyTraL running on Debian (bookworm-slim).
# The image contains only production dependencies — no dev, test, or ML tooling.
#
# Usage:
#   ./build.sh              # build from the repo root
#   ./build.sh /path/to/repo  # build from a specific repo path

set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REPO_ROOT="${1:-$(cd "${SCRIPT_DIR}/../../.." && pwd)}"

#
# Resolve version
#
VERSION=$(cd "${REPO_ROOT}" && uv run python -c "
import sys; sys.path.insert(0, 'mytral')
import version; print(version.__version__)
" 2>/dev/null || echo "unknown")

IMAGE_TAG="mytral-debian:${VERSION}"
IMAGE_LATEST="mytral-debian:latest"

echo "=== MyTraL Docker Debian image builder ==="
echo "  Version:  ${VERSION}"
echo "  Repo:     ${REPO_ROOT}"
echo "  Image:    ${IMAGE_TAG}"

#
# Build context setup (clean copy of source, no dev artifacts)
#
BUILD_CTX="/tmp/mytral-docker-debian-build"
echo "  Build ctx: ${BUILD_CTX}"

# Clean previous build context
rm -rf "${BUILD_CTX}"
mkdir -p "${BUILD_CTX}"

#
# Copy project source to build context
#
echo ""
echo "--- Copying project source ---"

# Directories
cp -r "${REPO_ROOT}/mytral"   "${BUILD_CTX}/"
cp -r "${REPO_ROOT}/tests"    "${BUILD_CTX}/"
cp -r "${REPO_ROOT}/build"    "${BUILD_CTX}/"
cp -r "${REPO_ROOT}/make"     "${BUILD_CTX}/"
cp -r "${REPO_ROOT}/docs"     "${BUILD_CTX}/"
cp -r "${REPO_ROOT}/licenses" "${BUILD_CTX}/"
cp -r "${REPO_ROOT}/media"    "${BUILD_CTX}/"
cp -r "${REPO_ROOT}/webs"     "${BUILD_CTX}/"

# Top-level files
cp "${REPO_ROOT}/pyproject.toml"  "${BUILD_CTX}/"
cp "${REPO_ROOT}/Makefile"        "${BUILD_CTX}/"
cp "${REPO_ROOT}/README.md"       "${BUILD_CTX}/"
cp "${REPO_ROOT}/LICENSE"         "${BUILD_CTX}/"
cp "${REPO_ROOT}/CHANGELOG.md"    "${BUILD_CTX}/"
cp "${REPO_ROOT}/CREDITS.md"      "${BUILD_CTX}/"
cp "${REPO_ROOT}/CONTRIBUTE.md"   "${BUILD_CTX}/"
cp "${REPO_ROOT}/KNOWN_ISSUES.md" "${BUILD_CTX}/"
cp "${REPO_ROOT}/.gitignore"      "${BUILD_CTX}/"

#
# Prune development artifacts from build context
#
echo ""
echo "--- Pruning development artifacts ---"

cd "${BUILD_CTX}"

# Python cache
find . -type d -name "__pycache__" -exec rm -rf {} + 2>/dev/null || true
find . -type d -name "*.egg-info" -exec rm -rf {} + 2>/dev/null || true

# Lint/test caches
rm -rf .ruff_cache .pytest_cache

# IDE directories
rm -rf .idea .vscode .claude

# Virtual environment
rm -rf .venv venv

# uv lock file (fresh resolve in container)
rm -f uv.lock

# Vibe coding directory
rm -rf vibe

# Generated HTML documentation (source Markdown is in docs/)
rm -rf mytral/static/documentation

# Stale build artifacts
rm -rf build/tarball/build
rm -rf build/docker/debian/build

# Desktop build spec files
rm -f build/desktop/*.spec 2>/dev/null || true

# macOS metadata
find . -name ".DS_Store" -delete 2>/dev/null || true

# Editor backup files
find . -type f \( -name "*~" -o -name "*.swp" -o -name "*.swo" \) -delete 2>/dev/null || true

# Empty directories
find . -type d -empty -delete 2>/dev/null || true

#
# Build Docker image
#
echo ""
echo "--- Building Docker image ---"
cd "${SCRIPT_DIR}"
docker build \
    --tag "${IMAGE_TAG}" \
    --tag "${IMAGE_LATEST}" \
    --file Dockerfile \
    "${BUILD_CTX}"

#
# Clean up build context
#
rm -rf "${BUILD_CTX}"

#
# Report
#
echo ""
echo "================================================================================"
echo "  DOCKER IMAGE BUILT"
echo "================================================================================"
echo "  Image:  ${IMAGE_TAG}"
echo "  Also tagged as: ${IMAGE_LATEST}"
echo ""
echo "  To run:   make distro-docker-debian-run"
echo "  To list:  docker images | grep mytral-debian"
echo "================================================================================"
