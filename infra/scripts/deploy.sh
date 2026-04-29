#!/usr/bin/env bash
# =============================================================================
# Idempotent deploy for the backend stack.
#
# Usage:
#   deploy.sh <env> <image_tag> [--skip-migrations]
#
# Arguments:
#   <env>         dev | prod
#   <image_tag>   ghcr.io/... tag to roll out (sha-xxx, semver, develop, ...)
#
# Behaviour:
#   1. Validates args and required env vars.
#   2. Pulls the target image.
#   3. Runs Alembic migrations in a one-shot container (pg_advisory_lock in
#      env.py protects against concurrent migrations).
#   4. Starts / updates services (docker compose up -d).
#   5. Waits for /health on backend-api.
#   6. On failure — rolls back to the previous tag stored in LAST_GOOD_TAG_FILE.
# =============================================================================
set -Eeuo pipefail

SCRIPT_DIR="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" &>/dev/null && pwd)"
REPO_ROOT="$(cd -- "${SCRIPT_DIR}/../.." &>/dev/null && pwd)"
COMPOSE_DIR="${REPO_ROOT}/infra/compose"
STATE_DIR="${STATE_DIR:-/var/lib/tlg-aggregator}"
LAST_GOOD_TAG_FILE="${STATE_DIR}/last-good-tag"

log()  { printf '[deploy %s] %s\n' "$(date -u +%H:%M:%S)" "$*"; }
die()  { printf '[deploy ERROR] %s\n' "$*" >&2; exit 1; }

# ---- args ------------------------------------------------------------------
ENV_NAME="${1:?usage: deploy.sh <dev|prod> <image_tag> [--skip-migrations]}"
IMAGE_TAG="${2:?image_tag required}"
shift 2 || true
SKIP_MIGRATIONS="false"
for arg in "$@"; do
    case "$arg" in
        --skip-migrations) SKIP_MIGRATIONS="true" ;;
        *) die "unknown flag: $arg" ;;
    esac
done

case "$ENV_NAME" in
    dev)  OVERRIDE_FILE="docker-compose.dev.yml"  ;;
    prod) OVERRIDE_FILE="docker-compose.prod.yml" ;;
    *)    die "env must be 'dev' or 'prod', got: $ENV_NAME" ;;
esac

# ---- checks ----------------------------------------------------------------
command -v docker >/dev/null || die "docker not installed"
docker compose version >/dev/null 2>&1 || die "docker compose plugin required"

[[ -f "${COMPOSE_DIR}/docker-compose.yml" ]] || die "base compose not found"
[[ -f "${COMPOSE_DIR}/${OVERRIDE_FILE}" ]]   || die "override ${OVERRIDE_FILE} not found"

: "${POSTGRES_PASSWORD:?POSTGRES_PASSWORD must be set in the environment}"

sudo mkdir -p "${STATE_DIR}" 2>/dev/null || mkdir -p "${STATE_DIR}" || true

export BACKEND_TAG="${IMAGE_TAG}"
export BACKEND_IMAGE="${BACKEND_IMAGE:-ghcr.io/sigmed/tlg-aggregator}"

# Defaults for compose-substitution; can be overridden via env (e.g. prod uses POSTGRES_DB=tlg).
export POSTGRES_USER="${POSTGRES_USER:-tlg}"
case "$ENV_NAME" in
    dev)  export POSTGRES_DB="${POSTGRES_DB:-tlg_dev}" ;;
    prod) export POSTGRES_DB="${POSTGRES_DB:-tlg}" ;;
esac

