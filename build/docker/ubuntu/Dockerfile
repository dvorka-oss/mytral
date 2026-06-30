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

# MyTraL per-Ubuntu-release test image.
#
# Faithful end-to-end test of the Ubuntu .deb on one specific release:
#   1. build the .deb ON that release (uv provisions Python 3.12 for the wheel),
#   2. install the .deb (postinst provisions uv + Python 3.12, installs the app),
#   3. leave MyTraL ready to run for manual testing.
#
# Everything happens at image-build time, so a failure on the chosen release
# (build, TLS to GitHub, glibc, ...) fails the build loudly. Pick the release
# with --build-arg UBUNTU_RELEASE=<codename> (see build.sh / run.sh).
#
# Build context: a clean copy of the MyTraL source tree with the old-Ubuntu
# debian/ overlay applied at the root (see build.sh).

ARG UBUNTU_RELEASE=trusty
FROM ubuntu:${UBUNTU_RELEASE}

LABEL org.opencontainers.image.title="MyTraL"
LABEL org.opencontainers.image.description="My training log — personal sport training log web application"
LABEL org.opencontainers.image.licenses="AGPL-3.0"
LABEL org.opencontainers.image.source="https://github.com/dvorka-oss/mytral"

ENV DEBIAN_FRONTEND=noninteractive

# pinned uv release — must match debian/postinst
ENV UV_VERSION=0.7.8

#
# Install the Debian packaging toolchain (works back to trusty's debhelper 9)
#
COPY build/docker/ubuntu/apt-setup.sh /tmp/apt-setup.sh
RUN sh /tmp/apt-setup.sh && \
    apt-get install -y --no-install-recommends \
        build-essential \
        debhelper \
        devscripts \
        dpkg-dev \
        fakeroot \
        curl \
        ca-certificates \
        xz-utils \
    && rm -rf /var/lib/apt/lists/*

#
# Install uv — fetched straight from GitHub releases, the same source and
# version debian/postinst uses, so the build exercises the same TLS path.
#
RUN curl -LsSf \
        "https://github.com/astral-sh/uv/releases/download/${UV_VERSION}/uv-x86_64-unknown-linux-gnu.tar.gz" \
        | tar -xz -C /usr/local/bin --strip-components=1 uv-x86_64-unknown-linux-gnu/uv

#
# Build the .deb on this release
#
COPY . /opt/mytral-src
WORKDIR /opt/mytral-src
RUN dpkg-buildpackage -b -us -uc

#
# Install the freshly built .deb — postinst provisions uv + Python 3.12 and
# installs the app under /opt/mytral. The cache update is needed because -f
# install pulls runtime dependencies from apt.
#
RUN ( dpkg -i ../mytral_*.deb || ( sh /tmp/apt-setup.sh && apt-get -f install -y ) ) && \
    rm -rf /var/lib/apt/lists/* ../mytral_*

#
# Runtime configuration (mirrors build/docker/debian/Dockerfile)
#

# bind to all interfaces so the container is reachable from the host
ENV MYTRAL_HOST=0.0.0.0

# data directory — mount a host volume at /mytral for persistence
ENV MYTRAL_DATA_DIR=/mytral

# disable debug mode by default (override for development)
ENV MYTRAL_DEBUG=false

# desktop incarnation keeps first-run as simple as possible
ENV MYTRAL_INCARNATION=DESKTOP

# enable user registration by default to make it easy to create an account
ENV MYTRAL_USER_REGISTRATION=true

# enable caching by default to speed up the run
ENV MYTRAL_ENABLE_CACHE=true

RUN mkdir -p /mytral

EXPOSE 5000

# health check — poll the home page every 30 seconds
HEALTHCHECK --interval=30s --timeout=5s --start-period=15s --retries=3 \
    CMD curl -f http://localhost:5000/ || exit 1

# run the installed web server (the wrapper execs /opt/mytral/venv/bin/mytral-web)
CMD ["/usr/bin/mytral-web"]
