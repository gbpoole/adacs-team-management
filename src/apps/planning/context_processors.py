from apps.planning.models import Semester
from apps.planning.views._mixins import _is_semester_developer
from apps.planning.views._mixins import _is_semester_observer
from apps.planning.views._semester import get_selected_semester


def semester_context(request):
    """Inject selected_semester, all_semesters, and user participation flags."""
    if not hasattr(request, "user") or not request.user.is_authenticated:
        return {}
    sem = get_selected_semester(request)
    all_sems = list(Semester.objects.order_by("year", "semester_type"))
    return {
        "selected_semester": sem,
        "all_semesters": all_sems,
        "user_is_semester_developer": _is_semester_developer(request.user, sem),
        "user_is_semester_observer": _is_semester_observer(request.user, sem),
    }
