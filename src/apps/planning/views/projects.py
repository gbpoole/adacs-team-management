import csv
import io
import json
import math

from django.contrib import messages
from django.contrib.auth.mixins import LoginRequiredMixin
from django.db import transaction
from django.db.models import Q
from django.db.models import Value
from django.db.models.functions import Coalesce
from django.http import HttpResponse
from django.shortcuts import get_object_or_404
from django.shortcuts import render
from django.views import View
from django.views.generic import ListView

from apps.planning.effort import ProjectEffort
from apps.planning.effort import compute_project_effort
from apps.planning.forms import ProjectWriteForm
from apps.planning.models import DeveloperProfile
from apps.planning.models import Project
from apps.planning.models import ProjectAllocation
from apps.planning.models import ProjectTimeEntry
from apps.planning.models import Semester
from apps.planning.models import Stream
from apps.planning.models import Tag
from apps.planning.models import UserProjectAccess
from apps.users.models import Role

from ._csv_import import _get_or_create_streams
from ._csv_import import _get_or_create_tags
from ._mixins import RoleRequiredMixin
from ._mixins import _redirect_or_hx_redirect
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
        can_edit = self.request.user.role == Role.PM or self.request.user.is_superuser
        ctx["can_edit"] = can_edit
        ctx["all_tags"] = Tag.objects.all()
        ctx["streams"] = Stream.objects.order_by("name")
        ctx["selected_tags"] = self.request.GET.getlist("tags")
        ctx["selected_streams"] = self.request.GET.getlist("streams")

        ctx.update(_project_modal_options_context(semester))

        # Effort figures are computed live: carryover flows from each project's
        # continuation_of parent, so all continuation-semester projects are
        # included in one batch when the modals need them.
        current_pks = [p.pk for p in ctx["projects"]]
        if can_edit:
            cont_semesters = ctx["continuation_semesters"]
            cont_sem_pks = [s.pk for s in cont_semesters]
            cont_projects = list(
                Project.objects.filter(semester__in=cont_sem_pks)
                .prefetch_related("streams")
                .order_by("name"),
            )
            effort_map = compute_project_effort(
                current_pks + [p.pk for p in cont_projects],
            )
        else:
            effort_map = compute_project_effort(current_pks)

        time_entry_counts: dict = {}
        for proj_pk in ProjectTimeEntry.objects.filter(
            project__semester=semester,
        ).values_list("project_id", flat=True):
            time_entry_counts[proj_pk] = time_entry_counts.get(proj_pk, 0) + 1

        empty = ProjectEffort()
        for project in ctx["projects"]:
            effort = effort_map.get(project.pk, empty)
            project.display_name = project.name
            project.effort_new = effort.weeks_new
            project.effort_carryover = effort.carryover
            project.effort_resourced = effort.resourced
            project.effort_allocated = effort.allocated
            project.effort_discrepancy = effort.unallocated
            project.time_entry_count = time_entry_counts.get(project.pk, 0)
            project.continuation_display_name = (
                project.continuation_of.name if project.continuation_of else None
            )

        # Build per-semester project data for the continuation-of and migration
        # modals, plus per-project time entries for the non-dev time modal.
        # Only PM/superuser can edit, so non-PM users must not receive a JSON
        # blob of every project name in the HTML (information leak).
        if can_edit:
            # Projects already targeted by some other project's continuation_of
            # (each source project can only be continued by one other project).
            already_linked_pks = set(
                Project.objects.filter(continuations__isnull=False).values_list(
                    "pk",
                    flat=True,
                ),
            )

            continuation_map: dict = {str(s.pk): [] for s in cont_semesters}
            for p in cont_projects:
                effort = effort_map.get(p.pk, empty)
                continuation_map[str(p.semester_id)].append(
                    {
                        "pk": p.pk,
                        "name": p.name,
                        "weeks_resourced": effort.resourced,
                        "weeks_unallocated": effort.unallocated,
                        "streams": [s.name for s in p.streams.all()],
                        "already_linked": p.pk in already_linked_pks,
                    },
                )
            ctx["continuation_data_json"] = json.dumps(continuation_map)

            time_entries_map: dict = {}
            for entry in ProjectTimeEntry.objects.filter(
                project__semester=semester,
            ):
                time_entries_map.setdefault(str(entry.project_id), []).append(
                    {
                        "pk": entry.pk,
                        "weeks": float(entry.weeks),
                        "comment": entry.comment,
                    },
                )
            ctx["time_entries_json"] = json.dumps(time_entries_map)
        else:
            ctx["continuation_semesters"] = []
            ctx["migrate_semesters"] = []
            ctx["continuation_data_json"] = json.dumps({})
            ctx["time_entries_json"] = json.dumps({})
        ctx["project_add_form"] = ProjectWriteForm()
        ctx["selected_add_streams"] = []
        ctx["selected_add_tags"] = []
        ctx["project_edit_form"] = ProjectWriteForm()
        ctx["selected_edit_streams"] = []
        ctx["selected_edit_tags"] = []
        ctx["edit_project"] = None
        return ctx


