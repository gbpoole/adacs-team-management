#!/usr/bin/env bash
# Manually verify (activate) a registered user's email address without them having
# to click the confirmation link. Useful when the outbound mail queue is stuck and a
# user cannot receive their verification email.
#
# Usage:
#   scripts/verify_user.sh <email>     # e.g. scripts/verify_user.sh someone@example.com
#
# The email is passed to the Django shell via an environment variable (not string
# interpolation) so the value is never spliced into the executed code.
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REPO_DIR="$(cd "$SCRIPT_DIR/.." && pwd)"
cd "$REPO_DIR"

usage() {
    echo "usage: $(basename "$0") <email>   (e.g. $(basename "$0") someone@example.com)"
}

case "${1:-}" in
    -h|--help) usage; exit 0 ;;
esac

if [[ $# -lt 1 || -z "${1:-}" ]]; then
    echo "error: <email> is required." >&2
    usage >&2
    exit 2
fi

export VERIFY_USER_EMAIL="$1"

# Validation failures inside the shell exit 3 (message already printed there);
# any other non-zero exit means Docker/the shell itself could not run.
set +e
docker compose exec -T \
    -e VERIFY_USER_EMAIL \
    django poetry run python manage.py shell <<'PY'
import os
import sys

from django.contrib.auth import get_user_model
from allauth.account.models import EmailAddress

email = os.environ["VERIFY_USER_EMAIL"]

user = get_user_model().objects.filter(email__iexact=email).first()
if user is None:
    print(f"No user found with email {email!r}. Run `make check-users` to list accounts.", file=sys.stderr)
    sys.exit(3)

# Ensure the account itself is enabled.
if not user.is_active:
    user.is_active = True
    user.save(update_fields=["is_active"])
    print(f"{user.email}: is_active -> True")

# Mark the allauth email address verified, creating the record if allauth never did.
address = EmailAddress.objects.filter(user=user, email__iexact=user.email).first()
if address is None:
    has_primary = EmailAddress.objects.filter(user=user, primary=True).exists()
    EmailAddress.objects.create(
        user=user, email=user.email, verified=True, primary=not has_primary
    )
    print(f"{user.email}: created verified EmailAddress record")
elif address.verified:
    print(f"{user.email}: already verified (no change)")
else:
    address.verified = True
    if not EmailAddress.objects.filter(user=user, primary=True).exists():
        address.primary = True
    address.save(update_fields=["verified", "primary"])
    print(f"{user.email}: verified -> True")
PY
rc=$?
set -e

if [[ $rc -eq 0 || $rc -eq 3 ]]; then
    exit "$rc"
fi

echo "error: could not run the Django shell. Is the stack up (make status) and are you running from the repo root?" >&2
exit 1
