from django.contrib.auth.mixins import LoginRequiredMixin
from django.core.exceptions import PermissionDenied
from django.utils.http import url_has_allowed_host_and_scheme

from apps.users.models import Role


def _get_next_url(request, default="/planning/planning/"):
    url = request.POST.get("next") or request.META.get("HTTP_REFERER", default)
    if url_has_allowed_host_and_scheme(url, allowed_hosts={request.get_host()}):
        return url
    return default


def _update_user_profile_fields(user, post):
    user.name = post.get("name", "").strip()
    user.organisation = post.get("organisation", "").strip()
    user.save(update_fields=["name", "organisation"])


def _is_semester_developer(user, semester):
    """True if the user has effort_available > 0 for this semester."""
    from apps.planning.models import SemesterDeveloper
    return SemesterDeveloper.objects.filter(
        developer__user=user, semester=semester, effort_available__gt=0,
    ).exists()


def _is_semester_observer(user, semester):
    """True if the user has a SemesterObserver record for this semester."""
    from apps.planning.models import SemesterObserver
    return SemesterObserver.objects.filter(user=user, semester=semester).exists()


class RoleRequiredMixin(LoginRequiredMixin):
    """Restrict access to users whose role is in ``allowed_roles``."""

    allowed_roles: tuple[str, ...] = ()

    def dispatch(self, request, *args, **kwargs):
        if request.user.is_authenticated:
            role = request.user.role
            if not (role in self.allowed_roles or request.user.is_superuser):
                raise PermissionDenied
        return super().dispatch(request, *args, **kwargs)


class PMOrDeveloperMixin(LoginRequiredMixin):
    """PM always allowed; others allowed only if semester developer."""

    def dispatch(self, request, *args, **kwargs):
        if not request.user.is_authenticated:
            return super().dispatch(request, *args, **kwargs)
        if request.user.is_superuser or request.user.role == Role.PM:
            return super().dispatch(request, *args, **kwargs)
        from apps.planning.views._semester import get_selected_semester
        semester = get_selected_semester(request)
        if not _is_semester_developer(request.user, semester):
            raise PermissionDenied
        return super().dispatch(request, *args, **kwargs)


class PMOrObserverMixin(LoginRequiredMixin):
    """PM always allowed; others allowed only if semester observer."""

    def dispatch(self, request, *args, **kwargs):
        if not request.user.is_authenticated:
            return super().dispatch(request, *args, **kwargs)
        if request.user.is_superuser or request.user.role == Role.PM:
            return super().dispatch(request, *args, **kwargs)
        from apps.planning.views._semester import get_selected_semester
        semester = get_selected_semester(request)
        if not _is_semester_observer(request.user, semester):
            raise PermissionDenied
        return super().dispatch(request, *args, **kwargs)


class PMOrParticipantMixin(LoginRequiredMixin):
    """PM always allowed; others allowed if semester developer OR observer."""

    def dispatch(self, request, *args, **kwargs):
        if not request.user.is_authenticated:
            return super().dispatch(request, *args, **kwargs)
        if request.user.is_superuser or request.user.role == Role.PM:
            return super().dispatch(request, *args, **kwargs)
        from apps.planning.views._semester import get_selected_semester
        semester = get_selected_semester(request)
        if not (_is_semester_developer(request.user, semester)
                or _is_semester_observer(request.user, semester)):
            raise PermissionDenied
        return super().dispatch(request, *args, **kwargs)
