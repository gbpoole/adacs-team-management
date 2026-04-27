import csv
import io
import json

from django.contrib.auth import get_user_model
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


class DevelopersView(RoleRequiredMixin, ListView):
    allowed_roles = (Role.PM,)
    template_name = "planning/developers.html"
    context_object_name = "developers"

    def get_queryset(self):
        semester = get_selected_semester(self.request)
        qs = (
            DeveloperProfile.objects.select_related("user")
            .prefetch_related("tags")
            .filter(semester_records__semester=semester)
            .order_by("user__name", "user__email")
        )
        tag_filter = self.request.GET.getlist("tags")
        if tag_filter:
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
            .prefetch_related("tags"),
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

        # For add-developer modal: all users not yet in this semester as developers
        all_dev_pks_in_sem = set(sd_map.keys())
        user_pks_in_sem = set(
            SemesterDeveloper.objects.filter(semester=semester)
            .values_list("developer__user_id", flat=True),
        )
        User = get_user_model()
        ctx["available_users"] = list(
            User.objects.exclude(pk__in=user_pks_in_sem)
            .select_related("developer_profile")
            .order_by("name", "email"),
        )

        # For migrate modal: other semesters and their exclusive developers
        other_semesters = list(
            Semester.objects.exclude(pk=semester.pk)
            .order_by("-year", "-semester_type"),
        )
        migrate_map = {}
        for sem in other_semesters:
            devs = list(
                DeveloperProfile.objects.filter(semester_records__semester=sem)
                .exclude(pk__in=all_dev_pks_in_sem)
                .select_related("user")
                .prefetch_related("tags"),
            )
            migrate_map[str(sem.pk)] = [
                {
                    "pk": d.pk,
                    "name": d.user.name or d.user.email,
                    "email": d.user.email,
                    "tags": [t.name for t in d.tags.all()],
                }
                for d in devs
            ]
        ctx["migrate_semesters"] = other_semesters
        ctx["migrate_data_json"] = json.dumps(migrate_map)
        return ctx


class DeveloperCreateView(RoleRequiredMixin, View):
    allowed_roles = (Role.PM,)

    def post(self, request, *args, **kwargs):
        User = get_user_model()
        pks = request.POST.getlist("user_pks")
        semester = get_selected_semester(request)
        for pk_str in pks:
            try:
                user = User.objects.get(pk=int(pk_str))
            except (User.DoesNotExist, ValueError):
                continue
            profile, profile_created = DeveloperProfile.objects.get_or_create(user=user)
            effort_str = request.POST.get(f"effort_{user.pk}", "").strip()
            if not effort_str:
                effort_str = str(profile.base_effort_weeks)
            # Update base effort if newly created or explicitly requested
            if profile_created or request.POST.get(f"update_base_{user.pk}"):
                try:
                    profile.base_effort_weeks = float(effort_str)
                    profile.save(update_fields=["base_effort_weeks"])
                except (ValueError, TypeError):
                    pass
            sd, sd_created = _upsert_semester_developer(profile, effort_str, semester)
            if sd is not None and sd_created:
                sd.tags.set(profile.tags.all())
        return redirect("planning:developers")


class DeveloperDownloadView(RoleRequiredMixin, View):
    allowed_roles = (Role.PM,)

    def get(self, request, *args, **kwargs):
        semester = get_selected_semester(request)
        sd_records = (
            SemesterDeveloper.objects.filter(semester=semester)
            .select_related("developer__user")
            .prefetch_related("tags")
            .order_by("developer__user__name", "developer__user__email")
        )
        output = io.StringIO()
        writer = csv.writer(output, delimiter="\t")
        writer.writerow(["email", "name", "organisation", "effort_available", "tags"])
        for sd in sd_records:
            user = sd.developer.user
            tags = "||".join(t.name for t in sd.tags.all())
            writer.writerow([
                user.email,
                user.name or "",
                user.organisation or "",
                sd.effort_available,
                tags,
            ])
        response = HttpResponse(
            output.getvalue(), content_type="application/octet-stream",
        )
        response["Content-Disposition"] = (
            f'attachment; filename="developers_{semester}.tsv"'
        )
        return response


class DeveloperMigrateView(RoleRequiredMixin, View):
    allowed_roles = (Role.PM,)

    def post(self, request, *args, **kwargs):
        pks = request.POST.getlist("profile_pks")
        semester = get_selected_semester(request)
        for pk_str in pks:
            try:
                profile = DeveloperProfile.objects.get(pk=int(pk_str))
            except (DeveloperProfile.DoesNotExist, ValueError):
                continue
            effort_str = str(profile.base_effort_weeks)
            sd, sd_created = _upsert_semester_developer(profile, effort_str, semester)
            if sd is not None and sd_created:
                sd.tags.set(profile.tags.all())
        return redirect("planning:developers")


# NOTE: This view updates semester-specific developer properties only (effort, tags).
# User identity fields (name, email, organisation) are managed via PersonUpdateView.
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
        semester = get_selected_semester(request)
        SemesterDeveloper.objects.filter(developer=profile, semester=semester).delete()
        return HttpResponse(status=204)
