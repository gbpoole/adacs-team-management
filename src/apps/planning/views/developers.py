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
from apps.planning.models import SemesterDeveloper
from apps.planning.models import Tag
from apps.users.models import Role

from ._csv_import import _get_or_create_tags
from ._csv_import import _upload_error
from ._csv_import import _validate_developer_rows
from ._mixins import PMOrDeveloperMixin
from ._mixins import RoleRequiredMixin
from ._semester import get_selected_semester


def _upsert_semester_developer(profile, effort_str, semester):
    if not effort_str:
        return None, False
    try:
        effort = float(effort_str)
    except ValueError:
        return None, False
    sd, created = SemesterDeveloper.objects.get_or_create(
        developer=profile,
        semester=semester,
        defaults={"effort_available": effort},
    )
    if not created:
        sd.effort_available = effort
        sd.save(update_fields=["effort_available"])
    return sd, created


class DevelopersView(PMOrDeveloperMixin, ListView):
    template_name = "planning/developers.html"
    context_object_name = "developers"

    def get_queryset(self):
        qs = (
            DeveloperProfile.objects.select_related("user")
            .prefetch_related("tags")
            .order_by("user__name", "user__email")
        )
        tag_filter = self.request.GET.getlist("tags")
        if tag_filter:
            semester = get_selected_semester(self.request)
            qs = qs.filter(
                semester_records__semester=semester,
                semester_records__tags__name__in=tag_filter,
            ).distinct()
        return qs

    def get_context_data(self, **kwargs):
        ctx = super().get_context_data(**kwargs)
        semester = get_selected_semester(self.request)
        ctx["semester"] = semester
        ctx["can_edit"] = self.request.user.role == Role.PM or self.request.user.is_superuser
        ctx["all_tags"] = Tag.objects.all()
        ctx["selected_tags"] = self.request.GET.getlist("tags")

        sd_records = list(
            SemesterDeveloper.objects.filter(semester=semester)
            .prefetch_related("tags")
        )
        sd_map = {sd.developer_id: sd for sd in sd_records}

        phases = Phase.objects.filter(
            semester=semester,
        ).select_related("developer").prefetch_related("developer__leave_periods")
        effort_allocated = {}
        for phase in phases:
            effort_allocated[phase.developer_id] = (
                effort_allocated.get(phase.developer_id, 0) + phase.effort_weeks()
            )

        for dev in ctx["developers"]:
            sd = sd_map.get(dev.pk)
            dev.effort_available = sd.effort_available if sd else None
            dev.semester_tags = list(sd.tags.all()) if sd else []
            dev.effort_allocated = round(effort_allocated.get(dev.pk, 0), 2)
            if dev.effort_available is not None:
                dev.effort_unallocated = round(float(dev.effort_available) - dev.effort_allocated, 2)
            else:
                dev.effort_unallocated = None
        return ctx


class DeveloperCreateView(RoleRequiredMixin, View):
    allowed_roles = (Role.PM,)

    def post(self, request, *args, **kwargs):
        User = get_user_model()
        email = request.POST.get("email", "").strip()
        if not email:
            return redirect("planning:developers")
        user, _ = User.objects.get_or_create(
            email=email,
            defaults={
                "name": request.POST.get("name", "").strip(),
                "role": Role.USER,
                "organisation": request.POST.get("organisation", "").strip(),
            },
        )
        profile, _ = DeveloperProfile.objects.get_or_create(user=user)
        tag_names = request.POST.getlist("tags")
        if tag_names:
            profile.tags.set(_get_or_create_tags(tag_names))

        # Default effort to base effort if not provided
        effort_str = request.POST.get("effort_available", "").strip()
        if not effort_str:
            effort_str = str(profile.base_effort_weeks)

        semester = get_selected_semester(request)
        sd, sd_created = _upsert_semester_developer(profile, effort_str, semester)
        # Seed semester tags from base tags when first added to this semester
        if sd is not None and sd_created:
            sd.tags.set(profile.tags.all())
        return redirect("planning:developers")


class DeveloperUploadView(RoleRequiredMixin, View):
    allowed_roles = (Role.PM,)

    def post(self, request, *args, **kwargs):
        f = request.FILES.get("tsv_file")
        if not f:
            return redirect("planning:developers")
        rows = list(csv.DictReader(io.StringIO(f.read().decode("utf-8-sig")), delimiter="\t"))
        errors = _validate_developer_rows(rows)
        if errors:
            return _upload_error(request, "developers", errors)
        User = get_user_model()
        semester = get_selected_semester(request)
        with transaction.atomic():
            for row in rows:
                email = row["email"].strip()
                user, _ = User.objects.get_or_create(
                    email=email,
                    defaults={
                        "name": row.get("name", "").strip(),
                        "role": Role.USER,
                        "organisation": row.get("organisation", "").strip(),
                    },
                )
                profile, _ = DeveloperProfile.objects.get_or_create(user=user)
                tag_names = [t.strip() for t in row.get("tags", "").split(",") if t.strip()]
                if tag_names:
                    profile.tags.set(_get_or_create_tags(tag_names))
                effort_str = row.get("effort_available", "").strip() or str(profile.base_effort_weeks)
                sd, sd_created = _upsert_semester_developer(profile, effort_str, semester)
                if sd is not None and sd_created:
                    sd.tags.set(profile.tags.all())
        messages.success(request, f"{len(rows)} developer(s) uploaded successfully.")
        return redirect("planning:developers")


class DeveloperUpdateView(RoleRequiredMixin, View):
    allowed_roles = (Role.PM,)

    def post(self, request, pk, *args, **kwargs):
        profile = get_object_or_404(DeveloperProfile, pk=pk)
        tag_names = request.POST.getlist("tags")
        tags = _get_or_create_tags(tag_names)
        semester = get_selected_semester(request)
        # Update semester-specific tags
        try:
            sd = SemesterDeveloper.objects.get(developer=profile, semester=semester)
            sd.tags.set(tags)
        except SemesterDeveloper.DoesNotExist:
            pass
        # Optionally also update base tags
        if request.POST.get("update_base_tags"):
            profile.tags.set(tags)
        _upsert_semester_developer(
            profile, request.POST.get("effort_available", "").strip(),
            semester,
        )
        return redirect("planning:developers")


class DeveloperDeleteView(RoleRequiredMixin, View):
    allowed_roles = (Role.PM,)

    def post(self, request, pk, *args, **kwargs):
        profile = get_object_or_404(DeveloperProfile, pk=pk)
        user = profile.user
        profile.delete()
        user.delete()
        return HttpResponse(status=204)
