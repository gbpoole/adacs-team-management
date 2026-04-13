import datetime

from apps.planning.models import Semester
from apps.planning.views._mixins import _is_semester_developer
from apps.planning.views._mixins import _is_semester_observer
from apps.planning.views._semester import get_selected_semester


def _next_semester(all_sems):
    """Return (year, type) for the first semester that does not yet exist."""
    existing = {(s.year, s.semester_type) for s in all_sems}
    year = datetime.date.today().year
    for _ in range(20):  # scan at most 10 years ahead
        for s_type in ("A", "B"):
            if (year, s_type) not in existing:
                return year, s_type
        year += 1
    return year, "A"


def semester_context(request):
    """Inject selected_semester, all_semesters, and user participation flags."""
    if not hasattr(request, "user") or not request.user.is_authenticated:
        return {}
    sem = get_selected_semester(request)
    all_sems = list(Semester.objects.order_by("year", "semester_type"))
    next_year, next_type = _next_semester(all_sems)
    return {
        "selected_semester": sem,
        "all_semesters": all_sems,
        "user_is_semester_developer": _is_semester_developer(request.user, sem),
        "user_is_semester_observer": _is_semester_observer(request.user, sem),
        "next_semester_year": next_year,
        "next_semester_type": next_type,
    }
