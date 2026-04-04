import csv
import datetime
import io
import json

from django.contrib import messages
from django.contrib.auth import get_user_model
from django.contrib.auth.mixins import LoginRequiredMixin
from django.core.exceptions import PermissionDenied, ValidationError
from django.core.validators import EmailValidator
from django.db import transaction
from django.http import HttpResponse
from django.shortcuts import get_object_or_404, redirect
from django.views import View
from django.views.generic import ListView, TemplateView

from apps.users.models import Role

from .models import (
    DeveloperLane,
    DeveloperProfile,
    Leave,
    ObserverProfile,
    Phase,
    Project,
    ProjectAllocation,
    ProjectSemesterName,
    Semester,
    SemesterDeveloper,
    Stream,
    Tag,
)


# ---------------------------------------------------------------------------
# Home / dashboard
# ---------------------------------------------------------------------------


class HomeView(TemplateView):
    template_name = "pages/home.html"

    def get_context_data(self, **kwargs):
        ctx = super().get_context_data(**kwargs)
        user = self.request.user
        if not user.is_authenticated:
            return ctx

        semester = Semester.get_current()
        ctx["semester"] = semester
        today = datetime.date.today()
        in_30_days = today + datetime.timedelta(days=30)
        role = user.role

        if role in (Role.ADMIN, Role.PM) or user.is_superuser:
            ctx["dev_count"] = DeveloperProfile.objects.count()
            ctx["project_count"] = Project.objects.count()
            records = SemesterDeveloper.objects.filter(semester=semester)
            ctx["total_effort_available"] = sum(r.effort_available for r in records)
            phases = list(Phase.objects.filter(semester=semester).select_related("developer"))
            allocated: dict = {}
            for ph in phases:
                allocated[ph.developer_id] = allocated.get(ph.developer_id, 0) + ph.effort_weeks()
            ctx["total_effort_allocated"] = round(sum(allocated.values()), 1)
            ctx["upcoming_leave"] = (
                Leave.objects.filter(end_date__gte=today, start_date__lte=in_30_days)
                .select_related("developer__user")
                .order_by("start_date")[:10]
            )

        if role == Role.DEVELOPER and not user.is_superuser:
            try:
                profile = user.developer_profile
                ctx["my_profile"] = profile
                sd = SemesterDeveloper.objects.filter(developer=profile, semester=semester).first()
                ctx["my_effort_available"] = sd.effort_available if sd else None
                my_phases = list(
                    Phase.objects.filter(developer=profile, semester=semester)
                    .select_related("project")
                    .prefetch_related("project__semester_names")
                    .order_by("start_date")
                )
                for ph in my_phases:
                    ph.display_name = ph.project.name_for_semester(semester)
                ctx["my_effort_allocated"] = round(sum(ph.effort_weeks() for ph in my_phases), 1)
                ctx["my_phases"] = my_phases
                ctx["my_upcoming_leave"] = (
                    Leave.objects.filter(developer=profile, end_date__gte=today)
                    .order_by("start_date")[:5]
                )
            except DeveloperProfile.DoesNotExist:
                pass

        if role == Role.OBSERVER and not user.is_superuser:
            try:
                ctx["my_project_count"] = user.observer_profile.project_access.count()
            except Exception:
                ctx["my_project_count"] = 0

        return ctx


class RoleRequiredMixin(LoginRequiredMixin):
    """Restrict access to users whose role is in ``allowed_roles``."""

    allowed_roles: tuple[str, ...] = ()

    def dispatch(self, request, *args, **kwargs):
        response = super().dispatch(request, *args, **kwargs)
        if request.user.is_authenticated:
            role = request.user.role
            if not (role in self.allowed_roles or request.user.is_superuser):
                raise PermissionDenied
        return response


# ---------------------------------------------------------------------------
# Timeline helpers  (FR-16 / FR-17)
# ---------------------------------------------------------------------------


def _week_starts(start: datetime.date, end: datetime.date) -> list:
    """Return list of Monday dates covering the range [start, end]."""
    first = start - datetime.timedelta(days=start.weekday())
    weeks = []
    w = first
    while w <= end:
        weeks.append(w)
        w += datetime.timedelta(weeks=1)
    return weeks


