#!/usr/bin/env bash
# Report the state of the outbound (post_office) mail queue: how many messages are
# sent / failed / queued, how stale the oldest undelivered message is, and the most
# recent failures. Run this to confirm the mail worker is actually draining the queue.
#
# Usage:
#   scripts/check_mail_queue.sh
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REPO_DIR="$(cd "$SCRIPT_DIR/.." && pwd)"
cd "$REPO_DIR"

# Runs against the django container (which has the full environment and DB access),
# not the cron/worker container.
docker compose exec -T django poetry run python manage.py shell <<'PY'
from django.utils import timezone
from post_office.models import Email, STATUS

labels = {STATUS.sent: "sent", STATUS.failed: "failed", STATUS.queued: "queued", STATUS.requeued: "requeued"}

print("Mail queue (post_office):")
for status, label in labels.items():
    print(f"  {label:9} {Email.objects.filter(status=status).count()}")

pending = Email.objects.filter(status__in=[STATUS.queued, STATUS.requeued]).order_by("created")
oldest = pending.first()
if oldest is not None:
    age = timezone.now() - oldest.created
    mins = int(age.total_seconds() // 60)
    print(f"\nOldest undelivered message: {mins} min old (created {oldest.created:%Y-%m-%d %H:%M})")
    print("  -> If this keeps growing, the worker is not draining the queue"
          " (check `docker compose logs cron` / `make status`).")
else:
    print("\nNothing queued — the worker is keeping up.")

recent_failures = Email.objects.filter(status=STATUS.failed).order_by("-last_updated")[:5]
if recent_failures:
    print("\nRecent failures:")
    for e in recent_failures:
        print(f"  {e.last_updated:%Y-%m-%d %H:%M}  -> {e.to}  | {e.subject}")
PY
