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

# Run the MyTraL test container for one specific Ubuntu release.
#
#   - host port 8888 mapped to container 5000
#   - data directory on the host for persistence across restarts
#
# Usage:
#   ./run.sh [release] [version]
#     release  Ubuntu codename (default: trusty)
#     version  image version tag (default: resolved from the source tree)

set -euo pipefail

RELEASE="${1:-trusty}"

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REPO_ROOT="$(cd "${SCRIPT_DIR}/../../.." && pwd)"

VERSION="${2:-$(cd "${REPO_ROOT}" && uv run python -c "
import sys; sys.path.insert(0, 'mytral')
import version; print(version.__version__)
" 2>/dev/null || echo "latest")}"

IMAGE="mytral-ubuntu-${RELEASE}:${VERSION}"
CONTAINER_NAME="mytral-ubuntu-${RELEASE}"

#
# Data directory on the host filesystem
#
HOST_DATA_DIR="${MYTRAL_DOCKER_DATA_DIR:-${HOME}/.local/share/mytral-docker-ubuntu-${RELEASE}}"
mkdir -p "${HOST_DATA_DIR}"

#
# Keys — for production set these in the environment before running
#
ENC_KEY="${MYTRAL_ENCRYPTION_KEY:-docker-dev-key-change-me}"

#
# Replace any existing container with the same name
#
if docker ps -a --format '{{.Names}}' | grep -q "^${CONTAINER_NAME}$"; then
    echo "--- Stopping and removing existing container '${CONTAINER_NAME}' ---"
    docker stop "${CONTAINER_NAME}" 2>/dev/null || true
    docker rm "${CONTAINER_NAME}" 2>/dev/null || true
fi

echo "=== MyTraL Docker Ubuntu (${RELEASE}) runner ==="
echo "  Image:       ${IMAGE}"
echo "  Container:   ${CONTAINER_NAME}"
echo "  Host port:   8888 -> container 5000"
echo "  Host data:   ${HOST_DATA_DIR} -> container /mytral"
echo ""

docker run \
    --name "${CONTAINER_NAME}" \
    --publish 8888:5000 \
    --volume "${HOST_DATA_DIR}:/mytral" \
    --env MYTRAL_ENCRYPTION_KEY="${ENC_KEY}" \
    --env MYTRAL_SIGNING_KEY="${MYTRAL_SIGNING_KEY:-docker-signing-key-change-me}" \
    --restart unless-stopped \
    --detach \
    "${IMAGE}"

echo ""
echo "================================================================================"
echo "  MyTraL IS RUNNING ON UBUNTU ${RELEASE}"
echo "================================================================================"
echo "  URL:       http://localhost:8888"
echo "  Data dir:  ${HOST_DATA_DIR}"
echo ""
echo "  To stop:   docker stop ${CONTAINER_NAME}"
echo "  To logs:   docker logs -f ${CONTAINER_NAME}"
echo "  To remove: docker rm ${CONTAINER_NAME}"
echo "================================================================================"