def _find_or_create_non_overlapping_lane(
    developer, semester, start_date, end_date, preferred_lane, exclude_phase_pk=None,
):
    """
    Return ``preferred_lane`` if no phase in it overlaps [start_date, end_date].
    Otherwise try each of the developer's lanes in order; if all overlap, create
    a new lane at max_order+1.
    """
    from django.db.models import Max  # noqa: PLC0415

    def has_overlap(lane):
        qs = Phase.objects.filter(
            lane=lane, start_date__lte=end_date, end_date__gte=start_date,
        )
        if exclude_phase_pk:
            qs = qs.exclude(pk=exclude_phase_pk)
        return qs.exists()

    if not has_overlap(preferred_lane):
        return preferred_lane

    for lane in DeveloperLane.objects.filter(
        developer=developer, semester=semester,
    ).exclude(pk=preferred_lane.pk).order_by("order", "pk"):
        if not has_overlap(lane):
            return lane

    max_order = DeveloperLane.objects.filter(
        developer=developer, semester=semester,
    ).aggregate(Max("order"))["order__max"]
    new_order = (max_order + 1) if max_order is not None else 0
    return DeveloperLane.objects.create(developer=developer, semester=semester, order=new_order)


def _build_lane_cells(n_weeks, phase_segments):
    """
    Build a cell list for a single lane.
    phase_segments: list of (start_col, span, phase).

    All phases are emitted as individual cells regardless of overlap — absolute
    positioning in the template renders them correctly even when they overlap.
    Empty cells are emitted for column runs not covered by any phase (used for
    drag-to-create).
    """
    # Mark columns covered by at least one phase
    covered = bytearray(n_weeks)
    for start_col, span, _ in phase_segments:
        for c in range(max(0, start_col), min(n_weeks, start_col + span)):
            covered[c] = 1

    # Emit every phase cell (sorted for deterministic order)
    cells = [
        {
            "type": "phase",
            "colspan": span,
            "phase": ph,
            "col_start": start_col,
            "col_end": start_col + span - 1,
        }
        for start_col, span, ph in sorted(phase_segments, key=lambda x: x[0])
    ]

    # Emit empty cells for uncovered column runs
    col = 0
    while col < n_weeks:
        if not covered[col]:
            end = col
            while end + 1 < n_weeks and not covered[end + 1]:
                end += 1
            cells.append({
                "type": "empty",
                "colspan": end - col + 1,
                "phase": None,
                "col_start": col,
                "col_end": end,
            })
            col = end + 1
        else:
            col += 1

    return cells


def _coverage(item_start: datetime.date, item_end: datetime.date, weeks: list):
    """Return (start_col, span) for an item over the given week list, or (None, None)."""
    start_col = end_col = None
    for i, ws in enumerate(weeks):
        we = ws + datetime.timedelta(days=6)
        if item_start <= we and item_end >= ws:
            if start_col is None:
                start_col = i
            end_col = i
    if start_col is None:
        return None, None
    return start_col, end_col - start_col + 1


def _build_timeline_layers(n_weeks, phase_segments, leave_week_set):
    """
    Assign phase_segments to non-overlapping layers and build cell lists.

    phase_segments: list of (start_col, span, phase)
    leave_week_set: set of week indices covered by leave

    Returns list of layers; each layer is a list of cell dicts:
      {'type': 'empty'|'leave'|'phase', 'colspan': int, 'phase': Phase|None,
       'col_start': int, 'col_end': int}
    """
    layers_data = []
    for seg in sorted(phase_segments, key=lambda x: x[0]):
        start_col, span, phase = seg
        placed = False
        for layer in layers_data:
            if not any(s < start_col + span and s + p > start_col for s, p, _ in layer):
                layer.append(seg)
                placed = True
                break
        if not placed:
            layers_data.append([seg])

    if not layers_data:
        layers_data = [[]]

    result = []
    for layer in layers_data:
        phase_at = {s: (s, span, ph) for s, span, ph in layer}
        cells = []
        col = 0
        while col < n_weeks:
            if col in phase_at:
                s, span, ph = phase_at[col]
                cells.append({
                    "type": "phase",
                    "colspan": span,
                    "phase": ph,
                    "col_start": s,
                    "col_end": s + span - 1,
                })
                col += span
            else:
                next_phase = min((s for s in phase_at if s > col), default=n_weeks)
                run = col
                while run < next_phase:
                    if run in leave_week_set:
                        end = run
                        while end + 1 < next_phase and end + 1 in leave_week_set:
                            end += 1
                        cells.append({
                            "type": "leave",
                            "colspan": end - run + 1,
                            "phase": None,
                            "col_start": run,
                            "col_end": end,
                        })
                        run = end + 1
                    else:
                        end = run
                        while end + 1 < next_phase and end + 1 not in leave_week_set:
                            end += 1
                        cells.append({
                            "type": "empty",
                            "colspan": end - run + 1,
                            "phase": None,
                            "col_start": run,
                            "col_end": end,
                        })
                        run = end + 1
                col = next_phase
        result.append(cells)
    return result


