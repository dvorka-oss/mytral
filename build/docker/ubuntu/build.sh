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

# Build a MyTraL test image for one specific Ubuntu release.
#
# The image builds the .deb ON that release and installs it (see Dockerfile).
#
# Usage:
#   ./build.sh [release] [repo-root]
#     release    Ubuntu codename (default: trusty)
#     repo-root  MyTraL git checkout (default: repository this script lives in)

set -euo pipefail

RELEASE="${1:-trusty}"

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REPO_ROOT="${2:-$(cd "${SCRIPT_DIR}/../../.." && pwd)}"

#
# Resolve version
#
VERSION=$(cd "${REPO_ROOT}" && uv run python -c "
import sys; sys.path.insert(0, 'mytral')
import version; print(version.__version__)
" 2>/dev/null || echo "unknown")

IMAGE_TAG="mytral-ubuntu-${RELEASE}:${VERSION}"
IMAGE_LATEST="mytral-ubuntu-${RELEASE}:latest"

echo "=== MyTraL Docker Ubuntu (${RELEASE}) image builder ==="
echo "  Release:  ${RELEASE}"
echo "  Version:  ${VERSION}"
echo "  Repo:     ${REPO_ROOT}"
echo "  Image:    ${IMAGE_TAG}"

#
# Build context: clean copy of the working tree (so uncommitted changes are
# included), minus heavy or irrelevant artifacts.
#
BUILD_CTX="/tmp/mytral-docker-ubuntu-${RELEASE}-build"
echo "  Build ctx: ${BUILD_CTX}"

rm -rf "${BUILD_CTX}"
mkdir -p "${BUILD_CTX}"
tar -C "${REPO_ROOT}" \
    --exclude=.git \
    --exclude=.venv --exclude=venv \
    --exclude=distro --exclude=data \
    --exclude=.idea --exclude=.vscode --exclude=.claude \
    --exclude=.ruff_cache --exclude=.pytest_cache \
    --exclude=__pycache__ --exclude='*.pyc' \
    --exclude=vibe --exclude=uv.lock \
    -cf - . | tar -C "${BUILD_CTX}" -xf -

#
# Apply the old-Ubuntu debian/ overlay at the context root so dpkg-buildpackage
# finds ./debian/ there. Shared files (postinst, postrm, copyright, docs) come
# from the canonical packaging; the overlay only replaces what trusty needs.
#
echo ""
echo "--- Preparing debian/ (canonical + old-Ubuntu overlay) ---"
cp -r "${BUILD_CTX}/build/ubuntu/debian" "${BUILD_CTX}/debian"
cp -r "${BUILD_CTX}/build/docker/ubuntu/debian-overlay/." "${BUILD_CTX}/debian/"

#
# Generate a native-format changelog for this local test build
#
CHANGELOG_DATE=$(date "+%a, %d %b %Y %H:%M:%S %z")
cat > "${BUILD_CTX}/debian/changelog" <<EOF
mytral (${VERSION}~${RELEASE}) ${RELEASE}; urgency=low

  * Local Docker test build for Ubuntu ${RELEASE}.

 -- Martin Dvorak (Dvorka) <martin.dvorak@mindforger.com>  ${CHANGELOG_DATE}
EOF

#
# Build Docker image
#
echo ""
echo "--- Building Docker image (build + install the .deb on ${RELEASE}) ---"
docker build \
    --build-arg "UBUNTU_RELEASE=${RELEASE}" \
    --tag "${IMAGE_TAG}" \
    --tag "${IMAGE_LATEST}" \
    --file "${BUILD_CTX}/build/docker/ubuntu/Dockerfile" \
    "${BUILD_CTX}"

rm -rf "${BUILD_CTX}"

echo ""
echo "================================================================================"
echo "  DOCKER IMAGE BUILT"
echo "================================================================================"
echo "  Image:  ${IMAGE_TAG}"
echo "  Also tagged as: ${IMAGE_LATEST}"
echo ""
echo "  To run:  ./build/docker/ubuntu/run.sh ${RELEASE}"
echo "================================================================================"
