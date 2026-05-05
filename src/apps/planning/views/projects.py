import csv
import io
import json
import math

from django.contrib import messages
from django.contrib.auth import get_user_model
from django.contrib.auth.mixins import LoginRequiredMixin
from django.db import transaction
from django.db.models import Q
from django.http import HttpResponse
from django.shortcuts import get_object_or_404
from django.shortcuts import redirect
from django.views import View
from django.views.generic import ListView

from apps.planning.forms import ProjectWriteForm
from apps.planning.models import Phase
from apps.planning.models import Project
from apps.planning.models import ProjectAllocation
from apps.planning.models import Semester
from apps.planning.models import Stream
from apps.planning.models import Tag
from apps.users.models import Role

from ._csv_import import _get_or_create_streams
from ._csv_import import _get_or_create_tags
from ._mixins import RoleRequiredMixin
from ._mixins import _visible_project_ids_for_user
from ._semester import get_selected_semester


class ProjectsView(LoginRequiredMixin, ListView):
    template_name = "planning/projects.html"
    context_object_name = "projects"

    def get_queryset(self):
        semester = get_selected_semester(self.request)
        qs = (
            Project.objects.filter(semester=semester)
            .prefetch_related("tags", "streams")
            .select_related("dev_lead", "science_lead", "continuation_of")
        )
        visible_project_ids = _visible_project_ids_for_user(self.request.user, semester)
        if visible_project_ids is not None:
            qs = qs.filter(pk__in=visible_project_ids)
        tag_filter = self.request.GET.getlist("tags")
        stream_filter = self.request.GET.getlist("streams")
        if tag_filter:
            qs = qs.filter(tags__name__in=tag_filter).distinct()
        if stream_filter:
            qs = qs.filter(streams__name__in=stream_filter).distinct()
        return qs.order_by("id")

    def get_context_data(self, **kwargs):
        ctx = super().get_context_data(**kwargs)
        semester = get_selected_semester(self.request)
        ctx["semester"] = semester
        ctx["can_edit"] = (
            self.request.user.role == Role.PM or self.request.user.is_superuser
        )
        ctx["all_tags"] = Tag.objects.all()
        ctx["streams"] = Stream.objects.order_by("name")
        ctx["selected_tags"] = self.request.GET.getlist("tags")
        ctx["selected_streams"] = self.request.GET.getlist("streams")

        User = get_user_model()
        ctx["available_people"] = list(User.objects.order_by("name", "email"))

        resourced_map = {
            pk: float(new + carryover)
            for pk, new, carryover in ProjectAllocation.objects.filter(
                semester=semester,
            ).values_list("project_id", "weeks_new", "weeks_carryover")
        }
        allocated_map: dict = {}
        for phase in (
            Phase.objects.filter(semester=semester)
            .select_related("developer")
            .prefetch_related("developer__leave_periods")
        ):
            allocated_map[phase.project_id] = (
                allocated_map.get(phase.project_id, 0) + phase.effort_weeks()
            )

        for project in ctx["projects"]:
            project.display_name = project.name
            project.effort_resourced = resourced_map.get(project.pk, 0)
            project.effort_allocated = round(allocated_map.get(project.pk, 0), 2)
            project.effort_discrepancy = round(
                project.effort_resourced - project.effort_allocated,
                2,
            )
            project.continuation_display_name = (
                project.continuation_of.name if project.continuation_of else None
            )

        # Build per-semester project data for continuation-of selectors and migration modal.
        # Only past semesters are relevant (earlier year, or same year with earlier type).
        other_semesters = list(
            Semester.objects.filter(
                Q(year__lt=semester.year)
                | Q(year=semester.year, semester_type__lt=semester.semester_type),
            ).order_by("-year", "-semester_type"),
        )

        # Bulk-fetch allocations and phase totals for all other semesters
        other_sem_pks = [s.pk for s in other_semesters]
        alloc_by_sem_proj = {}
        for proj_pk, sem_pk, new, carry in ProjectAllocation.objects.filter(
            semester__in=other_sem_pks,
        ).values_list("project_id", "semester_id", "weeks_new", "weeks_carryover"):
            alloc_by_sem_proj[(sem_pk, proj_pk)] = float(new + carry)

        phase_by_sem_proj: dict = {}
        for phase in (
            Phase.objects.filter(semester__in=other_sem_pks)
            .select_related("developer")
            .prefetch_related("developer__leave_periods")
        ):
            key = (phase.semester_id, phase.project_id)
            phase_by_sem_proj[key] = (
                phase_by_sem_proj.get(key, 0) + phase.effort_weeks()
            )

        # Projects already targeted by some other project's continuation_of
        # (each source project can only be continued by one other project).
        already_linked_pks = set(
            Project.objects.filter(continuations__isnull=False).values_list(
                "pk", flat=True,
            ),
        )

        continuation_map = {}
        for sem in other_semesters:
            projects_in_sem = (
                Project.objects.filter(semester=sem)
                .prefetch_related("streams")
                .order_by("name")
            )
            entries = []
            for p in projects_in_sem:
                w_res = alloc_by_sem_proj.get((sem.pk, p.pk), 0)
                w_alloc = round(phase_by_sem_proj.get((sem.pk, p.pk), 0), 2)
                entries.append(
                    {
                        "pk": p.pk,
                        "name": p.name,
                        "weeks_resourced": w_res,
                        "weeks_unallocated": round(max(0, w_res - w_alloc), 2),
                        "streams": [s.name for s in p.streams.all()],
                        "already_linked": p.pk in already_linked_pks,
                    },
                )
            continuation_map[str(sem.pk)] = entries
        ctx["continuation_semesters"] = other_semesters
        ctx["continuation_data_json"] = json.dumps(continuation_map)
        return ctx


