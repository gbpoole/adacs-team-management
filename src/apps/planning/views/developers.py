import csv
import io

from django.contrib import messages
from django.contrib.auth import get_user_model
from django.db import transaction
from django.http import HttpResponse
from django.shortcuts import get_object_or_404
from django.shortcuts import redirect
from django.views import View
from django.views.generic import ListView

from apps.planning.models import DeveloperProfile
from apps.planning.models import Phase
from apps.planning.models import Semester
from apps.planning.models import SemesterDeveloper
from apps.planning.models import Tag
from apps.users.models import Role

from ._csv_import import _get_or_create_tags
from ._csv_import import _upload_error
from ._csv_import import _validate_developer_rows
from ._mixins import RoleRequiredMixin
from ._mixins import _update_user_profile_fields


def _upsert_semester_developer(profile, effort_str):
    if not effort_str:
        return
    try:
        effort = float(effort_str)
    except ValueError:
        return
    sd, created = SemesterDeveloper.objects.get_or_create(
        developer=profile,
        semester=Semester.get_current(),
        defaults={"effort_available": effort},
    )
    if not created:
        sd.effort_available = effort
        sd.save(update_fields=["effort_available"])


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
        ctx["can_edit"] = self.request.user.role in (Role.ADMIN, Role.PM) or self.request.user.is_superuser
        ctx["all_tags"] = Tag.objects.all()

        records = SemesterDeveloper.objects.filter(semester=semester).values_list(
            "developer_id", "effort_available",
        )
        effort_map = dict(records)

        phases = Phase.objects.filter(
            semester=semester,
        ).select_related("developer").prefetch_related("developer__leave_periods")
        effort_allocated = {}
        for phase in phases:
            effort_allocated[phase.developer_id] = (
                effort_allocated.get(phase.developer_id, 0) + phase.effort_weeks()
            )

        for dev in ctx["developers"]:
            dev.effort_available = effort_map.get(dev.pk)
            dev.effort_allocated = round(effort_allocated.get(dev.pk, 0), 2)
        return ctx


class DeveloperCreateView(RoleRequiredMixin, View):
    allowed_roles = (Role.ADMIN, Role.PM)

    def post(self, request, *args, **kwargs):
        User = get_user_model()
        email = request.POST.get("email", "").strip()
        if not email:
            return redirect("planning:developers")
        user, _ = User.objects.get_or_create(
            email=email,
            defaults={
                "name": request.POST.get("name", "").strip(),
                "role": Role.DEVELOPER,
                "organisation": request.POST.get("organisation", "").strip(),
                "emoji": request.POST.get("emoji", "").strip(),
            },
        )
        profile, _ = DeveloperProfile.objects.get_or_create(user=user)
        tag_names = request.POST.getlist("tags")
        if tag_names:
            profile.tags.set(_get_or_create_tags(tag_names))
        _upsert_semester_developer(profile, request.POST.get("effort_available", "").strip())
        return redirect("planning:developers")


class DeveloperUploadView(RoleRequiredMixin, View):
    allowed_roles = (Role.ADMIN, Role.PM)

    def post(self, request, *args, **kwargs):
        f = request.FILES.get("tsv_file")
        if not f:
            return redirect("planning:developers")
        rows = list(csv.DictReader(io.StringIO(f.read().decode("utf-8-sig")), delimiter="\t"))
        errors = _validate_developer_rows(rows)
        if errors:
            return _upload_error(request, "developers", errors)
        User = get_user_model()
        with transaction.atomic():
            for row in rows:
                email = row["email"].strip()
                user, _ = User.objects.get_or_create(
                    email=email,
                    defaults={
                        "name": row.get("name", "").strip(),
                        "role": Role.DEVELOPER,
                        "organisation": row.get("organisation", "").strip(),
                        "emoji": row.get("emoji", "").strip(),
                    },
                )
                profile, _ = DeveloperProfile.objects.get_or_create(user=user)
                tag_names = [t.strip() for t in row.get("tags", "").split(",") if t.strip()]
                if tag_names:
                    profile.tags.set(_get_or_create_tags(tag_names))
                _upsert_semester_developer(profile, row.get("effort_available", "").strip())
        messages.success(request, f"{len(rows)} developer(s) uploaded successfully.")
        return redirect("planning:developers")


class DeveloperUpdateView(RoleRequiredMixin, View):
    allowed_roles = (Role.ADMIN, Role.PM)

    def post(self, request, pk, *args, **kwargs):
        profile = get_object_or_404(DeveloperProfile, pk=pk)
        _update_user_profile_fields(profile.user, request.POST)
        tag_names = request.POST.getlist("tags")
        profile.tags.set(_get_or_create_tags(tag_names))
        _upsert_semester_developer(profile, request.POST.get("effort_available", "").strip())
        return redirect("planning:developers")


class DeveloperDeleteView(RoleRequiredMixin, View):
    allowed_roles = (Role.ADMIN, Role.PM)

    def post(self, request, pk, *args, **kwargs):
        profile = get_object_or_404(DeveloperProfile, pk=pk)
        user = profile.user
        profile.delete()
        user.delete()
        return HttpResponse(status=204)
