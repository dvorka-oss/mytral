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

# MyTraL Docker Fedora container runner.
#
# Starts a MyTraL container with:
#   - port 8888 on the host mapped to 5000 in the container
#   - data directory on the host filesystem for persistence across restarts
#
# Usage:
#   ./run.sh              # run with defaults
#   ./run.sh 1.51.0dev    # run a specific version tag

set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REPO_ROOT="$(cd "${SCRIPT_DIR}/../../.." && pwd)"

#
# Resolve version
#
VERSION="${1:-$(cd "${REPO_ROOT}" && uv run python -c "
import sys; sys.path.insert(0, 'mytral')
import version; print(version.__version__)
" 2>/dev/null || echo "latest")}"

IMAGE="mytral-fedora:${VERSION}"
CONTAINER_NAME="mytral-fedora"

#
# Data directory on the host filesystem
#
# Default: ~/.local/share/mytral-docker-fedora (follows XDG_DATA_HOME convention)
HOST_DATA_DIR="${MYTRAL_DOCKER_FEDORA_DATA_DIR:-${HOME}/.local/share/mytral-docker-fedora}"
mkdir -p "${HOST_DATA_DIR}"

#
# Encryption key
#
# For production, set MYTRAL_ENCRYPTION_KEY in the environment before running.
# For development, we pass a default key so the container starts without error.
ENC_KEY="${MYTRAL_ENCRYPTION_KEY:-docker-dev-key-change-me}"

#
# Stop and remove any existing container with the same name
#
if docker ps -a --format '{{.Names}}' | grep -q "^${CONTAINER_NAME}$"; then
    echo "--- Stopping and removing existing container '${CONTAINER_NAME}' ---"
    docker stop "${CONTAINER_NAME}" 2>/dev/null || true
    docker rm "${CONTAINER_NAME}" 2>/dev/null || true
fi

#
# Run
#
echo "=== MyTraL Docker Fedora runner ==="
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

#
# Report
#
echo ""
echo "================================================================================"
echo "  MyTraL IS RUNNING"
echo "================================================================================"
echo "  URL:       http://localhost:8888"
echo "  Data dir:  ${HOST_DATA_DIR}"
echo ""
echo "  To stop:   docker stop ${CONTAINER_NAME}"
echo "  To logs:   docker logs -f ${CONTAINER_NAME}"
echo "  To remove: docker rm ${CONTAINER_NAME}"
echo "================================================================================"
