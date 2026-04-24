# syntax=docker/dockerfile:1.7
# =============================================================================
# Telegram Lead Aggregator — backend image
# Single image, four run modes switched by ENTRYPOINT argument:
#   listener | worker | api | bot
# =============================================================================

# -----------------------------------------------------------------------------
# Stage 1: builder — resolves dependencies with `uv` and produces a venv.
# -----------------------------------------------------------------------------
FROM python:3.11-slim-bookworm AS builder

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PIP_NO_CACHE_DIR=1 \
    UV_SYSTEM_PYTHON=0 \
    UV_LINK_MODE=copy \
    UV_PROJECT_ENVIRONMENT=/opt/venv

# Build deps needed for asyncpg / cryptography wheels fallback
RUN apt-get update \
    && apt-get install -y --no-install-recommends \
        build-essential \
        curl \
        ca-certificates \
        libffi-dev \
        libssl-dev \
    && rm -rf /var/lib/apt/lists/*

# Install uv (pinned minor)
COPY --from=ghcr.io/astral-sh/uv:0.5 /uv /usr/local/bin/uv

WORKDIR /app

# Copy only dependency descriptors first — maximises layer cache hits.
COPY backend/pyproject.toml backend/README.md ./
# Optional lockfile — copy if present so we pin.
# (Use a wildcard so the build does not fail when the lock is missing locally.)
COPY backend/uv.lock* ./

RUN uv venv /opt/venv \
    && uv sync --frozen --no-install-project --extra dev || uv sync --no-install-project --extra dev

# Now copy source and install the project itself into the venv.
COPY backend/src ./src
COPY backend/migrations ./migrations
COPY backend/prompts ./prompts
COPY backend/seeds ./seeds

RUN uv sync --no-editable || uv pip install --python /opt/venv/bin/python .

# -----------------------------------------------------------------------------
# Stage 2: runtime — slim, non-root, only what we need to run.
# -----------------------------------------------------------------------------
FROM python:3.11-slim-bookworm AS runtime

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PATH="/opt/venv/bin:$PATH" \
    VIRTUAL_ENV=/opt/venv \
    PYTHONPATH=/app/src \
    APP_HOME=/app \
    TLG_SESSION_DIR=/var/lib/tlg/sessions

RUN apt-get update \
    && apt-get install -y --no-install-recommends \
        curl \
        ca-certificates \
        tini \
        postgresql-client \
    && rm -rf /var/lib/apt/lists/* \
    && groupadd --system --gid 1001 app \
    && useradd --system --uid 1001 --gid app --home-dir /home/app --create-home app \
    && mkdir -p /var/lib/tlg/sessions /app \
    && chown -R app:app /var/lib/tlg /app

WORKDIR /app

# Bring the ready venv and source over from the builder.
COPY --from=builder --chown=app:app /opt/venv /opt/venv
COPY --from=builder --chown=app:app /app/src ./src
COPY --from=builder --chown=app:app /app/migrations ./migrations
COPY --from=builder --chown=app:app /app/prompts ./prompts
COPY --from=builder --chown=app:app /app/seeds ./seeds
COPY --chown=app:app backend/pyproject.toml ./pyproject.toml

# Entrypoint dispatcher lives in the image.
COPY --chown=app:app infra/docker/entrypoint.sh /usr/local/bin/entrypoint.sh
RUN chmod +x /usr/local/bin/entrypoint.sh

USER app

# Default HTTP port used by the `api` mode. Harmless for other modes.
EXPOSE 8000

# Generic healthcheck: modes override it in compose where it matters (API).
HEALTHCHECK --interval=30s --timeout=5s --start-period=20s --retries=3 \
    CMD python -c "import sys; sys.exit(0)" || exit 1

ENTRYPOINT ["/usr/bin/tini", "--", "/usr/local/bin/entrypoint.sh"]
CMD ["api"]