# ---------------------------------------------------------------------------
# Developers page  (FR-10)
# ---------------------------------------------------------------------------


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
        ).select_related("developer")
        effort_allocated = {}
        for phase in phases:
            effort_allocated[phase.developer_id] = (
                effort_allocated.get(phase.developer_id, 0) + phase.effort_weeks()
            )

        for dev in ctx["developers"]:
            dev.effort_available = effort_map.get(dev.pk)
            dev.effort_allocated = round(effort_allocated.get(dev.pk, 0), 2)
        return ctx


# ---------------------------------------------------------------------------
# Observers page  (FR-11)
# ---------------------------------------------------------------------------


class ObserversView(RoleRequiredMixin, ListView):
    template_name = "planning/observers.html"
    context_object_name = "observers"
    allowed_roles = (Role.ADMIN, Role.PM)

    def get_queryset(self):
        return (
            ObserverProfile.objects.select_related("user")
            .prefetch_related("project_access")
            .order_by("user__name", "user__email")
        )

    def get_context_data(self, **kwargs):
        ctx = super().get_context_data(**kwargs)
        semester = Semester.get_current()
        ctx["semester"] = semester
        all_projects = list(Project.objects.prefetch_related("semester_names").all())
        for p in all_projects:
            p.display_name = p.name_for_semester(semester)
        ctx["all_projects"] = all_projects
        return ctx


# ---------------------------------------------------------------------------
# Projects page  (FR-12)
# ---------------------------------------------------------------------------


class ProjectsView(RoleRequiredMixin, ListView):
    template_name = "planning/projects.html"
    context_object_name = "projects"
    allowed_roles = (Role.ADMIN, Role.PM, Role.DEVELOPER, Role.OBSERVER)

    def get_queryset(self):
        qs = Project.objects.prefetch_related("tags", "semester_names").select_related(
            "stream",
        )
        user = self.request.user
        if user.role == Role.OBSERVER:
            try:
                profile = user.observer_profile
                qs = qs.filter(observer_access=profile)
            except ObserverProfile.DoesNotExist:
                qs = qs.none()
        return qs.order_by("id")

    def get_context_data(self, **kwargs):
        ctx = super().get_context_data(**kwargs)
        semester = Semester.get_current()
        ctx["semester"] = semester
        ctx["can_edit"] = self.request.user.role in (Role.ADMIN, Role.PM) or self.request.user.is_superuser
        ctx["all_tags"] = Tag.objects.all()
        ctx["streams"] = Stream.objects.order_by("name")

        resourced_map = {
            pk: float(new + carryover)
            for pk, new, carryover in ProjectAllocation.objects.filter(semester=semester)
            .values_list("project_id", "weeks_new", "weeks_carryover")
        }
        allocated_map: dict = {}
        for phase in Phase.objects.filter(semester=semester).select_related("developer"):
            allocated_map[phase.project_id] = allocated_map.get(phase.project_id, 0) + phase.effort_weeks()

        for project in ctx["projects"]:
            project.display_name = project.name_for_semester(semester)
            project.effort_resourced = resourced_map.get(project.pk, 0)
            project.effort_allocated = round(allocated_map.get(project.pk, 0), 2)
            project.effort_discrepancy = round(project.effort_resourced - project.effort_allocated, 2)
        return ctx


# ---------------------------------------------------------------------------
# Developer create / upload
# ---------------------------------------------------------------------------


def _get_or_create_tags(names):
    return [Tag.objects.get_or_create(name=n)[0] for n in names if n.strip()]


_email_validator = EmailValidator()


def _validate_email(value):
    """Return an error string, or None if valid."""
    if not value:
        return "email is required"
    try:
        _email_validator(value)
    except ValidationError:
        return f"invalid email '{value}'"
    return None


def _validate_name(value):
    if not value:
        return "name is required"
    return None


def _validate_effort(value):
    """Empty → valid (treated as 0). Non-empty must be a non-negative number."""
    if not value:
        return None
    try:
        f = float(value)
    except ValueError:
        return f"effort_available must be a number (got '{value}')"
    if f < 0:
        return f"effort_available must be zero or positive (got '{value}')"
    return None


def _validate_developer_rows(rows):
    errors = []
    for i, row in enumerate(rows, start=2):
        email_err = _validate_email(row.get("email", "").strip())
        if email_err:
            errors.append(f"Row {i}: {email_err}")
        name_err = _validate_name(row.get("name", "").strip())
        if name_err:
            errors.append(f"Row {i}: {name_err}")
        effort_err = _validate_effort(row.get("effort_available", "").strip())
        if effort_err:
            errors.append(f"Row {i}: {effort_err}")
    return errors


def _validate_project_rows(rows):
    errors = []
    for i, row in enumerate(rows, start=2):
        name_err = _validate_name(row.get("name", "").strip())
        if name_err:
            errors.append(f"Row {i}: {name_err}")
        effort_err = _validate_effort(row.get("effort_resourced", "").strip())
        if effort_err:
            errors.append(f"Row {i}: {effort_err}")
    return errors


