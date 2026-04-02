import datetime
import json

from django.contrib.auth.mixins import LoginRequiredMixin
from django.core.exceptions import PermissionDenied
from django.http import HttpResponse
from django.shortcuts import get_object_or_404, redirect
from django.views import View
from django.views.generic import ListView, TemplateView

from apps.users.models import Role

from .models import (
    DeveloperProfile,
    Leave,
    ObserverProfile,
    Phase,
    Project,
    Semester,
    SemesterDeveloper,
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
        ctx["can_edit"] = self.request.user.role in (Role.ADMIN, Role.PM)

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
        for project in ctx["projects"]:
            project.display_name = project.name_for_semester(semester)
        return ctx


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
                ).select_related("developer", "project")
            )
        else:
            phases = []

        from collections import defaultdict
        dev_phases: dict = defaultdict(list)
        for phase in phases:
            dev_phases[phase.developer_id].append(phase)

        developer_rows = []
        for dev in devs:
            # Build one leave cell per Leave period so each carries its pk and dates.
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

            phase_segments = []
            for phase in dev_phases.get(dev.pk, []):
                start_col, span = _coverage(phase.start_date, phase.end_date, weeks)
                if start_col is not None:
                    phase.display_name = phase.project.name_for_semester(semester)
                    phase.effort_display = phase.effort_weeks()
                    phase_segments.append((start_col, span, phase))

            # Pass an empty leave set — leave is now rendered as a separate overlay.
            layers = _build_timeline_layers(len(weeks), phase_segments, set())
            developer_rows.append({
                "developer": dev,
                "layers": layers,
                "layer_count": len(layers),
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
        Phase.objects.create(
            developer_id=developer_id,
            project_id=project_id,
            semester=semester,
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
        phase.start_date = datetime.date.fromisoformat(start_date)
        phase.end_date = datetime.date.fromisoformat(end_date)
        phase.save(update_fields=["start_date", "end_date"])
        return HttpResponse(status=204)


class LeaveUpdateView(RoleRequiredMixin, View):
    allowed_roles = (Role.ADMIN, Role.PM)

    def post(self, request, pk, *args, **kwargs):
        leave = get_object_or_404(Leave, pk=pk)
        leave.start_date = datetime.date.fromisoformat(request.POST.get("start_date"))
        leave.end_date = datetime.date.fromisoformat(request.POST.get("end_date"))
        leave.save(update_fields=["start_date", "end_date"])
        return HttpResponse(status=204)


class PhaseEditView(RoleRequiredMixin, View):
    allowed_roles = (Role.ADMIN, Role.PM)

    def post(self, request, pk, *args, **kwargs):
        phase = get_object_or_404(Phase, pk=pk)
        phase.project_id = request.POST.get("project")
        phase.start_date = datetime.date.fromisoformat(request.POST.get("start_date"))
        phase.end_date = datetime.date.fromisoformat(request.POST.get("end_date"))
        phase.effort_multiplier = float(request.POST.get("effort_multiplier", 1.0))
        phase.save(update_fields=["project_id", "start_date", "end_date", "effort_multiplier"])
        next_url = request.POST.get("next") or request.META.get("HTTP_REFERER", "/planning/planning/")
        return redirect(next_url)


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
