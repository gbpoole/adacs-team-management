from django.contrib.auth import get_user_model
from django.shortcuts import get_object_or_404
from django.shortcuts import redirect
from django.views import View
from django.views.generic import ListView

from apps.planning.models import SemesterDeveloper
from apps.planning.models import SemesterObserver
from apps.planning.models import Tag
from apps.users.models import Role

from ._mixins import PMOrParticipantMixin
from ._mixins import RoleRequiredMixin
from ._mixins import _update_user_profile_fields
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
        semester = get_selected_semester(self.request)
        dev_effort = {
            sd.developer.user_id: sd.effort_available
            for sd in SemesterDeveloper.objects.filter(semester=semester)
                                       .select_related("developer")
        }
        obs_records = list(
            SemesterObserver.objects.filter(semester=semester)
            .prefetch_related("project_access__semester_names", "stream_access")
        )
        for so in obs_records:
            for proj in so.project_access.all():
                proj.display_name = proj.name_for_semester(semester)
        obs_map = {so.user_id: so for so in obs_records}
        for user in ctx["people"]:
            user.semester_effort = dev_effort.get(user.pk)
            user.semester_observer = obs_map.get(user.pk)
        ctx["can_edit"] = self.request.user.role == Role.PM or self.request.user.is_superuser
        ctx["all_tags"] = Tag.objects.all()
        ctx["selected_tags"] = self.request.GET.getlist("tags")
        ctx["semester"] = semester
        return ctx


class PersonUpdateView(RoleRequiredMixin, View):
    allowed_roles = (Role.PM,)

    def post(self, request, pk, *args, **kwargs):
        User = get_user_model()
        user = get_object_or_404(User, pk=pk)
        _update_user_profile_fields(user, request.POST)
        return redirect("planning:people")
