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

if [[ -z "$CHANGED" ]]; then
    info "No changes detected. Services already up to date."
    docker compose ps
    exit 0
fi

info "Changed files:"
echo "$CHANGED" | sed 's/^/  /'

# Determine whether static assets (CSS/JS) or Nginx config changed — if so,
# the nginx image must be rebuilt too (static files are baked in at build time).
NEEDS_NGINX=false
if [[ "$FULL_REBUILD" == "true" ]]; then
    NEEDS_NGINX=true
elif echo "$CHANGED" | grep -qE '(^styles\.css$|^package(-lock)?\.json$|^\.nvmrc$|^nginx/)'; then
    NEEDS_NGINX=true
    info "CSS/JS or Nginx config changed — will rebuild nginx image."
fi

# ---------------------------------------------------------------------------
# 3. Rebuild and restart affected services
# ---------------------------------------------------------------------------
if [[ "$NEEDS_NGINX" == "true" ]]; then
    info "Rebuilding django, nginx, and cron images..."
    docker compose build django nginx cron
    info "Restarting django, nginx, and cron..."
    docker compose up -d django nginx cron
else
    info "Rebuilding django and cron images..."
    docker compose build django cron
    info "Restarting django and cron..."
    docker compose up -d django cron
fi

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
