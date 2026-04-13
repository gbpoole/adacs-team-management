from django.contrib.auth import get_user_model
from django.core.exceptions import ValidationError
from django.shortcuts import get_object_or_404
from django.shortcuts import redirect
from django.views import View
from django.views.generic import ListView

from apps.planning.models import DeveloperProfile
from apps.planning.models import Project
from apps.planning.models import SemesterDeveloper
from apps.planning.models import SemesterObserver
from apps.planning.models import Stream
from apps.planning.models import Tag
from apps.users.models import Role

from ._mixins import PMOrParticipantMixin
from ._mixins import RoleRequiredMixin
from ._semester import get_selected_semester


class PeopleView(PMOrParticipantMixin, ListView):
    template_name = "planning/people.html"
    context_object_name = "people"

    def get_queryset(self):
        User = get_user_model()
        qs = (
            User.objects.select_related("developer_profile")
            .prefetch_related("developer_profile__tags")
            .order_by("name", "email")
        )
        tag_filter = self.request.GET.getlist("tags")
        if tag_filter:
            qs = qs.filter(developer_profile__tags__name__in=tag_filter).distinct()
        return qs

    def get_context_data(self, **kwargs):
        ctx = super().get_context_data(**kwargs)
        highlighted = get_selected_semester(self.request)

        # Observer records for the highlighted semester
        obs_records = list(
            SemesterObserver.objects.filter(semester=highlighted)
            .prefetch_related("project_access__semester_names", "stream_access")
        )
        for so in obs_records:
            for proj in so.project_access.all():
                proj.display_name = proj.name_for_semester(highlighted)
        obs_map = {so.user_id: so for so in obs_records}

        # Sets of user PKs for icon flags (selected semester only)
        dev_pks = set(
            SemesterDeveloper.objects.filter(semester=highlighted)
            .values_list("developer__user_id", flat=True)
        )
        obs_pks = set(
            SemesterObserver.objects.filter(semester=highlighted)
            .values_list("user_id", flat=True)
        )

        for user in ctx["people"]:
            user.semester_observer = obs_map.get(user.pk)
            user.icon_dev = user.pk in dev_pks
            user.icon_obs = user.pk in obs_pks
            user.icon_pm = user.role == Role.PM or user.is_superuser

        all_projects = list(Project.objects.prefetch_related("semester_names").all())
        for p in all_projects:
            p.display_name = p.name_for_semester(highlighted)
        ctx["all_projects"] = all_projects
        ctx["all_streams"] = list(Stream.objects.order_by("name"))
        ctx["can_edit"] = self.request.user.role == Role.PM or self.request.user.is_superuser
        ctx["all_tags"] = Tag.objects.all()
        ctx["selected_tags"] = self.request.GET.getlist("tags")
        ctx["highlighted_semester"] = highlighted
        return ctx


class PersonUpdateView(RoleRequiredMixin, View):
    allowed_roles = (Role.PM,)

    def post(self, request, pk, *args, **kwargs):
        User = get_user_model()
        user = get_object_or_404(User, pk=pk)

        profile, _ = DeveloperProfile.objects.get_or_create(user=user)
        effort_str = request.POST.get("base_effort_weeks", "").strip()
        if effort_str:
            profile.base_effort_weeks = effort_str
            profile.save(update_fields=["base_effort_weeks"])
        profile.tags.set(request.POST.getlist("tags"))

        semester = get_selected_semester(request)
        try:
            obs, _ = SemesterObserver.objects.get_or_create(user=user, semester=semester)
            obs.full_clean()
            obs.project_access.set(request.POST.getlist("project_access"))
            obs.stream_access.set(request.POST.getlist("stream_access"))
        except ValidationError:
            pass

        return redirect("planning:people")
