import csv
import io
import json

from django.contrib.auth import get_user_model
from django.http import HttpResponse
from django.shortcuts import get_object_or_404
from django.shortcuts import redirect
from django.views import View
from django.views.generic import ListView

from apps.planning.models import Phase
from apps.planning.models import Project
from apps.planning.models import ProjectAllocation
from apps.planning.models import ProjectSemesterName
from apps.planning.models import Semester
from apps.planning.models import SemesterObserver
from apps.planning.models import Stream
from apps.planning.models import Tag
from apps.users.models import Role

from ._csv_import import _get_or_create_streams
from ._csv_import import _get_or_create_tags
from ._mixins import PMOrParticipantMixin
from ._mixins import RoleRequiredMixin
from ._mixins import _is_semester_observer
from ._semester import get_selected_semester


class ProjectsView(PMOrParticipantMixin, ListView):
    template_name = "planning/projects.html"
    context_object_name = "projects"

    def get_queryset(self):
        semester = get_selected_semester(self.request)
        # Only show projects with a name entry in the current semester
        qs = (
            Project.objects.filter(semester_names__semester=semester)
            .prefetch_related("tags", "streams", "semester_names")
            .select_related("dev_lead", "science_lead", "continuation_of")
        )
        user = self.request.user
        if _is_semester_observer(user, semester) and not user.is_superuser and user.role != Role.PM:
            obs_record = SemesterObserver.objects.filter(
                user=user, semester=semester,
            ).prefetch_related("project_access", "stream_access").first()
            if obs_record:
                direct_pks = set(obs_record.project_access.values_list("pk", flat=True))
                stream_pks = set(
                    Project.objects.filter(
                        streams__in=obs_record.stream_access.all()
                    ).values_list("pk", flat=True)
                )
                qs = qs.filter(pk__in=direct_pks | stream_pks)
            else:
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
        semester = get_selected_semester(self.request)
        ctx["semester"] = semester
        ctx["can_edit"] = self.request.user.role == Role.PM or self.request.user.is_superuser
        ctx["all_tags"] = Tag.objects.all()
        ctx["streams"] = Stream.objects.order_by("name")
        ctx["selected_tags"] = self.request.GET.getlist("tags")
        ctx["selected_streams"] = self.request.GET.getlist("streams")

        User = get_user_model()
        ctx["available_people"] = list(User.objects.order_by("name", "email"))

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
            if project.continuation_of:
                project.continuation_display_name = project.continuation_of.name_for_semester(semester)
            else:
                project.continuation_display_name = None

        # Build per-semester project data for continuation-of selectors and migration modal.
        # Includes effort_resourced and effort_unallocated so the migrate modal can pre-fill weeks.
        other_semesters = list(
            Semester.objects.exclude(pk=semester.pk).order_by("-year", "-semester_type")
        )

        # Bulk-fetch allocations and phase totals for all other semesters
        other_sem_pks = [s.pk for s in other_semesters]
        alloc_by_sem_proj = {}
        for proj_pk, sem_pk, new, carry in (
            ProjectAllocation.objects.filter(semester__in=other_sem_pks)
            .values_list("project_id", "semester_id", "weeks_new", "weeks_carryover")
        ):
            alloc_by_sem_proj[(sem_pk, proj_pk)] = float(new + carry)

        phase_by_sem_proj: dict = {}
        for phase in (
            Phase.objects.filter(semester__in=other_sem_pks)
            .select_related("developer")
            .prefetch_related("developer__leave_periods")
        ):
            key = (phase.semester_id, phase.project_id)
            phase_by_sem_proj[key] = phase_by_sem_proj.get(key, 0) + phase.effort_weeks()

        # Projects in the current semester that already have a continuation_of link —
        # exclude their targets from the migrate list so we don't double-migrate.
        already_linked_pks = set(
            Project.objects.filter(
                semester_names__semester=semester,
                continuation_of__isnull=False,
            ).values_list("continuation_of_id", flat=True)
        )

        continuation_map = {}
        for sem in other_semesters:
            psns = (
                ProjectSemesterName.objects.filter(semester=sem)
                .select_related("project")
                .prefetch_related("project__streams")
                .order_by("name")
            )
            entries = []
            for psn in psns:
                if psn.project.pk in already_linked_pks:
                    continue
                w_res = alloc_by_sem_proj.get((sem.pk, psn.project.pk), 0)
                w_alloc = round(phase_by_sem_proj.get((sem.pk, psn.project.pk), 0), 2)
                entries.append({
                    "pk": psn.project.pk,
                    "name": psn.name,
                    "weeks_resourced": w_res,
                    "weeks_unallocated": round(max(0, w_res - w_alloc), 2),
                    "streams": [s.name for s in psn.project.streams.all()],
                })
            continuation_map[str(sem.pk)] = entries
        ctx["continuation_semesters"] = other_semesters
        ctx["continuation_data_json"] = json.dumps(continuation_map)
        return ctx


