#!/usr/bin/env bash
# Mail queue worker for the "cron" container.
#
# We deliberately do NOT use system cron here. cron runs jobs with a scrubbed
# environment, so the secrets injected by docker-compose (env_file: .env) —
# DJANGO_SECRET_KEY, the MySQL credentials, EMAIL_* — are invisible to a cron job.
# Django's prod settings (config.settings.prod) then fail to load and
# send_queued_mail crashes every minute, leaving verification emails stuck at
# status=2 (queued, never sent).
#
# Running this loop as a child of the container's PID 1 means it inherits the full
# environment, exactly like the django container does, so the queue actually drains.
set -u

cd /app/src

# The heartbeat is refreshed only after a *successful* send_queued_mail run. The
# container healthcheck treats a stale heartbeat as unhealthy, so a persistently
# failing worker shows up in `docker compose ps` / `make status` instead of failing
# silently the way the old cron job did.
HEARTBEAT="${MAIL_WORKER_HEARTBEAT:-/tmp/mail-worker.heartbeat}"

log() { echo "[mail-worker] $(date -u '+%Y-%m-%dT%H:%M:%SZ') $*"; }

last_cleanup_day=""

log "starting: send_queued_mail every 60s, cleanup_mail daily at 01:00 UTC"

while true; do
    if poetry run python manage.py send_queued_mail; then
        date -u +%s > "$HEARTBEAT"
    else
        log "ERROR: send_queued_mail failed (traceback above); heartbeat not refreshed"
    fi

    # Daily mail cleanup at ~01:00 UTC, at most once per day.
    if [ "$(date -u +%H)" = "01" ] && [ "$(date -u +%F)" != "$last_cleanup_day" ]; then
        if poetry run python manage.py cleanup_mail --days=30 --delete-attachments; then
            last_cleanup_day="$(date -u +%F)"
        else
            log "ERROR: cleanup_mail failed (traceback above)"
        fi
    fi

    sleep 60
done