# ---- transient backend.env ------------------------------------------------
# Compose reads `infra/env/backend.env` via `env_file:`; we generate it on
# every deploy from environment variables that arrive over SSH from GH Secrets.
# The file is gitignored (see .gitignore) and chmod 600.
write_backend_env() {
    local env_file="${REPO_ROOT}/infra/env/backend.env"
    log "writing transient ${env_file}"
    mkdir -p "$(dirname "${env_file}")"
    : "${TELEGRAM_API_ID:?TELEGRAM_API_ID required}"
    : "${TELEGRAM_API_HASH:?TELEGRAM_API_HASH required}"
    : "${TELEGRAM_PHONE:?TELEGRAM_PHONE required}"
    : "${TELETHON_SESSION_KEY:?TELETHON_SESSION_KEY required}"
    : "${ANTHROPIC_API_KEY:?ANTHROPIC_API_KEY required}"
    : "${NOTIFY_BOT_TOKEN:?NOTIFY_BOT_TOKEN required}"
    : "${NOTIFY_BOT_ADMIN_CHAT_ID:?NOTIFY_BOT_ADMIN_CHAT_ID required}"
    : "${JWT_SECRET:?JWT_SECRET required}"
    cat > "${env_file}" <<EOF
POSTGRES_USER=${POSTGRES_USER}
POSTGRES_PASSWORD=${POSTGRES_PASSWORD}
POSTGRES_DB=${POSTGRES_DB}
TELEGRAM_API_ID=${TELEGRAM_API_ID}
TELEGRAM_API_HASH=${TELEGRAM_API_HASH}
TELEGRAM_PHONE=${TELEGRAM_PHONE}
TELETHON_SESSION_KEY=${TELETHON_SESSION_KEY}
ANTHROPIC_API_KEY=${ANTHROPIC_API_KEY}
OPENAI_API_KEY=${OPENAI_API_KEY:-}
PROMPT_VERSION=${PROMPT_VERSION:-v1}
LLM_DAILY_COST_LIMIT_USD=${LLM_DAILY_COST_LIMIT_USD:-10.0}
NOTIFY_BOT_TOKEN=${NOTIFY_BOT_TOKEN}
NOTIFY_BOT_ADMIN_CHAT_ID=${NOTIFY_BOT_ADMIN_CHAT_ID}
JWT_SECRET=${JWT_SECRET}
SENTRY_DSN=${SENTRY_DSN:-}
LOG_LEVEL=${LOG_LEVEL:-INFO}
REDIS_MAXMEMORY=${REDIS_MAXMEMORY:-512mb}
API_PORT=${API_PORT:-8000}
BACKEND_TAG=${BACKEND_TAG}
EOF
    chmod 600 "${env_file}"
}
write_backend_env

COMPOSE=(docker compose \
    --project-directory "${COMPOSE_DIR}" \
    -f "${COMPOSE_DIR}/docker-compose.yml" \
    -f "${COMPOSE_DIR}/${OVERRIDE_FILE}")

# Save the currently-running tag BEFORE we overwrite it, for rollback.
PREVIOUS_TAG=""
if [[ -f "${LAST_GOOD_TAG_FILE}" ]]; then
    PREVIOUS_TAG="$(cat "${LAST_GOOD_TAG_FILE}")"
fi
log "env=${ENV_NAME} tag=${IMAGE_TAG} previous_good=${PREVIOUS_TAG:-<none>}"

# ---- trap for rollback -----------------------------------------------------
rollback() {
    local exit_code=$?
    trap - ERR EXIT
    if [[ $exit_code -eq 0 ]]; then
        return 0
    fi
    log "deploy failed (exit=${exit_code})"
    if [[ -n "${PREVIOUS_TAG}" && "${PREVIOUS_TAG}" != "${IMAGE_TAG}" ]]; then
        log "rolling back to ${PREVIOUS_TAG}"
        BACKEND_TAG="${PREVIOUS_TAG}" "${COMPOSE[@]}" up -d --no-build \
            backend-listener backend-worker backend-api backend-bot || true
    else
        log "no previous tag recorded — cannot auto-rollback, manual intervention required"
    fi
    exit "${exit_code}"
}
trap rollback ERR

# ---- pull ------------------------------------------------------------------
log "pulling images..."
"${COMPOSE[@]}" pull --quiet postgres redis || true
"${COMPOSE[@]}" pull backend-listener backend-worker backend-api backend-bot migrate

# ---- migrations ------------------------------------------------------------
if [[ "${SKIP_MIGRATIONS}" == "true" ]]; then
    log "skipping migrations (--skip-migrations)"
else
    log "running alembic upgrade head..."
    "${COMPOSE[@]}" up -d postgres redis
    "${COMPOSE[@]}" run --rm --no-deps migrate
fi

# ---- rollout ---------------------------------------------------------------
log "starting / updating services..."
"${COMPOSE[@]}" up -d --remove-orphans \
    postgres redis backend-listener backend-worker backend-api backend-bot \
    $( [[ "${ENV_NAME}" == "prod" ]] && echo "nginx" )

# ---- smoke test ------------------------------------------------------------
HEALTH_URL="${HEALTH_URL:-http://127.0.0.1:${API_PORT:-8000}/health}"
log "smoke-testing ${HEALTH_URL}"
ATTEMPTS="${HEALTH_ATTEMPTS:-30}"
SLEEP_SEC="${HEALTH_SLEEP:-2}"
for i in $(seq 1 "${ATTEMPTS}"); do
    if curl -fsS --max-time 3 "${HEALTH_URL}" >/dev/null 2>&1; then
        log "health check passed on attempt ${i}"
        echo -n "${IMAGE_TAG}" > "${LAST_GOOD_TAG_FILE}" || true
        log "deploy OK — recorded ${IMAGE_TAG} as last-good"
        trap - ERR
        exit 0
    fi
    sleep "${SLEEP_SEC}"
done

die "health check failed after ${ATTEMPTS} attempts (will trigger rollback)"
