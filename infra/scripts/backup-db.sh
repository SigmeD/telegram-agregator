#!/usr/bin/env bash
# =============================================================================
# pg_dump + gzip + upload to S3-compatible storage.
#
# Designed to run on the VPS from cron, e.g.:
#   15 3 * * *  /opt/tlg/infra/scripts/backup-db.sh prod
#
# Required env:
#   POSTGRES_USER, POSTGRES_PASSWORD, POSTGRES_DB
#   S3_BUCKET, S3_PREFIX (optional)
#   AWS_ACCESS_KEY_ID, AWS_SECRET_ACCESS_KEY, AWS_DEFAULT_REGION
#     (or configure an alternative endpoint via S3_ENDPOINT for Timeweb/Backblaze)
# =============================================================================
set -Eeuo pipefail

ENV_NAME="${1:-prod}"
: "${POSTGRES_USER:?}"
: "${POSTGRES_PASSWORD:?}"
: "${POSTGRES_DB:?}"

STAMP="$(date -u +%Y%m%dT%H%M%SZ)"
OUT_DIR="${BACKUP_OUT_DIR:-/var/backups/tlg/pg}"
OUT_FILE="${OUT_DIR}/${ENV_NAME}-${POSTGRES_DB}-${STAMP}.sql.gz"

log() { printf '[backup-db %s] %s\n' "$(date -u +%H:%M:%S)" "$*"; }

mkdir -p "${OUT_DIR}"

log "dumping ${POSTGRES_DB} → ${OUT_FILE}"
# Run pg_dump from the running postgres container — avoids needing client libs
# on the host and guarantees version match.
docker exec -e PGPASSWORD="${POSTGRES_PASSWORD}" \
    "$(docker compose --project-directory "$(dirname "$0")/../compose" ps -q postgres)" \
    pg_dump -U "${POSTGRES_USER}" -d "${POSTGRES_DB}" --format=plain --no-owner \
    | gzip -9 > "${OUT_FILE}"

log "local dump size: $(du -h "${OUT_FILE}" | cut -f1)"

# ----- upload (stub; aws-cli or s3cmd required) -----------------------------
if command -v aws >/dev/null 2>&1; then
    : "${S3_BUCKET:?S3_BUCKET required for upload}"
    S3_PREFIX="${S3_PREFIX:-tlg/${ENV_NAME}/pg}"
    S3_URI="s3://${S3_BUCKET}/${S3_PREFIX}/$(basename "${OUT_FILE}")"
    EXTRA_ARGS=()
    [[ -n "${S3_ENDPOINT:-}" ]] && EXTRA_ARGS=(--endpoint-url "${S3_ENDPOINT}")
    log "uploading to ${S3_URI}"
    aws "${EXTRA_ARGS[@]}" s3 cp "${OUT_FILE}" "${S3_URI}" --only-show-errors
    log "upload complete"
else
    log "WARN: aws-cli not installed — dump kept locally only"
fi

# ----- retention (local) ----------------------------------------------------
find "${OUT_DIR}" -type f -name "*.sql.gz" -mtime "+${RETENTION_DAYS:-14}" -delete || true

log "done"
