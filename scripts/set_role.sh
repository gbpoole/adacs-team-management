#!/usr/bin/env bash
# Set a user's role (e.g. pm, user) by email address.
#
# Usage:
#   scripts/set_role.sh <email> <role>     # e.g. scripts/set_role.sh someone@example.com pm
#
# Inputs are passed to the Django shell via environment variables (not string
# interpolation) so the values are never spliced into the executed code.
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REPO_DIR="$(cd "$SCRIPT_DIR/.." && pwd)"
cd "$REPO_DIR"

usage() {
    echo "usage: $(basename "$0") <email> <role>   (e.g. $(basename "$0") someone@example.com pm)"
}

case "${1:-}" in
    -h|--help) usage; exit 0 ;;
esac

if [[ $# -lt 2 || -z "${1:-}" || -z "${2:-}" ]]; then
    echo "error: both <email> and <role> are required." >&2
    usage >&2
    exit 2
fi

export SET_ROLE_EMAIL="$1"
export SET_ROLE_VALUE="$2"

# Validation failures inside the shell exit 3 (message already printed there);
# any other non-zero exit means Docker/the shell itself could not run.
set +e
docker compose exec -T \
    -e SET_ROLE_EMAIL \
    -e SET_ROLE_VALUE \
    django poetry run python manage.py shell <<'PY'
import os
import sys

from django.contrib.auth import get_user_model

from apps.users.models import Role

email = os.environ["SET_ROLE_EMAIL"]
role = os.environ["SET_ROLE_VALUE"]

valid = sorted(Role.values)
if role not in valid:
    print(f"Invalid role {role!r}. Valid roles: {', '.join(valid)}", file=sys.stderr)
    sys.exit(3)

user = get_user_model().objects.filter(email__iexact=email).first()
if user is None:
    print(f"No user found with email {email!r}. Run `make check-users` to list accounts.", file=sys.stderr)
    sys.exit(3)

old = user.role
if old == role:
    print(f"{user.email}: role {old!r} -> {role!r} (no change)")
else:
    user.role = role
    user.save(update_fields=["role"])
    print(f"{user.email}: role {old!r} -> {user.role!r}")
PY
rc=$?
set -e

if [[ $rc -eq 0 || $rc -eq 3 ]]; then
    exit "$rc"
fi

echo "error: could not run the Django shell. Is the stack up (make status) and are you running from the repo root?" >&2
exit 1