def _validate_observer_rows(rows, valid_project_names):
    """Validate observer rows; valid_project_names is a set of known project names."""
    errors = []
    for i, row in enumerate(rows, start=2):
        email_err = _validate_email(row.get("email", "").strip())
        if email_err:
            errors.append(f"Row {i}: {email_err}")
        name_err = _validate_name(row.get("name", "").strip())
        if name_err:
            errors.append(f"Row {i}: {name_err}")
        access_names = [n.strip() for n in row.get("project_access", "").split(",") if n.strip()]
        unknown = [n for n in access_names if n not in valid_project_names]
        if unknown:
            errors.append(f"Row {i}: unknown project(s) in project_access: {', '.join(repr(n) for n in unknown)}")
    return errors


def _upload_error(request, redirect_name, errors):
    msg = "Upload failed — fix the following errors and try again:\n" + "\n".join(f"• {e}" for e in errors)
    messages.error(request, msg)
    return redirect(f"planning:{redirect_name}")


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
        effort_str = request.POST.get("effort_available", "").strip()
        if effort_str:
            try:
                effort = float(effort_str)
                sd, created = SemesterDeveloper.objects.get_or_create(
                    developer=profile, semester=Semester.get_current(),
                    defaults={"effort_available": effort},
                )
                if not created:
                    sd.effort_available = effort
                    sd.save(update_fields=["effort_available"])
            except ValueError:
                pass
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
        semester = Semester.get_current()
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
                effort_str = row.get("effort_available", "").strip()
                effort = float(effort_str) if effort_str else 0
                sd, created = SemesterDeveloper.objects.get_or_create(
                    developer=profile, semester=semester,
                    defaults={"effort_available": effort},
                )
                if not created:
                    sd.effort_available = effort
                    sd.save(update_fields=["effort_available"])
        messages.success(request, f"{len(rows)} developer(s) uploaded successfully.")
        return redirect("planning:developers")


# ---------------------------------------------------------------------------
# Project create / upload
# ---------------------------------------------------------------------------


class ProjectCreateView(RoleRequiredMixin, View):
    allowed_roles = (Role.ADMIN, Role.PM)

    def post(self, request, *args, **kwargs):
        name = request.POST.get("name", "").strip()
        if not name:
            return redirect("planning:projects")
        semester = Semester.get_current()
        stream_name = request.POST.get("stream", "").strip()
        stream = Stream.objects.get_or_create(name=stream_name)[0] if stream_name else None
        project = Project(stream=stream)
        project.save()
        ProjectSemesterName.objects.create(project=project, semester=semester, name=name)
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
    allowed_roles = (Role.ADMIN, Role.PM)

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
                stream_name = row.get("stream", "").strip()
                stream = Stream.objects.get_or_create(name=stream_name)[0] if stream_name else None
                project = Project(stream=stream)
                project.save()
                ProjectSemesterName.objects.create(project=project, semester=semester, name=name)
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


# ---------------------------------------------------------------------------
# Observer create
# ---------------------------------------------------------------------------


class ObserverCreateView(RoleRequiredMixin, View):
    allowed_roles = (Role.ADMIN, Role.PM)

    def post(self, request, *args, **kwargs):
        User = get_user_model()
        email = request.POST.get("email", "").strip()
        if not email:
            return redirect("planning:observers")
        user, _ = User.objects.get_or_create(
            email=email,
            defaults={
                "name": request.POST.get("name", "").strip(),
                "role": Role.OBSERVER,
                "organisation": request.POST.get("organisation", "").strip(),
                "emoji": request.POST.get("emoji", "").strip(),
            },
        )
        obs, _ = ObserverProfile.objects.get_or_create(user=user)
        project_pks = request.POST.getlist("project_access")
        if project_pks:
            obs.project_access.set(project_pks)
        return redirect("planning:observers")


# ---------------------------------------------------------------------------
# Leave page  (FR-14)
# ---------------------------------------------------------------------------


class LeaveView(RoleRequiredMixin, ListView):
    model = Leave
    template_name = "planning/leave.html"
    context_object_name = "leave_periods"
    allowed_roles = (Role.ADMIN, Role.PM, Role.DEVELOPER)

    def get_queryset(self):
        qs = Leave.objects.select_related("developer__user").order_by("start_date")
        user = self.request.user
        if user.role == Role.DEVELOPER and not user.is_superuser:
            try:
                qs = qs.filter(developer=user.developer_profile)
            except DeveloperProfile.DoesNotExist:
                qs = qs.none()
        if not self.request.GET.get("show_past"):
            qs = qs.filter(end_date__gte=datetime.date.today())
        return qs

    def get_context_data(self, **kwargs):
        ctx = super().get_context_data(**kwargs)
        user = self.request.user
        ctx["can_edit"] = user.role in (Role.ADMIN, Role.PM) or user.is_superuser
        ctx["is_developer"] = user.role == Role.DEVELOPER and not user.is_superuser
        ctx["show_past"] = bool(self.request.GET.get("show_past"))
        ctx["developers"] = DeveloperProfile.objects.select_related("user").order_by("user__name")
        if ctx["is_developer"]:
            try:
                ctx["my_developer_id"] = user.developer_profile.pk
            except DeveloperProfile.DoesNotExist:
                ctx["my_developer_id"] = None
        return ctx