class ProjectCreateView(RoleRequiredMixin, View):
    allowed_roles = (Role.PM,)

    def post(self, request, *args, **kwargs):
        target_url = "planning:projects"
        semester = get_selected_semester(request)
        form = ProjectWriteForm(request.POST)
        continuation = None
        if form.is_valid():
            continuation, cont_error = _resolve_continuation(
                form.cleaned_data.get("continuation_of"),
                semester,
            )
            if cont_error:
                form.add_error("continuation_of", cont_error)
        sci_error = _validate_inline_science_lead(request)
        if sci_error:
            form.add_error(None, sci_error)
        if form.errors:
            if request.headers.get("HX-Request") == "true":
                context = _project_modal_options_context(semester)
                context["project_add_form"] = form
                context["selected_add_streams"] = request.POST.getlist("streams")
                context["selected_add_tags"] = request.POST.getlist("tags")
                context["new_science_lead_name"] = request.POST.get(
                    "new_science_lead_name", ""
                )
                context["new_science_lead_email"] = request.POST.get(
                    "new_science_lead_email", ""
                )
                return render(
                    request,
                    "planning/partials/project_add_form.html",
                    context,
                    status=422,
                )
            for field_errors in form.errors.values():
                for err in field_errors:
                    messages.error(request, err)
            return _redirect_or_hx_redirect(request, target_url)
        cleaned = form.cleaned_data
        with transaction.atomic():
            project = Project(name=cleaned["name"], semester=semester)
            _apply_lead_fields(project, cleaned)
            project.continuation_of = continuation
            project.save()
            project.streams.set(_get_or_create_streams(cleaned.get("streams", [])))
            tag_names = cleaned.get("tags", [])
            if tag_names:
                project.tags.set(_get_or_create_tags(tag_names))
            ProjectAllocation.objects.create(
                project=project,
                semester=semester,
                weeks_new=cleaned["effort_resourced"],
            )
            _apply_inline_science_lead(request, project)
        return _redirect_or_hx_redirect(request, target_url)


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
        effort_map = compute_project_effort([p.pk for p in projects])
        empty = ProjectEffort()
        output = io.StringIO()
        writer = csv.writer(output, delimiter="\t")
        writer.writerow(
            [
                "name",
                "streams",
                "tags",
                "effort_new",
                "effort_carryover",
                "effort_resourced",
                "science_lead",
                "dev_lead",
                "continuation_of",
            ],
        )
        for p in projects:
            streams = "||".join(s.name for s in p.streams.all())
            tags = "||".join(t.name for t in p.tags.all())
            effort = effort_map.get(p.pk, empty)
            sci = p.science_lead.display_name if p.science_lead else ""
            dev = p.dev_lead.display_name if p.dev_lead else ""
            cont = p.continuation_of.name if p.continuation_of else ""
            writer.writerow(
                [
                    p.name,
                    streams,
                    tags,
                    effort.weeks_new,
                    effort.carryover,
                    effort.resourced,
                    sci,
                    dev,
                    cont,
                ],
            )
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
        target_url = "planning:projects"
        project = get_object_or_404(Project, pk=pk)
        semester = project.semester
        form = ProjectWriteForm(request.POST)
        continuation = None
        if form.is_valid():
            continuation, cont_error = _resolve_continuation(
                form.cleaned_data.get("continuation_of"),
                semester,
                project=project,
            )
            if cont_error:
                form.add_error("continuation_of", cont_error)
        sci_error = _validate_inline_science_lead(request)
        if sci_error:
            form.add_error(None, sci_error)
        if form.errors:
            if request.headers.get("HX-Request") == "true":
                context = _project_modal_options_context(semester)
                context["project_edit_form"] = form
                context["selected_edit_streams"] = request.POST.getlist("streams")
                context["selected_edit_tags"] = request.POST.getlist("tags")
                context["edit_project"] = project
                context["new_science_lead_name"] = request.POST.get(
                    "new_science_lead_name", ""
                )
                context["new_science_lead_email"] = request.POST.get(
                    "new_science_lead_email", ""
                )
                return render(
                    request,
                    "planning/partials/project_edit_form.html",
                    context,
                    status=422,
                )
            for field_errors in form.errors.values():
                for err in field_errors:
                    messages.error(request, err)
            return _redirect_or_hx_redirect(request, target_url)
        cleaned = form.cleaned_data
        with transaction.atomic():
            project.name = cleaned["name"]
            project.streams.set(_get_or_create_streams(cleaned.get("streams", [])))
            project.tags.set(_get_or_create_tags(cleaned.get("tags", [])))
            _apply_lead_fields(project, cleaned)
            project.continuation_of = continuation
            project.save()
            alloc, created = ProjectAllocation.objects.get_or_create(
                project=project,
                semester=semester,
                defaults={"weeks_new": cleaned["effort_resourced"]},
            )
            if not created:
                alloc.weeks_new = cleaned["effort_resourced"]
                alloc.save(update_fields=["weeks_new"])
            _apply_inline_science_lead(request, project)
        return _redirect_or_hx_redirect(request, target_url)


