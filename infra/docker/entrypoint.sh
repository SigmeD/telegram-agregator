#!/usr/bin/env bash
# -----------------------------------------------------------------------------
# Backend entrypoint dispatcher.
#
# Usage:
#   entrypoint.sh <mode> [args...]
#
# Modes:
#   listener  — Telethon user-session listener (reads chats → queue)
#   worker    — Celery worker (LLM classification, scoring, enrichment)
#   api       — FastAPI (uvicorn) for the admin panel
#   bot       — Aiogram notification bot
#   migrate   — Alembic upgrade head (one-shot)
#   shell     — diagnostic shell
#
# Environment is expected to be provided via compose / CI secrets.
# -----------------------------------------------------------------------------
set -euo pipefail

MODE="${1:-api}"
shift || true

case "$MODE" in
  listener)
    exec python -m listener "$@"
    ;;
  worker)
    # CONCURRENCY tunable via env — defaults match small VPS profile.
    : "${WORKER_CONCURRENCY:=4}"
    : "${WORKER_QUEUES:=default,llm,enrich}"
    exec celery -A worker.celery_app worker \
        --loglevel="${LOG_LEVEL:-info}" \
        --concurrency="${WORKER_CONCURRENCY}" \
        --queues="${WORKER_QUEUES}" \
        "$@"
    ;;
  beat)
    exec celery -A worker.celery_app beat --loglevel="${LOG_LEVEL:-info}" "$@"
    ;;
  api)
    : "${API_HOST:=0.0.0.0}"
    : "${API_PORT:=8000}"
    : "${API_WORKERS:=2}"
    exec uvicorn api.main:app \
        --host "${API_HOST}" \
        --port "${API_PORT}" \
        --workers "${API_WORKERS}" \
        --proxy-headers \
        --forwarded-allow-ips="*" \
        "$@"
    ;;
  bot)
    exec python -m bot "$@"
    ;;
  migrate)
    exec alembic -c migrations/alembic.ini upgrade head
    ;;
  shell)
    exec /bin/bash "$@"
    ;;
  *)
    echo "[entrypoint] unknown mode: $MODE" >&2
    echo "Valid modes: listener | worker | beat | api | bot | migrate | shell" >&2
    exit 64
    ;;
esac