class ProjectCreateView(RoleRequiredMixin, View):
    allowed_roles = (Role.PM,)

    def post(self, request, *args, **kwargs):
        name = request.POST.get("name", "").strip()
        if not name:
            return redirect("planning:projects")
        semester = get_selected_semester(request)
        project = Project()
        _apply_lead_fields(project, request)
        _apply_continuation(project, request)
        project.save()
        ProjectSemesterName.objects.create(project=project, semester=semester, name=name)
        stream_names = request.POST.getlist("streams")
        project.streams.set(_get_or_create_streams(stream_names))
        tag_names = request.POST.getlist("tags")
        if tag_names:
            project.tags.set(_get_or_create_tags(tag_names))
        effort_str = request.POST.get("effort_resourced", "").strip()
        try:
            weeks = float(effort_str) if effort_str else 0
        except ValueError:
            weeks = 0
        ProjectAllocation.objects.create(
            project=project, semester=semester,
            weeks_new=weeks, weeks_carryover=0,
        )
        return redirect("planning:projects")


class ProjectDownloadView(RoleRequiredMixin, View):
    allowed_roles = (Role.PM,)

    def get(self, request, *args, **kwargs):
        semester = get_selected_semester(request)
        psns = (
            ProjectSemesterName.objects.filter(semester=semester)
            .select_related("project__dev_lead", "project__science_lead", "project__continuation_of")
            .prefetch_related("project__tags", "project__streams", "project__semester_names")
            .order_by("name")
        )
        resourced_map = {
            pk: float(new + carryover)
            for pk, new, carryover in ProjectAllocation.objects.filter(semester=semester)
            .values_list("project_id", "weeks_new", "weeks_carryover")
        }
        output = io.StringIO()
        writer = csv.writer(output, delimiter="\t")
        writer.writerow([
            "name", "streams", "tags", "effort_resourced",
            "science_lead", "dev_lead", "continuation_of",
        ])
        for psn in psns:
            p = psn.project
            streams = ",".join(s.name for s in p.streams.all())
            tags = ",".join(t.name for t in p.tags.all())
            effort = resourced_map.get(p.pk, 0)
            if p.science_lead:
                sci = p.science_lead.name or p.science_lead.email
            elif p.science_lead_name:
                sci = p.science_lead_name + " (external)"
            else:
                sci = ""
            dev = (p.dev_lead.name or p.dev_lead.email) if p.dev_lead else ""
            cont = p.continuation_of.name_for_semester(semester) if p.continuation_of else ""
            writer.writerow([psn.name, streams, tags, effort, sci, dev, cont])
        response = HttpResponse(output.getvalue(), content_type="application/octet-stream")
        response["Content-Disposition"] = f'attachment; filename="projects_{semester}.tsv"'
        return response


