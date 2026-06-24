# MyTraL Docker image for Debian
#
# Build context: a clean copy of the MyTraL source tree (see build.sh).
#
# Run with a host directory bound for data persistence:
#   docker run -p 8888:5000 -v ~/.local/share/mytral-docker-debian:/mytral mytral-debian:latest

FROM debian:bookworm-slim

LABEL org.opencontainers.image.title="MyTraL"
LABEL org.opencontainers.image.description="My training log — personal sport training log web application"
LABEL org.opencontainers.image.licenses="AGPL-3.0"
LABEL org.opencontainers.image.source="https://github.com/dvorka-oss/mytral"

# ---------------------------------------------------------------------------
# Install Python 3.11 and uv
# ---------------------------------------------------------------------------
RUN apt-get update && \
    apt-get install -y --no-install-recommends \
        python3.11 \
        python3.11-venv \
        python3-pip \
        curl \
        ca-certificates \
    && rm -rf /var/lib/apt/lists/*

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
