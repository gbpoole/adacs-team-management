from django.contrib.auth.mixins import LoginRequiredMixin
from django.shortcuts import redirect
from django.views import View

from apps.planning.models import Semester
from apps.users.models import Role

from ._mixins import RoleRequiredMixin
from ._mixins import _get_next_url


def get_selected_semester(request):
    """Return the user-selected semester from session, falling back to get_current()."""
    code = request.session.get("selected_semester")
    if code:
        try:
            return Semester.objects.get(year=int(code[:4]), semester_type=code[4])
        except (Semester.DoesNotExist, ValueError, IndexError, TypeError):
            pass
    return Semester.get_current()


class SemesterSwitchView(LoginRequiredMixin, View):
    """POST to switch the active semester stored in the session."""

    def post(self, request, *args, **kwargs):
        code = request.POST.get("semester", "").strip()
        if code:
            try:
                Semester.objects.get(year=int(code[:4]), semester_type=code[4])
                request.session["selected_semester"] = code
            except (Semester.DoesNotExist, ValueError, IndexError, TypeError):
                pass
        return redirect(_get_next_url(request, default="/planning/planning/"))


class SemesterCreateView(RoleRequiredMixin, View):
    """POST to create a new semester (for future planning)."""

    allowed_roles = (Role.PM,)

    def post(self, request, *args, **kwargs):
        year_str = request.POST.get("year", "").strip()
        s_type = request.POST.get("semester_type", "").strip().upper()
        if year_str and s_type in ("A", "B"):
            try:
                year = int(year_str)
                Semester.objects.get_or_create(year=year, semester_type=s_type)
            except (ValueError, TypeError):
                pass
        return redirect(_get_next_url(request, default="/planning/planning/"))
