#!/usr/bin/env bash
# Inspect registered users and their email-verification / mail-queue status.
#
# Usage:
#   scripts/check_users.sh            # list all users (verified + active status)
#   scripts/check_users.sh --all      # same
#   scripts/check_users.sh <email>    # detailed check of one user + queued emails
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REPO_DIR="$(cd "$SCRIPT_DIR/.." && pwd)"
cd "$REPO_DIR"

mode="all"
email=""
case "${1:-}" in
    -h|--help) echo "usage: $0 [email]   (no email = list all users)"; exit 0 ;;
    -a|--all|"") mode="all" ;;
    *) email="$1"; mode="one" ;;
esac

docker compose exec -T django poetry run python manage.py shell <<PY
from django.contrib.auth import get_user_model
from allauth.account.models import EmailAddress
U = get_user_model()

mode = "${mode}"
email = "${email}"

if mode == "all":
    users = U.objects.order_by("-date_joined")
    verified = {e.lower() for e in EmailAddress.objects.filter(verified=True).values_list("email", flat=True)}
    print(f"{users.count()} users:")
    for u in users:
        v = u.email.lower() in verified
        print(f"  {u.date_joined:%Y-%m-%d %H:%M}  verified={str(v):5}  active={str(u.is_active):5}  {u.email}")
else:
    u = U.objects.filter(email__iexact=email).first()
    print("USER:", u, "| active:", getattr(u, "is_active", None), "| joined:", getattr(u, "date_joined", None))
    for e in EmailAddress.objects.filter(email__iexact=email):
        print("EMAILADDRESS:", e.email, "| verified:", e.verified, "| primary:", e.primary)
    try:
        from post_office.models import Email
        qs = Email.objects.filter(to__icontains=email).order_by("-created")[:5]
        print("QUEUED EMAILS:", qs.count())
        for e in qs:
            print("  ->", e.to, "| status:", e.status, "(0=sent,1=failed,2=queued)", "| subject:", e.subject)
    except Exception as ex:
        print("post_office check skipped:", ex)
PY