class ProjectUpdateView(RoleRequiredMixin, View):
    allowed_roles = (Role.PM,)

    def post(self, request, pk, *args, **kwargs):
        project = get_object_or_404(Project, pk=pk)
        semester = get_selected_semester(request)
        name = request.POST.get("name", "").strip()
        if name:
            psn, _ = ProjectSemesterName.objects.get_or_create(project=project, semester=semester)
            psn.name = name
            psn.save(update_fields=["name"])
        stream_names = request.POST.getlist("streams")
        project.streams.set(_get_or_create_streams(stream_names))
        tag_names = request.POST.getlist("tags")
        project.tags.set(_get_or_create_tags(tag_names))
        _apply_lead_fields(project, request)
        _apply_continuation(project, request)
        project.save()
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


# NOTE: Removes the project from the current semester only (deletes ProjectSemesterName and
# ProjectAllocation for this semester). If the project has no remaining semester names, it is
# deleted entirely to avoid orphaned records.
class ProjectDeleteView(RoleRequiredMixin, View):
    allowed_roles = (Role.PM,)

    def post(self, request, pk, *args, **kwargs):
        project = get_object_or_404(Project, pk=pk)
        semester = get_selected_semester(request)
        ProjectSemesterName.objects.filter(project=project, semester=semester).delete()
        ProjectAllocation.objects.filter(project=project, semester=semester).delete()
        if not project.semester_names.exists():
            project.delete()
        return HttpResponse(status=204)


class ProjectMigrateView(RoleRequiredMixin, View):
    allowed_roles = (Role.PM,)

    def post(self, request, *args, **kwargs):
        semester = get_selected_semester(request)
        source_semester_pk = request.POST.get("source_semester", "").strip()
        try:
            source_semester = Semester.objects.get(pk=int(source_semester_pk))
        except (Semester.DoesNotExist, ValueError):
            return redirect("planning:projects")
        project_pks = request.POST.getlist("project_pks")
        for pk_str in project_pks:
            try:
                source = Project.objects.prefetch_related("streams", "tags").get(pk=int(pk_str))
            except (Project.DoesNotExist, ValueError):
                continue
            effort_str = request.POST.get(f"effort_{pk_str}", "").strip()
            try:
                effort = float(effort_str) if effort_str else 0.0
            except ValueError:
                effort = 0.0
            new_project = Project(
                continuation_of=source,
                dev_lead=source.dev_lead,
                science_lead=source.science_lead,
                science_lead_name=source.science_lead_name,
            )
            new_project.save()
            new_project.streams.set(source.streams.all())
            new_project.tags.set(source.tags.all())
            ProjectSemesterName.objects.create(
                project=new_project,
                semester=semester,
                name=source.name_for_semester(source_semester),
            )
            ProjectAllocation.objects.create(
                project=new_project, semester=semester,
                weeks_new=effort, weeks_carryover=0,
            )
        return redirect("planning:projects")


def _apply_lead_fields(project, request):
    """Set dev_lead, science_lead, science_lead_name from POST data."""
    User = get_user_model()
    dev_lead_pk = request.POST.get("dev_lead", "").strip()
    if dev_lead_pk:
        try:
            project.dev_lead = User.objects.get(pk=int(dev_lead_pk))
        except (User.DoesNotExist, ValueError):
            project.dev_lead = None
    else:
        project.dev_lead = None

    science_lead_pk = request.POST.get("science_lead", "").strip()
    science_lead_name = request.POST.get("science_lead_name", "").strip()
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


def _apply_continuation(project, request):
    """Set continuation_of from POST data."""
    cont_pk = request.POST.get("continuation_of", "").strip()
    if cont_pk:
        try:
            cont = Project.objects.get(pk=int(cont_pk))
            project.continuation_of = cont if cont.pk != project.pk else None
        except (Project.DoesNotExist, ValueError):
            project.continuation_of = None
    else:
        project.continuation_of = None