class ProjectDeleteView(RoleRequiredMixin, View):
    allowed_roles = (Role.PM,)

    def post(self, request, pk, *args, **kwargs):
        project = get_object_or_404(Project, pk=pk)
        project.delete()
        return _redirect_or_hx_redirect(request, "planning:projects")


class ProjectMigrateView(RoleRequiredMixin, View):
    allowed_roles = (Role.PM,)

    def post(self, request, *args, **kwargs):
        target_url = "planning:projects"
        semester = get_selected_semester(request)
        source_semester_pk = request.POST.get("source_semester", "").strip()
        try:
            source_semester = Semester.objects.get(pk=int(source_semester_pk))
        except (Semester.DoesNotExist, ValueError):
            messages.error(request, "Select a valid source semester.")
            return _redirect_or_hx_redirect(request, target_url)
        if source_semester.sort_key >= semester.sort_key:
            messages.error(
                request, "Projects can only be migrated from a previous semester."
            )
            return _redirect_or_hx_redirect(request, target_url)
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
                return _redirect_or_hx_redirect(request, target_url)
            migration_rows.append((source, effort))

        with transaction.atomic():
            for source, effort in migration_rows:
                new_project = Project(
                    name=source.name,
                    semester=semester,
                    continuation_of=source,
                    dev_lead=source.dev_lead,
                    science_lead=source.science_lead,
                )
                new_project.save()
                new_project.streams.set(source.streams.all())
                new_project.tags.set(source.tags.all())
                ProjectAllocation.objects.create(
                    project=new_project,
                    semester=semester,
                    weeks_new=effort,
                )
        return _redirect_or_hx_redirect(request, target_url)


class ProjectTimeEntryCreateView(RoleRequiredMixin, View):
    allowed_roles = (Role.PM,)

    def post(self, request, pk, *args, **kwargs):
        project = get_object_or_404(Project, pk=pk)
        weeks = _parse_effort_weeks(
            request,
            request.POST.get("weeks", "").strip(),
            project.name,
        )
        if weeks is not None:
            ProjectTimeEntry.objects.create(
                project=project,
                weeks=weeks,
                comment=request.POST.get("comment", "").strip()[:255],
            )
        return _redirect_or_hx_redirect(request, "planning:projects")


class ProjectTimeEntryDeleteView(RoleRequiredMixin, View):
    allowed_roles = (Role.PM,)

    def post(self, request, pk, *args, **kwargs):
        get_object_or_404(ProjectTimeEntry, pk=pk).delete()
        return _redirect_or_hx_redirect(request, "planning:projects")


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
    """Set dev_lead and science_lead from POST data."""
    dev_lead_pk = cleaned_data.get("dev_lead")
    if dev_lead_pk:
        try:
            project.dev_lead = DeveloperProfile.objects.get(pk=int(dev_lead_pk))
        except (DeveloperProfile.DoesNotExist, ValueError):
            project.dev_lead = None
    else:
        project.dev_lead = None

    science_lead_pk = cleaned_data.get("science_lead")
    if science_lead_pk:
        try:
            project.science_lead = DeveloperProfile.objects.get(pk=int(science_lead_pk))
        except (DeveloperProfile.DoesNotExist, ValueError):
            project.science_lead = None
    else:
        project.science_lead = None


