from django.contrib import messages
from django.core.exceptions import ValidationError
from django.core.validators import EmailValidator
from django.shortcuts import redirect

from apps.planning.models import Tag


def _get_or_create_tags(names):
    return [Tag.objects.get_or_create(name=n)[0] for n in names if n.strip()]


_email_validator = EmailValidator()


def _validate_email(value):
    """Return an error string, or None if valid."""
    if not value:
        return "email is required"
    try:
        _email_validator(value)
    except ValidationError:
        return f"invalid email '{value}'"
    return None


def _validate_name(value):
    if not value:
        return "name is required"
    return None


def _validate_effort(value):
    """Empty → valid (treated as 0). Non-empty must be a non-negative number."""
    if not value:
        return None
    try:
        f = float(value)
    except ValueError:
        return f"effort_available must be a number (got '{value}')"
    if f < 0:
        return f"effort_available must be zero or positive (got '{value}')"
    return None


def _validate_rows(rows, validators):
    """Run per-field validators over CSV rows; return list of 'Row N: error' strings.

    validators: dict mapping field name → callable(value) → error string or None.
    Row numbering starts at 2 (row 1 is the header).
    """
    errors = []
    for i, row in enumerate(rows, start=2):
        for field, validate in validators.items():
            err = validate(row.get(field, "").strip())
            if err:
                errors.append(f"Row {i}: {err}")
    return errors


def _validate_developer_rows(rows):
    return _validate_rows(rows, {
        "email": _validate_email,
        "name": _validate_name,
        "effort_available": _validate_effort,
    })


def _validate_project_rows(rows):
    return _validate_rows(rows, {
        "name": _validate_name,
        "effort_resourced": _validate_effort,
    })


def _validate_observer_rows(rows, valid_project_names: set[str]):
    """Validate observer TSV rows; project_access names are cross-referenced against valid_project_names."""
    errors = []
    for i, row in enumerate(rows, start=2):
        email_err = _validate_email(row.get("email", "").strip())
        if email_err:
            errors.append(f"Row {i}: {email_err}")
        name_err = _validate_name(row.get("name", "").strip())
        if name_err:
            errors.append(f"Row {i}: {name_err}")
        unknown = [
            f"Row {i}: unknown project '{n}'"
            for n in (p.strip() for p in row.get("project_access", "").split(","))
            if n and n not in valid_project_names
        ]
        errors.extend(unknown)
    return errors


def _upload_error(request, redirect_name, errors):
    msg = "Upload failed — fix the following errors and try again:\n" + "\n".join(f"• {e}" for e in errors)
    messages.error(request, msg)
    return redirect(f"planning:{redirect_name}")
