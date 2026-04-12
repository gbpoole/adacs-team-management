import csv
import io

from django.contrib import messages
from django.db import transaction
from django.http import HttpResponse
from django.shortcuts import get_object_or_404
from django.shortcuts import redirect
from django.views import View
from django.views.generic import ListView

from apps.planning.models import ObserverProfile
from apps.planning.models import Phase
from apps.planning.models import Project
from apps.planning.models import ProjectAllocation
from apps.planning.models import ProjectSemesterName
from apps.planning.models import Semester
from apps.planning.models import Stream
from apps.planning.models import Tag
from apps.users.models import Role

from ._csv_import import _get_or_create_streams
from ._csv_import import _get_or_create_tags
from ._csv_import import _upload_error
from ._csv_import import _validate_project_rows
from ._mixins import RoleRequiredMixin


class ProjectsView(RoleRequiredMixin, ListView):
    template_name = "planning/projects.html"
    context_object_name = "projects"
    allowed_roles = (Role.PM, Role.DEVELOPER, Role.OBSERVER)

    def get_queryset(self):
        qs = Project.objects.prefetch_related("tags", "streams", "semester_names")
        user = self.request.user
        if user.role == Role.OBSERVER:
            try:
                profile = user.observer_profile
                qs = qs.filter(observer_access=profile)
            except ObserverProfile.DoesNotExist:
                qs = qs.none()
        tag_filter = self.request.GET.getlist("tags")
        stream_filter = self.request.GET.getlist("streams")
        if tag_filter:
            qs = qs.filter(tags__name__in=tag_filter).distinct()
        if stream_filter:
            qs = qs.filter(streams__name__in=stream_filter).distinct()
        return qs.order_by("id")

    def get_context_data(self, **kwargs):
        ctx = super().get_context_data(**kwargs)
        semester = Semester.get_current()
        ctx["semester"] = semester
        ctx["can_edit"] = self.request.user.role == Role.PM or self.request.user.is_superuser
        ctx["all_tags"] = Tag.objects.all()
        ctx["streams"] = Stream.objects.order_by("name")
        ctx["selected_tags"] = self.request.GET.getlist("tags")
        ctx["selected_streams"] = self.request.GET.getlist("streams")

        resourced_map = {
            pk: float(new + carryover)
            for pk, new, carryover in ProjectAllocation.objects.filter(semester=semester)
            .values_list("project_id", "weeks_new", "weeks_carryover")
        }
        allocated_map: dict = {}
        for phase in Phase.objects.filter(semester=semester).select_related("developer").prefetch_related("developer__leave_periods"):
            allocated_map[phase.project_id] = allocated_map.get(phase.project_id, 0) + phase.effort_weeks()

        for project in ctx["projects"]:
            project.display_name = project.name_for_semester(semester)
            project.effort_resourced = resourced_map.get(project.pk, 0)
            project.effort_allocated = round(allocated_map.get(project.pk, 0), 2)
            project.effort_discrepancy = round(project.effort_resourced - project.effort_allocated, 2)
        return ctx


class ProjectCreateView(RoleRequiredMixin, View):
    allowed_roles = (Role.PM,)

    def post(self, request, *args, **kwargs):
        name = request.POST.get("name", "").strip()
        if not name:
            return redirect("planning:projects")
        semester = Semester.get_current()
        project = Project()
        project.save()
        ProjectSemesterName.objects.create(project=project, semester=semester, name=name)
        stream_names = request.POST.getlist("streams")
        project.streams.set(_get_or_create_streams(stream_names))
        tag_names = request.POST.getlist("tags")
        if tag_names:
            project.tags.set(_get_or_create_tags(tag_names))
        effort_str = request.POST.get("effort_resourced", "").strip()
        weeks = float(effort_str) if effort_str else 0
        ProjectAllocation.objects.create(
            project=project, semester=semester,
            weeks_new=weeks, weeks_carryover=0,
        )
        return redirect("planning:projects")


class ProjectUploadView(RoleRequiredMixin, View):
    allowed_roles = (Role.PM,)

    def post(self, request, *args, **kwargs):
        f = request.FILES.get("tsv_file")
        if not f:
            return redirect("planning:projects")
        rows = list(csv.DictReader(io.StringIO(f.read().decode("utf-8-sig")), delimiter="\t"))
        errors = _validate_project_rows(rows)
        if errors:
            return _upload_error(request, "projects", errors)
        semester = Semester.get_current()
        with transaction.atomic():
            for row in rows:
                name = row["name"].strip()
                project = Project()
                project.save()
                ProjectSemesterName.objects.create(project=project, semester=semester, name=name)
                stream_names = [s.strip() for s in row.get("streams", "").split(",") if s.strip()]
                project.streams.set(_get_or_create_streams(stream_names))
                tag_names = [t.strip() for t in row.get("tags", "").split(",") if t.strip()]
                if tag_names:
                    project.tags.set(_get_or_create_tags(tag_names))
                effort_str = row.get("effort_resourced", "").strip()
                weeks = float(effort_str) if effort_str else 0
                ProjectAllocation.objects.create(
                    project=project, semester=semester,
                    weeks_new=weeks, weeks_carryover=0,
                )
        messages.success(request, f"{len(rows)} project(s) uploaded successfully.")
        return redirect("planning:projects")


class ProjectUpdateView(RoleRequiredMixin, View):
    allowed_roles = (Role.PM,)

    def post(self, request, pk, *args, **kwargs):
        project = get_object_or_404(Project, pk=pk)
        semester = Semester.get_current()
        name = request.POST.get("name", "").strip()
        if name:
            psn, _ = ProjectSemesterName.objects.get_or_create(project=project, semester=semester)
            psn.name = name
            psn.save(update_fields=["name"])
        stream_names = request.POST.getlist("streams")
        project.streams.set(_get_or_create_streams(stream_names))
        tag_names = request.POST.getlist("tags")
        project.tags.set(_get_or_create_tags(tag_names))
        effort_str = request.POST.get("effort_resourced", "").strip()
        try:
            weeks = float(effort_str) if effort_str else 0.0
            alloc, created = ProjectAllocation.objects.get_or_create(
                project=project, semester=semester,
                defaults={"weeks_new": weeks, "weeks_carryover": 0},
            )
            if not created:
                alloc.weeks_new = weeks
                alloc.weeks_carryover = 0
                alloc.save(update_fields=["weeks_new", "weeks_carryover"])
        except ValueError:
            pass
        return redirect("planning:projects")


class ProjectDeleteView(RoleRequiredMixin, View):
    allowed_roles = (Role.PM,)

    def post(self, request, pk, *args, **kwargs):
        project = get_object_or_404(Project, pk=pk)
        project.delete()
        return HttpResponse(status=204)