class ProjectCreateView(RoleRequiredMixin, View):
    allowed_roles = (Role.PM,)

    def post(self, request, *args, **kwargs):
        form = ProjectWriteForm(request.POST)
        if not form.is_valid():
            for field_errors in form.errors.values():
                for err in field_errors:
                    messages.error(request, err)
            return redirect("planning:projects")
        semester = get_selected_semester(request)
        cleaned = form.cleaned_data
        with transaction.atomic():
            project = Project(name=cleaned["name"], semester=semester)
            _apply_lead_fields(project, cleaned)
            _apply_continuation(project, cleaned)
            project.save()
            project.streams.set(_get_or_create_streams(cleaned.get("streams", [])))
            tag_names = cleaned.get("tags", [])
            if tag_names:
                project.tags.set(_get_or_create_tags(tag_names))
            ProjectAllocation.objects.create(
                project=project,
                semester=semester,
                weeks_new=cleaned["effort_resourced"],
                weeks_carryover=0,
            )
        return redirect("planning:projects")


class ProjectDownloadView(RoleRequiredMixin, View):
    allowed_roles = (Role.PM,)

    def get(self, request, *args, **kwargs):
        semester = get_selected_semester(request)
        projects = (
            Project.objects.filter(semester=semester)
            .select_related(
                "dev_lead",
                "science_lead",
                "continuation_of",
            )
            .prefetch_related(
                "tags",
                "streams",
            )
            .order_by("name")
        )
        resourced_map = {
            pk: float(new + carryover)
            for pk, new, carryover in ProjectAllocation.objects.filter(
                semester=semester,
            ).values_list("project_id", "weeks_new", "weeks_carryover")
        }
        output = io.StringIO()
        writer = csv.writer(output, delimiter="\t")
        writer.writerow(
            [
                "name",
                "streams",
                "tags",
                "effort_resourced",
                "science_lead",
                "dev_lead",
                "continuation_of",
            ],
        )
        for p in projects:
            streams = "||".join(s.name for s in p.streams.all())
            tags = "||".join(t.name for t in p.tags.all())
            effort = resourced_map.get(p.pk, 0)
            if p.science_lead:
                sci = p.science_lead.name or p.science_lead.email
            elif p.science_lead_name:
                sci = p.science_lead_name + " (external)"
            else:
                sci = ""
            dev = (p.dev_lead.name or p.dev_lead.email) if p.dev_lead else ""
            cont = p.continuation_of.name if p.continuation_of else ""
            writer.writerow([p.name, streams, tags, effort, sci, dev, cont])
        response = HttpResponse(
            output.getvalue(),
            content_type="application/octet-stream",
        )
        response["Content-Disposition"] = (
            f'attachment; filename="projects_{semester}.tsv"'
        )
        return response


