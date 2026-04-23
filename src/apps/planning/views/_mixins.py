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


def _has_developer_profile(user):
    """True if the user has a DeveloperProfile (semester-independent)."""
    from apps.planning.models import DeveloperProfile

    return DeveloperProfile.objects.filter(user=user).exists()


def _is_semester_developer(user, semester):
    """True if the user has effort_available > 0 for this semester."""
    from apps.planning.models import SemesterDeveloper

    return SemesterDeveloper.objects.filter(
        developer__user=user,
        semester=semester,
        effort_available__gt=0,
    ).exists()


def _has_project_access_policy(user):
    """True when a user has an explicit global access policy row."""
    from apps.planning.models import UserProjectAccess

    return UserProjectAccess.objects.filter(user=user).exists()


def _has_restricted_view_access(user, semester):
    """True when a non-developer user has explicit global access restrictions."""
    if _is_semester_developer(user, semester):
        return False
    return _has_project_access_policy(user)


def _is_semester_observer(user, semester):
    """Compatibility helper for observer-style access checks.

    Returns true when the user is not a selected-semester developer and has
    an explicit global project-access policy.
    """

    return _has_restricted_view_access(user, semester)


def _visible_project_ids_for_user(user, semester):
    """Return visible project IDs for a user in a semester.

    - ``None`` means unrestricted visibility.
    - A set of IDs means visibility is restricted to that set (possibly empty).

    Restriction semantics:
    - PM and superusers are unrestricted.
    - Missing UserProjectAccess row means unrestricted.
    - Existing row with both project_access and stream_access empty means unrestricted.
    - Otherwise visibility is union(project_access, projects in stream_access).
    """
    from apps.planning.models import Project
    from apps.planning.models import UserProjectAccess

    if user.is_superuser or user.role == Role.PM:
        return None

    record = (
        UserProjectAccess.objects.filter(user=user)
        .prefetch_related(
            "project_access",
            "stream_access",
        )
        .first()
    )
    if record is None:
        return None

    direct_ids = set(record.project_access.values_list("pk", flat=True))
    stream_qs = record.stream_access.all()
    stream_ids = set(stream_qs.values_list("pk", flat=True))
    if not direct_ids and not stream_ids:
        return None

    via_stream_ids = set()
    if stream_ids:
        via_stream_ids = set(
            Project.objects.filter(streams__in=stream_qs).values_list("pk", flat=True),
        )
    return direct_ids | via_stream_ids


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


class PMOrHasDeveloperProfileMixin(LoginRequiredMixin):
    """PM/superuser always allowed; others allowed if they have a DeveloperProfile."""

    def dispatch(self, request, *args, **kwargs):
        if not request.user.is_authenticated:
            return super().dispatch(request, *args, **kwargs)
        if request.user.is_superuser or request.user.role == Role.PM:
            return super().dispatch(request, *args, **kwargs)
        if not _has_developer_profile(request.user):
            raise PermissionDenied
        return super().dispatch(request, *args, **kwargs)


class PMOrObserverMixin(LoginRequiredMixin):
    """PM always allowed; others allowed only with observer-style access."""

    def dispatch(self, request, *args, **kwargs):
        if not request.user.is_authenticated:
            return super().dispatch(request, *args, **kwargs)
        if request.user.is_superuser or request.user.role == Role.PM:
            return super().dispatch(request, *args, **kwargs)
        from apps.planning.views._semester import get_selected_semester

        semester = get_selected_semester(request)
        if not _has_restricted_view_access(request.user, semester):
            raise PermissionDenied
        return super().dispatch(request, *args, **kwargs)


class PMOrParticipantMixin(LoginRequiredMixin):
    """PM always allowed; others allowed if semester developer or observer-style."""

    def dispatch(self, request, *args, **kwargs):
        if not request.user.is_authenticated:
            return super().dispatch(request, *args, **kwargs)
        if request.user.is_superuser or request.user.role == Role.PM:
            return super().dispatch(request, *args, **kwargs)
        from apps.planning.views._semester import get_selected_semester

        semester = get_selected_semester(request)
        if not (
            _is_semester_developer(request.user, semester)
            or _has_restricted_view_access(request.user, semester)
        ):
            raise PermissionDenied
        return super().dispatch(request, *args, **kwargs)
