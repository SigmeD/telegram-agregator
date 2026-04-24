#!/usr/bin/env bash
# =============================================================================
# Rotate Telethon user-session file.
#
# The Telethon session is the most sensitive artefact in the system: whoever
# holds it reads the monitored chats. This script is a STUB — flesh out step
# (3) once the on-disk format and KMS / secret store are finalised.
#
# Usage:
#   rotate-session.sh <env>
#
# Flow (target):
#   1. Pause the listener container so no writes happen to the session file.
#   2. Snapshot the current session (encrypted copy → secure storage).
#   3. Pull a freshly-issued session (produced by the operator via Telethon
#      interactive auth on a secure host), decrypt with TELETHON_SESSION_KEY,
#      write atomically into the session volume.
#   4. Unpause the listener and wait for it to report healthy.
#   5. Emit an audit event to the API (/internal/audit) for bookkeeping.
# =============================================================================
set -Eeuo pipefail

ENV_NAME="${1:?usage: rotate-session.sh <dev|prod>}"
: "${TELETHON_SESSION_KEY:?TELETHON_SESSION_KEY must be set}"

SCRIPT_DIR="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" &>/dev/null && pwd)"
COMPOSE_DIR="${SCRIPT_DIR}/../compose"
SESSION_VOLUME="tlg-session-data"
BACKUP_DIR="${BACKUP_DIR:-/var/backups/tlg/sessions}"

log() { printf '[rotate-session %s] %s\n' "$(date -u +%H:%M:%S)" "$*"; }

log "env=${ENV_NAME}"
mkdir -p "${BACKUP_DIR}"

# 1. Stop listener
log "stopping backend-listener..."
docker compose --project-directory "${COMPOSE_DIR}" stop backend-listener

# 2. Snapshot
STAMP="$(date -u +%Y%m%dT%H%M%SZ)"
SNAP="${BACKUP_DIR}/session-${ENV_NAME}-${STAMP}.tar.gz.enc"
log "snapshotting current session → ${SNAP}"
docker run --rm \
    -v "${SESSION_VOLUME}:/data:ro" \
    -v "${BACKUP_DIR}:/out" \
    alpine:3.20 \
    sh -c "apk add --no-cache openssl >/dev/null && \
           tar -C /data -cz . | openssl enc -aes-256-cbc -salt -pbkdf2 \
             -pass env:TELETHON_SESSION_KEY -out /out/$(basename "${SNAP}")" \
    || log "WARN: snapshot failed — continuing, but no backup exists"

# 3. TODO: Import new session from secret store.
# The operator is expected to produce `new-session.session` encrypted with
# TELETHON_SESSION_KEY and upload it via the operator UI / secret manager.
log "TODO: implement import of the new session blob — stub exits here"

# 4. Restart listener
log "starting backend-listener..."
docker compose --project-directory "${COMPOSE_DIR}" start backend-listener

# 5. Audit (best-effort)
curl -fsS -X POST "${AUDIT_URL:-http://127.0.0.1:8000/internal/audit}" \
    -H 'Content-Type: application/json' \
    -d "{\"event\":\"session.rotate\",\"env\":\"${ENV_NAME}\",\"at\":\"${STAMP}\"}" \
    || log "WARN: audit POST failed"

log "done (stub). Review TODO in step 3 before relying on this in prod."
