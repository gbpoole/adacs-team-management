from django.contrib import messages
from django.contrib.auth import get_user_model
from django.core.exceptions import ValidationError
from django.http import HttpResponse
from django.shortcuts import get_object_or_404
from django.shortcuts import redirect
from django.views import View
from django.views.generic import ListView

from apps.planning.models import Project
from apps.planning.models import SemesterObserver
from apps.planning.models import Stream
from apps.users.models import Role

from ._mixins import RoleRequiredMixin
from ._semester import get_selected_semester


class ObserversView(RoleRequiredMixin, ListView):
    template_name = "planning/observers.html"
    context_object_name = "observers"
    allowed_roles = (Role.PM,)

    def get_queryset(self):
        semester = get_selected_semester(self.request)
        return (
            SemesterObserver.objects.filter(semester=semester)
            .select_related("user")
            .prefetch_related("project_access", "stream_access")
            .order_by("user__name", "user__email")
        )

    def get_context_data(self, **kwargs):
        ctx = super().get_context_data(**kwargs)
        semester = get_selected_semester(self.request)
        ctx["semester"] = semester
        all_projects = list(Project.objects.prefetch_related("semester_names").all())
        for p in all_projects:
            p.display_name = p.name_for_semester(semester)
        ctx["all_projects"] = all_projects
        ctx["all_streams"] = list(Stream.objects.order_by("name"))
        existing_user_pks = set(
            SemesterObserver.objects.filter(semester=semester).values_list("user_id", flat=True)
        )
        User = get_user_model()
        ctx["available_users"] = list(
            User.objects.exclude(pk__in=existing_user_pks).order_by("name", "email")
        )
        project_map = {p.pk: p for p in all_projects}
        stream_map = {s.pk: s for s in ctx["all_streams"]}
        for obs in ctx["observers"]:
            obs.project_pills = [
                (project_map[p.pk].display_name, project_map[p.pk].colour)
                if p.pk in project_map else (str(p), "")
                for p in obs.project_access.all()
            ]
            obs.stream_pills = [
                (stream_map[s.pk].name, stream_map[s.pk].colour)
                if s.pk in stream_map else (str(s), "")
                for s in obs.stream_access.all()
            ]
        return ctx


class ObserverCreateView(RoleRequiredMixin, View):
    allowed_roles = (Role.PM,)

    def post(self, request, *args, **kwargs):
        User = get_user_model()
        user_pk = request.POST.get("user", "").strip()
        if not user_pk:
            return redirect("planning:observers")
        try:
            user = User.objects.get(pk=user_pk)
        except (User.DoesNotExist, ValueError):
            return redirect("planning:observers")
        semester = get_selected_semester(request)
        obs, _ = SemesterObserver.objects.get_or_create(user=user, semester=semester)
        try:
            obs.full_clean()
        except ValidationError as e:
            messages.error(request, " ".join(e.messages))
            return redirect("planning:observers")
        obs.project_access.set(request.POST.getlist("project_access"))
        obs.stream_access.set(request.POST.getlist("stream_access"))
        return redirect("planning:observers")


class ObserverUpdateView(RoleRequiredMixin, View):
    allowed_roles = (Role.PM,)

    def post(self, request, pk, *args, **kwargs):
        obs = get_object_or_404(SemesterObserver, pk=pk)
        obs.project_access.set(request.POST.getlist("project_access"))
        obs.stream_access.set(request.POST.getlist("stream_access"))
        return redirect("planning:observers")


class ObserverDeleteView(RoleRequiredMixin, View):
    allowed_roles = (Role.PM,)

    def post(self, request, pk, *args, **kwargs):
        obs = get_object_or_404(SemesterObserver, pk=pk)
        obs.project_access.clear()
        obs.stream_access.clear()
        return HttpResponse(status=204)
