#!/bin/bash
# Back up the MySQL database to a compressed file.
#
# Usage (from repo root — invoked by the cron wrapper or manually):
#   sudo bash scripts/backup-db.sh
#
# When called via the wrapper at /usr/local/bin/backup-adacs-db.sh, the
# APP_DIR environment variable is pre-set to the repository root.

set -euo pipefail

GREEN='\033[0;32m'; YELLOW='\033[1;33m'; NC='\033[0m'
info() { echo -e "${GREEN}[backup]${NC} $*"; }
warn() { echo -e "${YELLOW}[backup]${NC} $*"; }

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
APP_DIR="${APP_DIR:-$(cd "$SCRIPT_DIR/.." && pwd)}"
ENV_FILE="${APP_DIR}/.env"
COMPOSE_FILE="${APP_DIR}/docker-compose.yaml"
BACKUP_DIR="${BACKUP_DIR:-/var/backups/adacs}"
RETENTION_DAYS="${RETENTION_DAYS:-30}"
SWIFT_RETENTION_DAYS="${SWIFT_RETENTION_DAYS:-90}"
TIMESTAMP=$(date -u '+%Y%m%d_%H%M%S')
BACKUP_FILE="${BACKUP_DIR}/db_${TIMESTAMP}.sql.gz"
LOG_FILE="/var/log/adacs-backup.log"

# ---------------------------------------------------------------------------
# Validate environment
# ---------------------------------------------------------------------------
if [[ ! -f "$ENV_FILE" ]]; then
    echo "ERROR: .env not found at $ENV_FILE"
    exit 1
fi

if [[ ! -f "$COMPOSE_FILE" ]]; then
    echo "ERROR: docker-compose.yaml not found at $COMPOSE_FILE"
    exit 1
fi

if ! docker compose -f "$COMPOSE_FILE" ps db 2>/dev/null | grep -q 'running'; then
    echo "ERROR: MySQL container is not running. Start with: docker compose up -d"
    exit 1
fi

mkdir -p "$BACKUP_DIR"
chmod 700 "$BACKUP_DIR"

# ---------------------------------------------------------------------------
# Read credentials from .env (never hard-code or export secrets)
# ---------------------------------------------------------------------------
MYSQL_ROOT_PASSWORD=$(grep '^MYSQL_ROOT_PASSWORD=' "$ENV_FILE" | cut -d= -f2-)
MYSQL_DATABASE=$(grep '^MYSQL_DATABASE=' "$ENV_FILE" | cut -d= -f2-)

if [[ -z "$MYSQL_ROOT_PASSWORD" ]] || [[ -z "$MYSQL_DATABASE" ]]; then
    echo "ERROR: MYSQL_ROOT_PASSWORD or MYSQL_DATABASE not set in $ENV_FILE"
    exit 1
fi

# ---------------------------------------------------------------------------
# Run mysqldump via Docker
# --single-transaction: consistent snapshot without locking InnoDB tables
# --routines / --triggers: include stored routines and triggers
# ---------------------------------------------------------------------------
info "Dumping database '${MYSQL_DATABASE}' to ${BACKUP_FILE}..."

docker compose -f "$COMPOSE_FILE" exec -T db \
    mysqldump \
        --user=root \
        --password="${MYSQL_ROOT_PASSWORD}" \
        --single-transaction \
        --routines \
        --triggers \
        "${MYSQL_DATABASE}" \
    | gzip > "$BACKUP_FILE"

chmod 600 "$BACKUP_FILE"
BACKUP_SIZE=$(du -sh "$BACKUP_FILE" | cut -f1)
info "Backup written: ${BACKUP_FILE} (${BACKUP_SIZE})"

# ---------------------------------------------------------------------------
# Remove backups older than retention period
# ---------------------------------------------------------------------------
EXPIRED=$(find "$BACKUP_DIR" -name 'db_*.sql.gz' -mtime +"$RETENTION_DAYS" 2>/dev/null || true)
if [[ -n "$EXPIRED" ]]; then
    info "Removing backups older than ${RETENTION_DAYS} days..."
    echo "$EXPIRED" | xargs rm -f
fi

# ---------------------------------------------------------------------------
# Optional: push to Nectar Object Storage (Swift)
# Set SWIFT_BACKUP_CONTAINER in .env to enable.
# ---------------------------------------------------------------------------
SWIFT_CONTAINER=$(grep '^SWIFT_BACKUP_CONTAINER=' "$ENV_FILE" 2>/dev/null | cut -d= -f2- || true)
# Allow .env to override the default retention for Swift objects
_swift_ret=$(grep '^SWIFT_RETENTION_DAYS=' "$ENV_FILE" 2>/dev/null | cut -d= -f2- || true)
[[ -n "$_swift_ret" ]] && SWIFT_RETENTION_DAYS="$_swift_ret"

if [[ -n "$SWIFT_CONTAINER" ]]; then
    if command -v openstack &>/dev/null; then
        info "Uploading to Nectar Object Storage container: ${SWIFT_CONTAINER}..."
        openstack object create "$SWIFT_CONTAINER" "$BACKUP_FILE" \
            --name "$(basename "$BACKUP_FILE")"
        info "Uploaded."

        # Remove Swift objects whose filename date is older than the retention window.
        # Filenames have the form db_YYYYMMDD_HHMMSS.sql.gz so lexicographic comparison
        # of the YYYYMMDD prefix is safe.
        SWIFT_CUTOFF=$(date -u -d "${SWIFT_RETENTION_DAYS} days ago" '+%Y%m%d')
        info "Pruning Swift objects older than ${SWIFT_RETENTION_DAYS} days (before ${SWIFT_CUTOFF})..."
        while IFS= read -r obj; do
            obj_date="${obj#db_}"
            obj_date="${obj_date:0:8}"
            if [[ "$obj_date" < "$SWIFT_CUTOFF" ]]; then
                openstack object delete "$SWIFT_CONTAINER" "$obj" \
                    && info "Deleted old Swift object: ${obj}"
            fi
        done < <(openstack object list "$SWIFT_CONTAINER" -f value -c Name 2>/dev/null || true)
    else
        warn "SWIFT_BACKUP_CONTAINER is set but openstack CLI is not available."
    fi
fi

# ---------------------------------------------------------------------------
# Log completion
# ---------------------------------------------------------------------------
echo "$(date -u '+%Y-%m-%d %H:%M:%S UTC') backup OK ${BACKUP_FILE} ${BACKUP_SIZE}" \
    >> "$LOG_FILE" 2>/dev/null || true

info "Done."