class LeaveCreateView(RoleRequiredMixin, View):
    allowed_roles = (Role.ADMIN, Role.PM, Role.DEVELOPER)

    def post(self, request, *args, **kwargs):
        developer_id = request.POST.get("developer")
        start_date = request.POST.get("start_date")
        end_date = request.POST.get("end_date")
        user = request.user
        if user.role == Role.DEVELOPER and not user.is_superuser:
            try:
                developer_id = user.developer_profile.pk
            except DeveloperProfile.DoesNotExist:
                return HttpResponse(status=403)
        Leave.objects.create(
            developer_id=developer_id,
            start_date=start_date,
            end_date=end_date,
        )
        next_url = request.POST.get("next")
        return redirect(next_url) if next_url else redirect("planning:leave")


class LeaveDeleteView(RoleRequiredMixin, View):
    allowed_roles = (Role.ADMIN, Role.PM, Role.DEVELOPER)

    def post(self, request, pk, *args, **kwargs):
        leave = get_object_or_404(Leave, pk=pk)
        user = request.user
        if user.role == Role.DEVELOPER and not user.is_superuser:
            try:
                if leave.developer != user.developer_profile:
                    return HttpResponse(status=403)
            except DeveloperProfile.DoesNotExist:
                return HttpResponse(status=403)
        leave.delete()
        return redirect("planning:leave")


# ---------------------------------------------------------------------------
# Planning page  (FR-16)
# ---------------------------------------------------------------------------


class PlanningView(RoleRequiredMixin, TemplateView):
    template_name = "planning/planning.html"
    allowed_roles = (Role.ADMIN, Role.PM)

    def get_context_data(self, **kwargs):
        ctx = super().get_context_data(**kwargs)
        semester = Semester.get_current()

        weeks = _week_starts(semester.start_date, semester.end_date)

        tag_filter = self.request.GET.getlist("tags")
        dev_qs = (
            DeveloperProfile.objects
            .select_related("user")
            .prefetch_related("tags", "leave_periods")
            .order_by("user__name", "user__email")
        )
        if tag_filter:
            dev_qs = dev_qs.filter(tags__name__in=tag_filter).distinct()
        devs = list(dev_qs)

        if weeks:
            phases = list(
                Phase.objects.filter(
                    developer__in=devs,
                    start_date__lte=weeks[-1] + datetime.timedelta(days=6),
                    end_date__gte=weeks[0],
                ).select_related("developer", "project", "lane")
            )
        else:
            phases = []

        from collections import defaultdict

        # Fetch all lanes for these developers in the current semester
        lanes_qs = DeveloperLane.objects.filter(
            developer__in=devs, semester=semester,
        ).order_by("order", "pk")
        lanes_by_dev: dict = defaultdict(list)
        for lane in lanes_qs:
            lanes_by_dev[lane.developer_id].append(lane)

        # Group phases by lane pk
        phases_by_lane: dict = defaultdict(list)
        for phase in phases:
            phases_by_lane[phase.lane_id].append(phase)

        developer_rows = []
        for dev in devs:
            # Ensure at least one lane exists
            if not lanes_by_dev[dev.pk]:
                lane0, _ = DeveloperLane.objects.get_or_create(
                    developer=dev, semester=semester, order=0,
                )
                lanes_by_dev[dev.pk] = [lane0]

            # Build one leave cell per Leave period
            leave_cells = []
            if weeks:
                for leave in dev.leave_periods.all():
                    start_col, span = _coverage(leave.start_date, leave.end_date, weeks)
                    if start_col is not None:
                        leave_cells.append({
                            "col_start": start_col,
                            "col_end": start_col + span - 1,
                            "colspan": span,
                            "pk": leave.pk,
                            "start_date": leave.start_date,
                            "end_date": leave.end_date,
                        })

            dev_lanes = lanes_by_dev[dev.pk]
            lane_rows = []
            for lane in dev_lanes:
                phase_segments = []
                for phase in phases_by_lane.get(lane.pk, []):
                    start_col, span = _coverage(phase.start_date, phase.end_date, weeks)
                    if start_col is not None:
                        phase.display_name = phase.project.name_for_semester(semester)
                        phase.effort_display = phase.effort_weeks()
                        phase_segments.append((start_col, span, phase))
                cells = _build_lane_cells(len(weeks), phase_segments)
                lane_rows.append({
                    "lane": lane,
                    "cells": cells,
                    "is_empty": len(phase_segments) == 0,
                    "is_last": False,  # set below
                })
            if lane_rows:
                lane_rows[-1]["is_last"] = True

            developer_rows.append({
                "developer": dev,
                "lanes": lane_rows,
                "lane_count": len(lane_rows),
                "last_lane_pk": dev_lanes[-1].pk if dev_lanes else None,
                "leave_cells": leave_cells,
            })

        all_projects = list(Project.objects.prefetch_related("semester_names").all())
        for p in all_projects:
            p.display_name = p.name_for_semester(semester)

        ctx["weeks"] = weeks
        ctx["weeks_json"] = json.dumps([w.isoformat() for w in weeks])
        ctx["developer_rows"] = developer_rows
        ctx["semester"] = semester
        ctx["all_tags"] = Tag.objects.all()
        ctx["selected_tags"] = tag_filter
        ctx["can_edit"] = self.request.user.role in (Role.ADMIN, Role.PM) or self.request.user.is_superuser
        ctx["projects"] = all_projects
        ctx["developers"] = devs
        return ctx


