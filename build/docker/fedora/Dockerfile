# MyTraL Docker image for Fedora
#
# Build context: a clean copy of the MyTraL source tree (see build.sh).
#
# Run with MYTRAL_DATA_DIR bound to a host directory for data persistence:
#   docker run -p 8888:5000 -v ~/.local/share/mytral-docker:/data mytral-fedora:latest

FROM fedora:41

LABEL org.opencontainers.image.title="MyTraL"
LABEL org.opencontainers.image.description="My training log — personal sport training log web application"
LABEL org.opencontainers.image.licenses="AGPL-3.0"
LABEL org.opencontainers.image.source="https://github.com/dvorka/my-training-log"

# ---------------------------------------------------------------------------
# Install Python 3.11 and uv
# ---------------------------------------------------------------------------
RUN dnf install -y \
        python3.11 \
        curl \
    && dnf clean all

# Install uv (fast Python package manager)
RUN curl -LsSf https://astral.sh/uv/install.sh | sh
ENV PATH="/root/.local/bin:${PATH}"

# ---------------------------------------------------------------------------
# Copy project source
# ---------------------------------------------------------------------------
COPY . /opt/mytral

# ---------------------------------------------------------------------------
# Install Python dependencies
# ---------------------------------------------------------------------------
WORKDIR /opt/mytral
RUN uv sync --no-dev --no-group dev --no-group test --no-group ml --no-group notebook --no-group desktop --no-group blob-minio --no-group blob-s3

# ---------------------------------------------------------------------------
# Runtime configuration
# ---------------------------------------------------------------------------

# Bind to all interfaces so the container is reachable from the host
ENV MYTRAL_HOST=0.0.0.0

# Default data directory — mount a host volume here for persistence
ENV MYTRAL_DATA_DIR=/data

# Disable debug mode by default (override for development)
ENV MYTRAL_DEBUG=false

# Disable auto account creation by default
ENV MYTRAL_AUTO_ACCOUNT_CREATE=false

# Disable user registration by default
ENV MYTRAL_USER_REGISTRATION=false

# Create the data directory
RUN mkdir -p /data

# Expose the default MyTraL port
EXPOSE 5000

# Health check — poll the home page every 30 seconds
HEALTHCHECK --interval=30s --timeout=5s --start-period=10s --retries=3 \
    CMD curl -f http://localhost:5000/ || exit 1

# Run MyTraL
CMD ["uv", "run", "python", "-m", "mytral.run"]
