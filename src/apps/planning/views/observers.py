from django.contrib.auth import get_user_model
from django.http import HttpResponse
from django.shortcuts import get_object_or_404
from django.shortcuts import redirect
from django.views import View
from django.views.generic import ListView

from apps.planning.models import ObserverProfile
from apps.planning.models import Project
from apps.planning.models import Semester
from apps.users.models import Role

from ._mixins import RoleRequiredMixin
from ._mixins import _update_user_profile_fields


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

    def get_context_data(self, **kwargs):
        ctx = super().get_context_data(**kwargs)
        semester = Semester.get_current()
        ctx["semester"] = semester
        all_projects = list(Project.objects.prefetch_related("semester_names").all())
        for p in all_projects:
            p.display_name = p.name_for_semester(semester)
        ctx["all_projects"] = all_projects
        project_map = {p.pk: p for p in all_projects}
        for obs in ctx["observers"]:
            obs.project_pills = [
                (project_map[p.pk].display_name, project_map[p.pk].colour)
                if p.pk in project_map else (str(p), "")
                for p in obs.project_access.all()
            ]
        return ctx


class ObserverCreateView(RoleRequiredMixin, View):
    allowed_roles = (Role.ADMIN, Role.PM)

    def post(self, request, *args, **kwargs):
        User = get_user_model()
        email = request.POST.get("email", "").strip()
        if not email:
            return redirect("planning:observers")
        user, _ = User.objects.get_or_create(
            email=email,
            defaults={
                "name": request.POST.get("name", "").strip(),
                "role": Role.OBSERVER,
                "organisation": request.POST.get("organisation", "").strip(),
                "emoji": request.POST.get("emoji", "").strip(),
            },
        )
        obs, _ = ObserverProfile.objects.get_or_create(user=user)
        project_pks = request.POST.getlist("project_access")
        if project_pks:
            obs.project_access.set(project_pks)
        return redirect("planning:observers")


class ObserverUpdateView(RoleRequiredMixin, View):
    allowed_roles = (Role.ADMIN, Role.PM)

    def post(self, request, pk, *args, **kwargs):
        profile = get_object_or_404(ObserverProfile, pk=pk)
        _update_user_profile_fields(profile.user, request.POST)
        project_pks = request.POST.getlist("project_access")
        profile.project_access.set(project_pks)
        return redirect("planning:observers")


class ObserverDeleteView(RoleRequiredMixin, View):
    allowed_roles = (Role.ADMIN, Role.PM)

    def post(self, request, pk, *args, **kwargs):
        profile = get_object_or_404(ObserverProfile, pk=pk)
        user = profile.user
        profile.delete()
        user.delete()
        return HttpResponse(status=204)