# ---------------------------------------------------------------------------
# Phase create / delete  (FR-16)
# ---------------------------------------------------------------------------


class PhaseCreateView(RoleRequiredMixin, View):
    allowed_roles = (Role.ADMIN, Role.PM)

    def post(self, request, *args, **kwargs):
        developer_id = request.POST.get("developer")
        project_id = request.POST.get("project")
        start_date = request.POST.get("start_date")
        end_date = request.POST.get("end_date")
        effort_multiplier = float(request.POST.get("effort_multiplier", 1.0))
        semester = Semester.get_current()
        lane_pk = request.POST.get("lane_pk")
        if lane_pk:
            preferred_lane = get_object_or_404(DeveloperLane, pk=lane_pk)
        else:
            preferred_lane, _ = DeveloperLane.objects.get_or_create(
                developer_id=developer_id, semester=semester, order=0,
            )
        developer = get_object_or_404(DeveloperProfile, pk=developer_id)
        lane = _find_or_create_non_overlapping_lane(
            developer, semester,
            datetime.date.fromisoformat(start_date),
            datetime.date.fromisoformat(end_date),
            preferred_lane,
        )
        Phase.objects.create(
            developer_id=developer_id,
            project_id=project_id,
            semester=semester,
            lane=lane,
            start_date=start_date,
            end_date=end_date,
            effort_multiplier=effort_multiplier,
        )
        next_url = request.POST.get("next") or request.META.get("HTTP_REFERER", "/planning/planning/")
        return redirect(next_url)


class PhaseDeleteView(RoleRequiredMixin, View):
    allowed_roles = (Role.ADMIN, Role.PM)

    def post(self, request, pk, *args, **kwargs):
        phase = get_object_or_404(Phase, pk=pk)
        phase.delete()
        next_url = request.POST.get("next") or request.META.get("HTTP_REFERER", "/planning/planning/")
        return redirect(next_url)


class PhaseUpdateView(RoleRequiredMixin, View):
    allowed_roles = (Role.ADMIN, Role.PM)

    def post(self, request, pk, *args, **kwargs):
        phase = get_object_or_404(Phase, pk=pk)
        start_date = request.POST.get("start_date")
        end_date = request.POST.get("end_date")
        new_start = datetime.date.fromisoformat(start_date)
        new_end = datetime.date.fromisoformat(end_date)
        update_fields = ["start_date", "end_date"]
        lane_pk = request.POST.get("lane_pk")
        if lane_pk:
            preferred_lane = get_object_or_404(DeveloperLane, pk=lane_pk)
            phase.developer = preferred_lane.developer
            update_fields.append("developer_id")
        else:
            preferred_lane = phase.lane
        semester = phase.semester
        lane = _find_or_create_non_overlapping_lane(
            phase.developer, semester, new_start, new_end, preferred_lane,
            exclude_phase_pk=phase.pk,
        )
        phase.start_date = new_start
        phase.end_date = new_end
        phase.lane = lane
        update_fields.extend(["lane_id"])
        phase.save(update_fields=list(dict.fromkeys(update_fields)))
        return HttpResponse(status=204)


