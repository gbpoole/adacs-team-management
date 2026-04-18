import datetime
from collections import defaultdict

from django.views.generic import TemplateView

from apps.planning.models import DeveloperProfile
from apps.planning.models import Phase
from apps.planning.models import Project
from apps.planning.models import ProjectAllocation
from apps.planning.models import Stream
from apps.planning.models import Tag
from apps.users.models import Role

from django.contrib.auth.mixins import LoginRequiredMixin

from ._mixins import _has_restricted_view_access
from ._mixins import _visible_project_ids_for_user
from ._semester import get_selected_semester
from ._timeline import _coverage
from ._timeline import _week_starts


class ScheduleView(LoginRequiredMixin, TemplateView):
    template_name = "planning/schedule.html"

    def get_context_data(self, **kwargs):
        ctx = super().get_context_data(**kwargs)
        user = self.request.user
        semester = get_selected_semester(self.request)

        weeks = _week_starts(semester.start_date, semester.end_date)

        is_observer = (
            _has_restricted_view_access(user, semester)
            and not user.is_superuser
            and user.role != Role.PM
        )

        visible_project_ids = _visible_project_ids_for_user(user, semester)

        tag_filter = [] if is_observer else self.request.GET.getlist("tags")
        stream_filter = [] if is_observer else self.request.GET.getlist("streams")

        today = datetime.date.today()
        today_col = next(
            (i for i, w in enumerate(weeks) if w <= today < w + datetime.timedelta(days=7)),
            -1,
        )
        today_day_px = today.weekday() * 64 // 7
        today_left_px = today_col * 64 + today_day_px if today_col >= 0 else -1

        if weeks:
            phase_qs = (
                Phase.objects.filter(
                    start_date__lte=weeks[-1] + datetime.timedelta(days=6),
                    end_date__gte=weeks[0],
                )
                .select_related("developer__user", "project")
                .prefetch_related("developer__leave_periods")
            )
            if visible_project_ids is not None:
                phase_qs = phase_qs.filter(project_id__in=visible_project_ids)
            if tag_filter:
                phase_qs = phase_qs.filter(
                    project__tags__name__in=tag_filter,
                ).distinct()
            if stream_filter:
                phase_qs = phase_qs.filter(
                    project__streams__name__in=stream_filter,
                ).distinct()
            phases = list(phase_qs)
        else:
            phases = []

        project_dev_phases: dict = defaultdict(lambda: defaultdict(list))
        for phase in phases:
            project_dev_phases[phase.project_id][phase.developer_id].append(phase)

        project_qs = Project.objects.prefetch_related("semester_names").order_by("id")
        if visible_project_ids is not None:
            project_qs = project_qs.filter(pk__in=visible_project_ids)
        if tag_filter:
            project_qs = project_qs.filter(tags__name__in=tag_filter).distinct()
        if stream_filter:
            project_qs = project_qs.filter(streams__name__in=stream_filter).distinct()
        projects = list(project_qs)

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

        project_rows = []
        for project in projects:
            project.display_name = project.name_for_semester(semester)
            dev_phases_map = project_dev_phases[project.pk]
            dev_profiles = list(
                DeveloperProfile.objects.filter(pk__in=dev_phases_map.keys())
                .select_related("user")
                .order_by("user__name"),
            )
            layers = []
            for dev in dev_profiles:
                phase_segments = []
                for phase in dev_phases_map[dev.pk]:
                    start_col, span = _coverage(phase.start_date, phase.end_date, weeks)
                    if start_col is not None:
                        phase.display_name = project.display_name
                        phase.effort_display = phase.effort_weeks()
                        phase.effort_unfilled_pct = round(
                            (1 - phase.effort_multiplier) * 100,
                            1,
                        )
                        phase_segments.append((start_col, span, phase))

                phase_at = {
                    s: (s, sp, ph)
                    for s, sp, ph in sorted(phase_segments, key=lambda x: x[0])
                }
                dev_cells = []
                col = 0
                while col < len(weeks):
                    if col in phase_at:
                        s, sp, ph = phase_at[col]
                        cell_today_px = (today_left_px - s * 64) if today_col >= 0 and s <= today_col <= s + sp - 1 else -1
                        dev_cells.append({"type": "phase", "colspan": sp, "phase": ph, "col_start": s, "col_end": s + sp - 1, "today_px": cell_today_px})
                        col += sp
                    else:
                        next_p = min(
                            (s for s in phase_at if s > col),
                            default=len(weeks),
                        )
                        cell_today_px = (today_left_px - col * 64) if today_col >= 0 and col <= today_col <= next_p - 1 else -1
                        dev_cells.append(
                            {"type": "empty", "colspan": next_p - col, "phase": None, "col_start": col, "col_end": next_p - 1, "today_px": cell_today_px},
                        )
                        col = next_p
                if dev_cells:
                    layers.append({"developer": dev, "cells": dev_cells})

            effort_resourced = resourced_map.get(project.pk, 0)
            effort_allocated = round(allocated_map.get(project.pk, 0), 2)
            unscheduled = round(effort_resourced - effort_allocated, 2)

            project_rows.append(
                {
                    "project": project,
                    "layers": layers,
                    "layer_count": max(1, len(layers)),
                    "status_rowspan": len(layers) + 1,
                    "unscheduled_weeks": unscheduled,
                },
            )

        ctx["weeks"] = weeks
        ctx["today_col"] = today_col
        ctx["today_day_px"] = today_day_px
        ctx["today_left_px"] = today_left_px
        ctx["project_rows"] = project_rows
        ctx["semester"] = semester
        ctx["is_observer"] = is_observer
        ctx["all_tags"] = Tag.objects.all() if not is_observer else []
        ctx["all_streams"] = Stream.objects.all() if not is_observer else []
        ctx["selected_tags"] = tag_filter
        ctx["selected_streams"] = stream_filter
        return ctx