def _validate_inline_science_lead(request):
    """Validate the inline new-science-lead fields.

    Returns an error string when exactly one of name/email is filled, else None.
    """
    name = request.POST.get("new_science_lead_name", "").strip()
    email = request.POST.get("new_science_lead_email", "").strip()
    if name and email:
        return None
    if name or email:
        return "Provide both a name and an email for the new Science Lead."
    return None


def _apply_inline_science_lead(request, project):
    """Create/reuse a person from the inline new-science-lead fields, set them as
    the project's science lead, and grant them pre-registration access to this
    project only. New-person fields override the science-lead dropdown; no-op when
    the fields are empty. Assumes fields were already validated.
    """
    name = request.POST.get("new_science_lead_name", "").strip()
    email = request.POST.get("new_science_lead_email", "").strip()
    if not name or not email:
        return
    profile = DeveloperProfile.objects.filter(email__iexact=email).first()
    created = profile is None
    if created:
        profile = DeveloperProfile.objects.create(name=name, email=email)
    project.science_lead = profile
    project.save(update_fields=["science_lead"])
    # Only provision access for a newly created, still-unregistered person;
    # never clobber an existing person's policy.
    if created and not profile.is_registered:
        access, _ = UserProjectAccess.objects.get_or_create(developer_profile=profile)
        access.project_access.add(project)


def _resolve_continuation(cont_pk, semester, project=None):
    """Resolve and validate a continuation_of POST value.

    Returns ``(continuation_project_or_None, error_message_or_None)``.
    ``project`` is the project being edited (None on create).
    """
    if not cont_pk:
        return None, None
    try:
        cont = Project.objects.select_related("semester").get(pk=int(cont_pk))
    except (Project.DoesNotExist, ValueError):
        return None, None
    error = _validate_continuation(cont, semester, project)
    return (None, error) if error else (cont, None)


def _validate_continuation(cont, semester, project):
    """Return an error message if ``cont`` is not a valid continuation source."""
    if project is not None and cont.pk == project.pk:
        return "A project cannot be a continuation of itself."
    if cont.semester.sort_key > semester.sort_key:
        return (
            "Continuation must reference a project in the current "
            "or a previous semester."
        )
    if project is not None and _continuation_creates_cycle(cont, project):
        return "This would create a continuation cycle."
    linked_qs = Project.objects.filter(continuation_of=cont)
    if project is not None:
        linked_qs = linked_qs.exclude(pk=project.pk)
    if linked_qs.exists():
        return f"'{cont.name}' is already continued by another project."
    return None


def _continuation_creates_cycle(cont, project):
    """Walk the chain upward; reaching the edited project means a cycle."""
    visited = {cont.pk}
    ancestor_pk = cont.continuation_of_id
    while ancestor_pk is not None and ancestor_pk not in visited:
        if ancestor_pk == project.pk:
            return True
        visited.add(ancestor_pk)
        ancestor_pk = (
            Project.objects.filter(pk=ancestor_pk)
            .values_list("continuation_of_id", flat=True)
            .first()
        )
    return False


def _project_modal_options_context(semester):
    previous_semesters = list(
        Semester.objects.filter(
            Q(year__lt=semester.year)
            | Q(year=semester.year, semester_type__lt=semester.semester_type),
        ).order_by("-year", "-semester_type"),
    )
    return {
        "all_tags": Tag.objects.all(),
        "streams": Stream.objects.order_by("name"),
        "available_people": list(
            DeveloperProfile.objects.select_related("user")
            .annotate(
                sort_name=Coalesce("user__name", "name", Value("")),
                sort_email=Coalesce("user__email", "email", Value("")),
            )
            .order_by("sort_name", "sort_email")
        ),
        # Continuation may reference the current semester; bulk migration
        # only makes sense from a previous one.
        "continuation_semesters": [semester, *previous_semesters],
        "migrate_semesters": previous_semesters,
    }