class LeaveUpdateView(RoleRequiredMixin, View):
    allowed_roles = (Role.ADMIN, Role.PM, Role.DEVELOPER)

    def post(self, request, pk, *args, **kwargs):
        leave = get_object_or_404(Leave, pk=pk)
        user = request.user
        if user.role == Role.DEVELOPER and not user.is_superuser:
            try:
                if leave.developer != user.developer_profile:
                    return HttpResponse(status=403)
            except DeveloperProfile.DoesNotExist:
                return HttpResponse(status=403)
        leave.start_date = datetime.date.fromisoformat(request.POST.get("start_date"))
        leave.end_date = datetime.date.fromisoformat(request.POST.get("end_date"))
        leave.save(update_fields=["start_date", "end_date"])
        next_url = request.POST.get("next")
        if next_url:
            return redirect(next_url)
        return HttpResponse(status=204)


class PhaseEditView(RoleRequiredMixin, View):
    allowed_roles = (Role.ADMIN, Role.PM)

    def post(self, request, pk, *args, **kwargs):
        phase = get_object_or_404(Phase, pk=pk)
        phase.project_id = request.POST.get("project")
        new_start = datetime.date.fromisoformat(request.POST.get("start_date"))
        new_end = datetime.date.fromisoformat(request.POST.get("end_date"))
        phase.effort_multiplier = float(request.POST.get("effort_multiplier", 1.0))
        lane = _find_or_create_non_overlapping_lane(
            phase.developer, phase.semester, new_start, new_end, phase.lane,
            exclude_phase_pk=phase.pk,
        )
        phase.start_date = new_start
        phase.end_date = new_end
        phase.lane = lane
        phase.save(update_fields=["project_id", "start_date", "end_date", "effort_multiplier", "lane_id"])
        next_url = request.POST.get("next") or request.META.get("HTTP_REFERER", "/planning/planning/")
        return redirect(next_url)


# ---------------------------------------------------------------------------
# Lane add / remove
# ---------------------------------------------------------------------------


class LaneAddView(RoleRequiredMixin, View):
    allowed_roles = (Role.ADMIN, Role.PM)

    def post(self, request, pk, *args, **kwargs):
        developer = get_object_or_404(DeveloperProfile, pk=pk)
        semester = Semester.get_current()
        from django.db.models import Max
        max_order = DeveloperLane.objects.filter(
            developer=developer, semester=semester,
        ).aggregate(Max("order"))["order__max"]
        new_order = (max_order + 1) if max_order is not None else 0
        DeveloperLane.objects.create(developer=developer, semester=semester, order=new_order)
        return HttpResponse(status=204)


class LaneRemoveView(RoleRequiredMixin, View):
    allowed_roles = (Role.ADMIN, Role.PM)

    def post(self, request, pk, *args, **kwargs):
        lane = get_object_or_404(DeveloperLane, pk=pk)
        if lane.phases.exists():
            return HttpResponse(status=400)
        other_lanes = DeveloperLane.objects.filter(
            developer=lane.developer, semester=lane.semester,
        ).exclude(pk=pk)
        if not other_lanes.exists():
            return HttpResponse(status=400)
        lane.delete()
        return HttpResponse(status=204)


# ---------------------------------------------------------------------------
# Schedule page  (FR-17)
# ---------------------------------------------------------------------------


class ScheduleView(RoleRequiredMixin, TemplateView):
    template_name = "planning/schedule.html"
    allowed_roles = (Role.ADMIN, Role.PM)

    def get_context_data(self, **kwargs):
        ctx = super().get_context_data(**kwargs)
        semester = Semester.get_current()

        weeks = _week_starts(semester.start_date, semester.end_date)

        tag_filter = self.request.GET.getlist("tags")

        if weeks:
            phase_qs = Phase.objects.filter(
                start_date__lte=weeks[-1] + datetime.timedelta(days=6),
                end_date__gte=weeks[0],
            ).select_related("developer__user", "project")
            if tag_filter:
                phase_qs = phase_qs.filter(project__tags__name__in=tag_filter).distinct()
            phases = list(phase_qs)
        else:
            phases = []

        from collections import defaultdict
        project_dev_phases: dict = defaultdict(lambda: defaultdict(list))
        project_ids = set()
        for phase in phases:
            project_dev_phases[phase.project_id][phase.developer_id].append(phase)
            project_ids.add(phase.project_id)

        projects = list(
            Project.objects.filter(pk__in=project_ids)
            .prefetch_related("semester_names")
            .order_by("id")
        )

        project_rows = []
        for project in projects:
            project.display_name = project.name_for_semester(semester)
            dev_phases_map = project_dev_phases[project.pk]
            dev_profiles = list(
                DeveloperProfile.objects.filter(pk__in=dev_phases_map.keys())
                .select_related("user")
                .order_by("user__name")
            )
            layers = []
            for dev in dev_profiles:
                phase_segments = []
                for phase in dev_phases_map[dev.pk]:
                    start_col, span = _coverage(phase.start_date, phase.end_date, weeks)
                    if start_col is not None:
                        phase.display_name = project.display_name
                        phase.effort_display = phase.effort_weeks()
                        phase_segments.append((start_col, span, phase))

                phase_at = {s: (s, sp, ph) for s, sp, ph in sorted(phase_segments, key=lambda x: x[0])}
                dev_cells = []
                col = 0
                while col < len(weeks):
                    if col in phase_at:
                        s, sp, ph = phase_at[col]
                        dev_cells.append({"type": "phase", "colspan": sp, "phase": ph})
                        col += sp
                    else:
                        next_p = min((s for s in phase_at if s > col), default=len(weeks))
                        dev_cells.append({"type": "empty", "colspan": next_p - col, "phase": None})
                        col = next_p
                if dev_cells:
                    layers.append({"developer": dev, "cells": dev_cells})

            project_rows.append({
                "project": project,
                "layers": layers,
                "layer_count": max(1, len(layers)),
            })

        ctx["weeks"] = weeks
        ctx["project_rows"] = project_rows
        ctx["semester"] = semester
        ctx["all_tags"] = Tag.objects.all()
        ctx["selected_tags"] = tag_filter
        return ctx


