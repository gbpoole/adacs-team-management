from django.contrib.auth.mixins import LoginRequiredMixin
from django.core.exceptions import PermissionDenied
from django.views.generic import ListView

from apps.users.models import Role

from .models import DeveloperProfile
from .models import ObserverProfile
from .models import Project
from .models import Semester
from .models import SemesterDeveloper


class RoleRequiredMixin(LoginRequiredMixin):
    """Restrict access to users whose role is in ``allowed_roles``."""

    allowed_roles: tuple[str, ...] = ()

    def dispatch(self, request, *args, **kwargs):
        response = super().dispatch(request, *args, **kwargs)
        if request.user.is_authenticated:
            role = request.user.role
            if not (role in self.allowed_roles or request.user.is_superuser):
                raise PermissionDenied
        return response


# ---------------------------------------------------------------------------
# Developers page  (FR-10)
# ---------------------------------------------------------------------------


class DevelopersView(RoleRequiredMixin, ListView):
    template_name = "planning/developers.html"
    context_object_name = "developers"
    allowed_roles = (Role.ADMIN, Role.PM, Role.DEVELOPER)

    def get_queryset(self):
        return (
            DeveloperProfile.objects.select_related("user")
            .prefetch_related("tags")
            .order_by("user__name", "user__email")
        )

    def get_context_data(self, **kwargs):
        ctx = super().get_context_data(**kwargs)
        semester = Semester.get_current()
        ctx["semester"] = semester
        ctx["can_edit"] = self.request.user.role in (Role.ADMIN, Role.PM)

        # Attach effort_available and effort_allocated to each dev in-place.
        # effort_allocated comes from Phase (FR-15); default 0 until implemented.
        records = SemesterDeveloper.objects.filter(semester=semester).values_list(
            "developer_id", "effort_available",
        )
        effort_map = dict(records)
        for dev in ctx["developers"]:
            dev.effort_available = effort_map.get(dev.pk)
            dev.effort_allocated = 0  # placeholder until Phase (FR-15)
        return ctx


# ---------------------------------------------------------------------------
# Observers page  (FR-11)
# ---------------------------------------------------------------------------


class ObserversView(RoleRequiredMixin, ListView):
    template_name = "planning/observers.html"
    context_object_name = "observers"
    allowed_roles = (Role.ADMIN, Role.PM)

    def get_queryset(self):
        return (
            ObserverProfile.objects.select_related("user")
            .prefetch_related("project_access")
            .order_by("user__name", "user__email")
        )


# ---------------------------------------------------------------------------
# Projects page  (FR-12)
# ---------------------------------------------------------------------------


class ProjectsView(RoleRequiredMixin, ListView):
    template_name = "planning/projects.html"
    context_object_name = "projects"
    allowed_roles = (Role.ADMIN, Role.PM, Role.DEVELOPER, Role.OBSERVER)

    def get_queryset(self):
        qs = Project.objects.prefetch_related("tags", "semester_names").select_related(
            "stream",
        )
        user = self.request.user
        if user.role == Role.OBSERVER:
            try:
                profile = user.observer_profile
                qs = qs.filter(observer_access=profile)
            except ObserverProfile.DoesNotExist:
                qs = qs.none()
        return qs.order_by("id")

    def get_context_data(self, **kwargs):
        ctx = super().get_context_data(**kwargs)
        semester = Semester.get_current()
        ctx["semester"] = semester
        # Attach the semester-specific name to each project object.
        for project in ctx["projects"]:
            project.display_name = project.name_for_semester(semester)
        return ctx
