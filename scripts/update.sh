#!/bin/bash
# Pull the latest code and rebuild/restart only the affected Docker services.
# Run as the ubuntu user (no sudo required).
#
# Usage:
#   bash scripts/update.sh          # auto-detect what changed
#   bash scripts/update.sh --full   # always rebuild all services

set -euo pipefail

GREEN='\033[0;32m'; YELLOW='\033[1;33m'; NC='\033[0m'
info() { echo -e "${GREEN}[update]${NC} $*"; }
warn() { echo -e "${YELLOW}[update]${NC} $*"; }

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REPO_DIR="$(cd "$SCRIPT_DIR/.." && pwd)"
FULL_REBUILD=false

while [[ $# -gt 0 ]]; do
    case "$1" in
        --full) FULL_REBUILD=true; shift ;;
        *) echo "Unknown argument: $1"; echo "Usage: bash scripts/update.sh [--full]"; exit 1 ;;
    esac
done

cd "$REPO_DIR"

# ---------------------------------------------------------------------------
# 1. Pull latest code
# ---------------------------------------------------------------------------
info "Pulling latest code..."
git pull

# ---------------------------------------------------------------------------
# 2. Detect what changed since the previous HEAD
# ---------------------------------------------------------------------------
CHANGED=$(git diff HEAD@{1} HEAD --name-only 2>/dev/null || true)

if [[ -z "$CHANGED" && "$FULL_REBUILD" == "false" ]]; then
    info "No changes detected. Services already up to date."
    info "Use --full to force a rebuild anyway (e.g. to recover a broken deploy)."
    docker compose ps
    exit 0
fi

if [[ -n "$CHANGED" ]]; then
    info "Changed files:"
    echo "$CHANGED" | sed 's/^/  /'
fi

# ---------------------------------------------------------------------------
# 3. Rebuild and restart services
# ---------------------------------------------------------------------------
# django and nginx must ALWAYS be rebuilt together. Static files use
# content-hashed filenames (ManifestStaticFilesStorage), and Tailwind's compiled
# CSS depends on the templates/JS it scans — so a template or JS change alters the
# hashes. The hash manifest is baked into the django image while the hashed files
# are baked into the nginx image; rebuilding one without the other leaves nginx
# serving filenames the manifest no longer references (404 → CSS/JS vanish).
# Rebuilding nginx is nearly free when nothing static changed: the shared builder
# stage (npm build + collectstatic) is reused from cache.
info "Rebuilding django, nginx, and cron images..."
docker compose build django nginx cron
info "Restarting django, nginx, and cron..."
docker compose up -d django nginx cron

# ---------------------------------------------------------------------------
# 4. Wait for health
# ---------------------------------------------------------------------------
# Migrations run automatically in docker-entrypoint.sh — give the container
# time to migrate before declaring it healthy.
info "Waiting for application health check (up to 3 minutes)..."
MAX_ATTEMPTS=36
ATTEMPT=0
while [[ $ATTEMPT -lt $MAX_ATTEMPTS ]]; do
    if curl -fsS http://localhost:8000/health/ &>/dev/null; then
        info "Application is healthy."
        break
    fi
    sleep 5
    ATTEMPT=$((ATTEMPT + 1))
    printf '.'
done
echo

if [[ $ATTEMPT -ge $MAX_ATTEMPTS ]]; then
    warn "Health check timed out. Check: docker compose logs -f"
fi

# ---------------------------------------------------------------------------
# 5. Status summary
# ---------------------------------------------------------------------------
info "Service status:"
docker compose ps