# ---------------------------------------------------------------------------
# Developer edit / delete
# ---------------------------------------------------------------------------


class DeveloperUpdateView(RoleRequiredMixin, View):
    allowed_roles = (Role.ADMIN, Role.PM)

    def post(self, request, pk, *args, **kwargs):
        profile = get_object_or_404(DeveloperProfile, pk=pk)
        user = profile.user
        user.name = request.POST.get("name", "").strip()
        user.organisation = request.POST.get("organisation", "").strip()
        user.emoji = request.POST.get("emoji", "").strip()
        user.save(update_fields=["name", "organisation", "emoji"])
        tag_names = request.POST.getlist("tags")
        profile.tags.set(_get_or_create_tags(tag_names))
        effort_str = request.POST.get("effort_available", "").strip()
        if effort_str:
            try:
                effort = float(effort_str)
                sd, created = SemesterDeveloper.objects.get_or_create(
                    developer=profile, semester=Semester.get_current(),
                    defaults={"effort_available": effort},
                )
                if not created:
                    sd.effort_available = effort
                    sd.save(update_fields=["effort_available"])
            except ValueError:
                pass
        return redirect("planning:developers")


class DeveloperDeleteView(RoleRequiredMixin, View):
    allowed_roles = (Role.ADMIN, Role.PM)

    def post(self, request, pk, *args, **kwargs):
        profile = get_object_or_404(DeveloperProfile, pk=pk)
        user = profile.user
        profile.delete()
        user.delete()
        return HttpResponse(status=204)


# ---------------------------------------------------------------------------
# Project edit / delete
# ---------------------------------------------------------------------------


class ProjectUpdateView(RoleRequiredMixin, View):
    allowed_roles = (Role.ADMIN, Role.PM)

    def post(self, request, pk, *args, **kwargs):
        project = get_object_or_404(Project, pk=pk)
        semester = Semester.get_current()
        name = request.POST.get("name", "").strip()
        if name:
            psn, _ = ProjectSemesterName.objects.get_or_create(project=project, semester=semester)
            psn.name = name
            psn.save(update_fields=["name"])
        stream_name = request.POST.get("stream", "").strip()
        project.stream = Stream.objects.get_or_create(name=stream_name)[0] if stream_name else None
        project.save(update_fields=["stream"])
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
    allowed_roles = (Role.ADMIN, Role.PM)

    def post(self, request, pk, *args, **kwargs):
        project = get_object_or_404(Project, pk=pk)
        project.delete()
        return HttpResponse(status=204)


# ---------------------------------------------------------------------------
# Observer edit / delete
# ---------------------------------------------------------------------------


class ObserverUpdateView(RoleRequiredMixin, View):
    allowed_roles = (Role.ADMIN, Role.PM)

    def post(self, request, pk, *args, **kwargs):
        profile = get_object_or_404(ObserverProfile, pk=pk)
        user = profile.user
        user.name = request.POST.get("name", "").strip()
        user.organisation = request.POST.get("organisation", "").strip()
        user.emoji = request.POST.get("emoji", "").strip()
        user.save(update_fields=["name", "organisation", "emoji"])
        project_pks = request.POST.getlist("project_access")
        profile.project_access.set(project_pks)
        return redirect("planning:observers")


class ObserverDeleteView(RoleRequiredMixin, View):
    allowed_roles = (Role.ADMIN, Role.PM)

    def post(self, request, pk, *args, **kwargs):
        profile = get_object_or_404(ObserverProfile, pk=pk)
        user = profile.user
        profile.delete()
        user.delete()
        return HttpResponse(status=204)
