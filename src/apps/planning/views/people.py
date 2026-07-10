from django.db.models import Value
from django.db.models.functions import Coalesce
from django.shortcuts import get_object_or_404
from django.shortcuts import redirect
from django.views import View
from django.views.generic import ListView

from apps.planning.models import DeveloperProfile
from apps.planning.models import Project
from apps.planning.models import Stream
from apps.planning.models import Tag
from apps.planning.models import UserProjectAccess
from apps.users.models import Role

from ._csv_import import _get_or_create_streams
from ._csv_import import _get_or_create_tags
from ._mixins import RoleRequiredMixin


class PeopleView(RoleRequiredMixin, ListView):
    allowed_roles = (Role.PM,)
    template_name = "planning/people.html"
    context_object_name = "people"

    def get_queryset(self):
        qs = (
            DeveloperProfile.objects.select_related("user")
            .prefetch_related("tags")
            .annotate(
                sort_name=Coalesce("user__name", "name", Value("")),
                sort_email=Coalesce("user__email", "email", Value("")),
            )
            .order_by("sort_name", "sort_email")
        )
        tag_filter = self.request.GET.getlist("tags")
        if tag_filter:
            qs = qs.filter(tags__name__in=tag_filter).distinct()
        return qs

    def get_context_data(self, **kwargs):
        ctx = super().get_context_data(**kwargs)
        access_records = list(
            UserProjectAccess.objects.prefetch_related(
                "project_access",
                "stream_access",
            ),
        )
        for policy in access_records:
            for proj in policy.project_access.all():
                proj.display_name = proj.name
        by_user = {p.user_id: p for p in access_records if p.user_id}
        by_profile = {
            p.developer_profile_id: p for p in access_records if p.developer_profile_id
        }

        for profile in ctx["people"]:
            profile.access_policy_record = (
                by_user.get(profile.user_id)
                if profile.user_id
                else by_profile.get(profile.pk)
            )

        all_projects = list(Project.objects.all())
        for p in all_projects:
            p.display_name = p.name
        ctx["all_projects"] = all_projects
        ctx["all_streams"] = list(Stream.objects.order_by("name"))
        ctx["can_edit"] = (
            self.request.user.role == Role.PM or self.request.user.is_superuser
        )
        ctx["all_tags"] = Tag.objects.all()
        ctx["selected_tags"] = self.request.GET.getlist("tags")
        return ctx


class PersonUpdateView(RoleRequiredMixin, View):
    allowed_roles = (Role.PM,)

    def post(self, request, pk, *args, **kwargs):
        profile = get_object_or_404(DeveloperProfile, pk=pk)

        effort_str = request.POST.get("base_effort_weeks", "").strip()
        if effort_str:
            try:
                profile.base_effort_weeks = float(effort_str)
                profile.save(update_fields=["base_effort_weeks"])
            except (ValueError, TypeError):
                pass
        tag_names = [
            n for n in request.POST.getlist("tags") if "||" not in n and "\t" not in n
        ]
        profile.tags.set(_get_or_create_tags(tag_names))

        # Access can be set for registered (user-keyed) and unregistered
        # (developer_profile-keyed) people alike; the latter transfers to the
        # user's account when they register.
        owner = (
            {"user_id": profile.user_id}
            if profile.user_id
            else {"developer_profile_id": profile.pk}
        )
        project_pks = request.POST.getlist("project_access")
        stream_names = [
            n
            for n in request.POST.getlist("stream_access")
            if "||" not in n and "\t" not in n
        ]
        streams = _get_or_create_streams(stream_names)
        all_projects = "all_project_access" in request.POST
        all_streams = "all_stream_access" in request.POST
        access = UserProjectAccess.objects.filter(**owner).first()
        if access is not None or project_pks or streams or all_projects or all_streams:
            access, _ = UserProjectAccess.objects.get_or_create(**owner)
            access.project_access.set(project_pks)
            access.stream_access.set(streams)
            access.all_project_access = all_projects
            access.all_stream_access = all_streams
            access.save(update_fields=["all_project_access", "all_stream_access"])

        return redirect("planning:people")
