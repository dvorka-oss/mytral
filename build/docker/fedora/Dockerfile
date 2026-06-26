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

# MyTraL Docker image for Fedora
#
# Build context: a clean copy of the MyTraL source tree (see build.sh).
#
# Run with a host directory bound for data persistence:
#   docker run -p 8888:5000 -v ~/.local/share/mytral-docker-fedora:/mytral mytral-fedora:latest

FROM fedora:41

LABEL org.opencontainers.image.title="MyTraL"
LABEL org.opencontainers.image.description="My training log — personal sport training log web application"
LABEL org.opencontainers.image.licenses="AGPL-3.0"
LABEL org.opencontainers.image.source="https://github.com/dvorka/mytral"

#
# Install Python and uv
#
RUN dnf install -y \
        python3.12 \
        curl \
    && dnf clean all

# Install uv (fast Python package manager)
RUN curl -LsSf https://astral.sh/uv/install.sh | sh
ENV PATH="/root/.local/bin:${PATH}"

#
# Copy project source
#
COPY . /opt/mytral

#
# Install Python dependencies
#
WORKDIR /opt/mytral
RUN uv sync --no-dev --no-group dev --no-group test --no-group ml --no-group notebook --no-group desktop --no-group blob-minio --no-group blob-s3

#
# Runtime configuration
#

# Bind to all interfaces so the container is reachable from the host
ENV MYTRAL_HOST=0.0.0.0

# Default data directory — mount a host volume at /mytral for persistence.
# MYTRAL_DATA_DIR is the parent of the actual "data/" subdirectory, so
# the app stores data at /mytral/data/ inside the container.
ENV MYTRAL_DATA_DIR=/mytral

# Disable debug mode by default (override for development)
ENV MYTRAL_DEBUG=false

# Set the incarnation to DESKTOP by default to make use as simple as possible
ENV MYTRAL_INCARNATION=DESKTOP

# Enable user registration by default to make it easy to create an account
ENV MYTRAL_USER_REGISTRATION=true

# Enable caching by default to speed up the run
ENV MYTRAL_ENABLE_CACHE=true

# Create the data directory
RUN mkdir -p /mytral

# Expose the default MyTraL port
EXPOSE 5000

# Health check — poll the home page every 30 seconds
HEALTHCHECK --interval=30s --timeout=5s --start-period=10s --retries=3 \
    CMD curl -f http://localhost:5000/ || exit 1

# Run MyTraL
CMD ["uv", "run", "python", "-m", "mytral.run"]
