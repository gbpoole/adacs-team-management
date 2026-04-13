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

from ._mixins import PMOrObserverMixin
from ._mixins import _is_semester_observer
from ._semester import get_selected_semester
from ._timeline import _coverage
from ._timeline import _week_starts


class ScheduleView(PMOrObserverMixin, TemplateView):
    template_name = "planning/schedule.html"

    def get_context_data(self, **kwargs):
        ctx = super().get_context_data(**kwargs)
        user = self.request.user
        semester = get_selected_semester(self.request)

        weeks = _week_starts(semester.start_date, semester.end_date)

        is_observer = _is_semester_observer(user, semester) and not user.is_superuser and user.role != Role.PM

        # Determine accessible project PKs for observers (direct + via stream access)
        accessible_project_pks = None
        if is_observer:
            from apps.planning.models import SemesterObserver
            obs = SemesterObserver.objects.filter(user=user, semester=semester).first()
            if obs:
                accessible_project_pks = set(
                    obs.project_access.values_list("pk", flat=True)
                )
                accessible_project_pks |= set(
                    Project.objects.filter(
                        streams__in=obs.stream_access.all()
                    ).values_list("pk", flat=True)
                )
            else:
                accessible_project_pks = set()

        tag_filter = [] if is_observer else self.request.GET.getlist("tags")
        stream_filter = [] if is_observer else self.request.GET.getlist("streams")

        if weeks:
            phase_qs = Phase.objects.filter(
                start_date__lte=weeks[-1] + datetime.timedelta(days=6),
                end_date__gte=weeks[0],
            ).select_related("developer__user", "project").prefetch_related("developer__leave_periods")
            if tag_filter:
                phase_qs = phase_qs.filter(project__tags__name__in=tag_filter).distinct()
            if stream_filter:
                phase_qs = phase_qs.filter(project__streams__name__in=stream_filter).distinct()
            phases = list(phase_qs)
        else:
            phases = []

        project_dev_phases: dict = defaultdict(lambda: defaultdict(list))
        for phase in phases:
            project_dev_phases[phase.project_id][phase.developer_id].append(phase)

        project_qs = Project.objects.prefetch_related("semester_names").order_by("id")
        if tag_filter:
            project_qs = project_qs.filter(tags__name__in=tag_filter).distinct()
        if stream_filter:
            project_qs = project_qs.filter(streams__name__in=stream_filter).distinct()
        if is_observer and accessible_project_pks is not None:
            project_qs = project_qs.filter(pk__in=accessible_project_pks)
        projects = list(project_qs)

        resourced_map = {
            pk: float(new + carryover)
            for pk, new, carryover in ProjectAllocation.objects.filter(semester=semester)
            .values_list("project_id", "weeks_new", "weeks_carryover")
        }
        allocated_map: dict = {}
        for phase in (
            Phase.objects.filter(semester=semester)
            .select_related("developer")
            .prefetch_related("developer__leave_periods")
        ):
            allocated_map[phase.project_id] = allocated_map.get(phase.project_id, 0) + phase.effort_weeks()

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
                        phase.effort_unfilled_pct = round((1 - phase.effort_multiplier) * 100, 1)
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

            effort_resourced = resourced_map.get(project.pk, 0)
            effort_allocated = round(allocated_map.get(project.pk, 0), 2)
            unscheduled = round(effort_resourced - effort_allocated, 2)

            project_rows.append({
                "project": project,
                "layers": layers,
                "layer_count": max(1, len(layers)),
                "status_rowspan": len(layers) + 1,
                "unscheduled_weeks": unscheduled,
            })

        ctx["weeks"] = weeks
        ctx["project_rows"] = project_rows
        ctx["semester"] = semester
        ctx["is_observer"] = is_observer
        ctx["all_tags"] = Tag.objects.all() if not is_observer else []
        ctx["all_streams"] = Stream.objects.all() if not is_observer else []
        ctx["selected_tags"] = tag_filter
        ctx["selected_streams"] = stream_filter
        return ctx
