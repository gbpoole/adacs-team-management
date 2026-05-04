from django.contrib import messages
from django.contrib.auth import get_user_model
from django.http import HttpResponse
from django.shortcuts import get_object_or_404
from django.shortcuts import redirect
from django.views import View
from django.views.generic import ListView

from apps.planning.models import Project
from apps.planning.models import SemesterDeveloper
from apps.planning.models import Stream
from apps.planning.models import UserProjectAccess
from apps.users.models import Role

from ._mixins import RoleRequiredMixin
from ._semester import get_selected_semester


class ObserversView(RoleRequiredMixin, ListView):
    template_name = "planning/observers.html"
    context_object_name = "observers"
    allowed_roles = (Role.PM,)

    def get_queryset(self):
        semester = get_selected_semester(self.request)
        developer_user_ids = SemesterDeveloper.objects.filter(
            semester=semester,
            effort_available__gt=0,
        ).values_list("developer__user_id", flat=True)
        return (
            UserProjectAccess.objects.all()
            .exclude(user_id__in=developer_user_ids)
            .select_related("user")
            .prefetch_related("project_access", "stream_access")
            .order_by("user__name", "user__email")
        )

    def get_context_data(self, **kwargs):
        ctx = super().get_context_data(**kwargs)
        semester = get_selected_semester(self.request)
        ctx["semester"] = semester
        all_projects = list(Project.objects.all())
        for p in all_projects:
            p.display_name = p.name
        ctx["all_projects"] = all_projects
        ctx["all_streams"] = list(Stream.objects.order_by("name"))
        observer_pks = set(UserProjectAccess.objects.values_list("user_id", flat=True))
        developer_pks = set(
            SemesterDeveloper.objects.filter(
                semester=semester,
                effort_available__gt=0,
            ).values_list("developer__user_id", flat=True),
        )
        dev_lead_pks = set(
            Project.objects.filter(
                semester=semester,
                dev_lead__isnull=False,
            ).values_list("dev_lead_id", flat=True),
        )
        excluded_pks = observer_pks | developer_pks | dev_lead_pks
        User = get_user_model()
        ctx["available_users"] = list(
            User.objects.exclude(pk__in=excluded_pks).order_by("name", "email"),
        )
        project_map = {p.pk: p for p in all_projects}
        stream_map = {s.pk: s for s in ctx["all_streams"]}
        for obs in ctx["observers"]:
            obs.project_pills = [
                (project_map[p.pk].display_name, project_map[p.pk].colour)
                if p.pk in project_map
                else (str(p), "")
                for p in obs.project_access.all()
            ]
            obs.stream_pills = [
                (stream_map[s.pk].name, stream_map[s.pk].colour)
                if s.pk in stream_map
                else (str(s), "")
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
        # Observer management is only for non-developer users in the selected semester.
        if SemesterDeveloper.objects.filter(
            developer__user=user,
            semester=semester,
            effort_available__gt=0,
        ).exists():
            messages.error(
                request,
                f"Cannot assign observer access — {user} is a developer in {semester}.",
            )
            return redirect("planning:observers")
        obs, _ = UserProjectAccess.objects.get_or_create(user=user)
        obs.project_access.set(request.POST.getlist("project_access"))
        obs.stream_access.set(request.POST.getlist("stream_access"))
        obs.all_project_access = "all_project_access" in request.POST
        obs.all_stream_access = "all_stream_access" in request.POST
        obs.save(update_fields=["all_project_access", "all_stream_access"])
        return redirect("planning:observers")


class ObserverUpdateView(RoleRequiredMixin, View):
    allowed_roles = (Role.PM,)

    def post(self, request, pk, *args, **kwargs):
        obs = get_object_or_404(UserProjectAccess, pk=pk)
        obs.project_access.set(request.POST.getlist("project_access"))
        obs.stream_access.set(request.POST.getlist("stream_access"))
        obs.all_project_access = "all_project_access" in request.POST
        obs.all_stream_access = "all_stream_access" in request.POST
        obs.save(update_fields=["all_project_access", "all_stream_access"])
        return redirect("planning:observers")


# NOTE: This clears all project and stream access for the user
# but does NOT delete the access record or the User account.
class ObserverDeleteView(RoleRequiredMixin, View):
    allowed_roles = (Role.PM,)

    def post(self, request, pk, *args, **kwargs):
        obs = get_object_or_404(UserProjectAccess, pk=pk)
        obs.project_access.clear()
        obs.stream_access.clear()
        obs.all_project_access = False
        obs.all_stream_access = False
        obs.save(update_fields=["all_project_access", "all_stream_access"])
        return HttpResponse(status=204)
