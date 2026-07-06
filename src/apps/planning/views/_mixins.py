from django.contrib.auth.mixins import LoginRequiredMixin
from django.core.exceptions import PermissionDenied
from django.http import HttpResponse
from django.shortcuts import redirect
from django.shortcuts import resolve_url
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


def _redirect_or_hx_redirect(request, url, status=204):
    resolved_url = resolve_url(url)
    if request.headers.get("HX-Request") == "true":
        response = HttpResponse(status=status)
        response["HX-Redirect"] = resolved_url
        return response
    return redirect(resolved_url)


def _has_developer_profile(user):
    """True if the user has a DeveloperProfile (semester-independent)."""
    from apps.planning.models import DeveloperProfile

    return DeveloperProfile.objects.filter(user=user).exists()


def _is_semester_developer(user, semester):
    """True if the user has effort_available > 0 for this semester, or is dev lead on any project in this semester."""
    from apps.planning.models import Project
    from apps.planning.models import SemesterDeveloper

    return (
        SemesterDeveloper.objects.filter(
            developer__user=user,
            semester=semester,
            effort_available__gt=0,
        ).exists()
        or Project.objects.filter(
            semester=semester,
            dev_lead__user=user,
        ).exists()
    )


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
    - Existing row with all_project_access or all_stream_access flag set means unrestricted.
    - Otherwise visibility is union of:
        - explicit project_access entries
        - projects reachable via stream_access entries
        - projects where the user has a phase this semester
        - projects where the user is dev lead or science lead
    - Both access sets empty with no all_* flag means no access (empty set returned).
    """
    from apps.planning.models import Phase
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

    if record.all_project_access or record.all_stream_access:
        return None

    # Explicit direct project access
    direct_ids = set(record.project_access.values_list("pk", flat=True))

    # Stream-based access
    stream_qs = record.stream_access.all()
    via_stream_ids = set()
    if stream_qs.exists():
        via_stream_ids = set(
            Project.objects.filter(streams__in=stream_qs).values_list("pk", flat=True),
        )

    # Team membership: phases in this semester
    phase_project_ids = set(
        Phase.objects.filter(
            developer__user=user,
            semester=semester,
        ).values_list("project_id", flat=True),
    )

    # Team membership: dev lead or science lead (scoped to projects in this semester)
    lead_project_ids = set(
        Project.objects.filter(
            semester=semester,
            dev_lead__user=user,
        ).values_list("pk", flat=True),
    ) | set(
        Project.objects.filter(
            semester=semester,
            science_lead__user=user,
        ).values_list("pk", flat=True),
    )

    return direct_ids | via_stream_ids | phase_project_ids | lead_project_ids


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