class ProjectUpdateView(RoleRequiredMixin, View):
    allowed_roles = (Role.PM,)

    def post(self, request, pk, *args, **kwargs):
        project = get_object_or_404(Project, pk=pk)
        semester = project.semester
        form = ProjectWriteForm(request.POST)
        if not form.is_valid():
            for field_errors in form.errors.values():
                for err in field_errors:
                    messages.error(request, err)
            return redirect("planning:projects")
        cleaned = form.cleaned_data
        with transaction.atomic():
            project.name = cleaned["name"]
            project.streams.set(_get_or_create_streams(cleaned.get("streams", [])))
            project.tags.set(_get_or_create_tags(cleaned.get("tags", [])))
            _apply_lead_fields(project, cleaned)
            _apply_continuation(project, cleaned)
            project.save()
            alloc, created = ProjectAllocation.objects.get_or_create(
                project=project,
                semester=semester,
                defaults={"weeks_new": cleaned["effort_resourced"], "weeks_carryover": 0},
            )
            if not created:
                alloc.weeks_new = cleaned["effort_resourced"]
                alloc.weeks_carryover = 0
                alloc.save(update_fields=["weeks_new", "weeks_carryover"])
        return redirect("planning:projects")


class ProjectDeleteView(RoleRequiredMixin, View):
    allowed_roles = (Role.PM,)

    def post(self, request, pk, *args, **kwargs):
        project = get_object_or_404(Project, pk=pk)
        project.delete()
        return HttpResponse(status=204)


class ProjectMigrateView(RoleRequiredMixin, View):
    allowed_roles = (Role.PM,)

    def post(self, request, *args, **kwargs):
        semester = get_selected_semester(request)
        source_semester_pk = request.POST.get("source_semester", "").strip()
        try:
            Semester.objects.get(pk=int(source_semester_pk))
        except (Semester.DoesNotExist, ValueError):
            messages.error(request, "Select a valid source semester.")
            return redirect("planning:projects")
        project_pks = request.POST.getlist("project_pks")

        migration_rows = []
        for pk_str in project_pks:
            try:
                source = Project.objects.prefetch_related("streams", "tags").get(
                    pk=int(pk_str),
                )
            except (Project.DoesNotExist, ValueError):
                continue
            effort_str = request.POST.get(f"effort_{pk_str}", "").strip()
            effort = _parse_effort_weeks(
                request,
                effort_str,
                source.name,
            )
            if effort is None:
                return redirect("planning:projects")
            migration_rows.append((source, effort))

        with transaction.atomic():
            for source, effort in migration_rows:
                new_project = Project(
                    name=source.name,
                    semester=semester,
                    continuation_of=source,
                    dev_lead=source.dev_lead,
                    science_lead=source.science_lead,
                    science_lead_name=source.science_lead_name,
                )
                new_project.save()
                new_project.streams.set(source.streams.all())
                new_project.tags.set(source.tags.all())
                ProjectAllocation.objects.create(
                    project=new_project,
                    semester=semester,
                    weeks_new=effort,
                    weeks_carryover=0,
                )
        return redirect("planning:projects")


def _parse_effort_weeks(request, effort_str, project_name=""):
    if not effort_str:
        return 0.0
    try:
        weeks = float(effort_str)
    except ValueError:
        weeks = None
    if weeks is None or not math.isfinite(weeks):
        label = f" for '{project_name}'" if project_name else ""
        messages.error(request, f"Enter a valid resourced effort value{label}.")
        return None
    if weeks < 0:
        label = f" for '{project_name}'" if project_name else ""
        messages.error(request, f"Resourced effort cannot be negative{label}.")
        return None
    return weeks


def _apply_lead_fields(project, cleaned_data):
    """Set dev_lead, science_lead, science_lead_name from POST data."""
    User = get_user_model()
    dev_lead_pk = cleaned_data.get("dev_lead")
    if dev_lead_pk:
        try:
            project.dev_lead = User.objects.get(pk=int(dev_lead_pk))
        except (User.DoesNotExist, ValueError):
            project.dev_lead = None
    else:
        project.dev_lead = None

    science_lead_pk = cleaned_data.get("science_lead")
    science_lead_name = (cleaned_data.get("science_lead_name") or "").strip()
    if science_lead_pk:
        try:
            project.science_lead = User.objects.get(pk=int(science_lead_pk))
            project.science_lead_name = ""
        except (User.DoesNotExist, ValueError):
            project.science_lead = None
            project.science_lead_name = science_lead_name
    else:
        project.science_lead = None
        project.science_lead_name = science_lead_name


def _apply_continuation(project, cleaned_data):
    """Set continuation_of from POST data."""
    cont_pk = cleaned_data.get("continuation_of")
    if cont_pk:
        try:
            cont = Project.objects.get(pk=int(cont_pk))
            project.continuation_of = cont if cont.pk != project.pk else None
        except (Project.DoesNotExist, ValueError):
            project.continuation_of = None
    else:
        project.continuation_of = None
