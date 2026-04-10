import datetime
import json
from collections import defaultdict

from django.views.generic import TemplateView

from apps.planning.models import DeveloperLane
from apps.planning.models import DeveloperProfile
from apps.planning.models import ObserverProfile
from apps.planning.models import Phase
from apps.planning.models import Project
from apps.planning.models import Semester
from apps.planning.models import Stream
from apps.planning.models import Tag
from apps.users.models import Role

from ._mixins import RoleRequiredMixin
from ._timeline import _build_lane_cells
from ._timeline import _coverage
from ._timeline import _week_starts


class PlanningView(RoleRequiredMixin, TemplateView):
    template_name = "planning/planning.html"
    allowed_roles = (Role.ADMIN, Role.PM, Role.OBSERVER)

    def get_context_data(self, **kwargs):
        ctx = super().get_context_data(**kwargs)
        user = self.request.user
        semester = Semester.get_current()

        weeks = _week_starts(semester.start_date, semester.end_date)

        is_observer = user.role == Role.OBSERVER and not user.is_superuser

        # Determine accessible project PKs for observers (direct + via stream access)
        accessible_project_pks = None
        if is_observer:
            try:
                profile = user.observer_profile
                accessible_project_pks = set(
                    profile.project_access.values_list("pk", flat=True)
                )
                accessible_project_pks |= set(
                    Project.objects.filter(
                        streams__in=profile.stream_access.all()
                    ).values_list("pk", flat=True)
                )
            except ObserverProfile.DoesNotExist:
                accessible_project_pks = set()

        tag_filter = [] if is_observer else self.request.GET.getlist("tags")
        stream_filter = [] if is_observer else self.request.GET.getlist("streams")

        dev_qs = (
            DeveloperProfile.objects
            .select_related("user")
            .prefetch_related("tags", "leave_periods")
            .order_by("user__name", "user__email")
        )
        if tag_filter:
            dev_qs = dev_qs.filter(tags__name__in=tag_filter).distinct()
        if stream_filter:
            dev_qs = dev_qs.filter(
                phases__project__streams__name__in=stream_filter,
                phases__semester=semester,
            ).distinct()
        devs = list(dev_qs)

        if weeks:
            phases = list(
                Phase.objects.filter(
                    developer__in=devs,
                    start_date__lte=weeks[-1] + datetime.timedelta(days=6),
                    end_date__gte=weeks[0],
                ).select_related("developer", "project", "lane")
                .prefetch_related("developer__leave_periods")
            )
        else:
            phases = []

        # For observers, restrict phases to accessible projects and devs to those with visible phases
        if is_observer and accessible_project_pks is not None:
            phases = [p for p in phases if p.project_id in accessible_project_pks]
            dev_pks_with_phases = {p.developer_id for p in phases}
            devs = [d for d in devs if d.pk in dev_pks_with_phases]

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
            effort_by_col = [0.0] * len(weeks)
            for lane in dev_lanes:
                phase_segments = []
                for phase in phases_by_lane.get(lane.pk, []):
                    start_col, span = _coverage(phase.start_date, phase.end_date, weeks)
                    if start_col is not None:
                        phase.display_name = phase.project.name_for_semester(semester)
                        phase.effort_display = phase.effort_weeks()
                        phase.effort_unfilled_pct = round((1 - phase.effort_multiplier) * 100, 1)
                        phase_segments.append((start_col, span, phase))
                        for col in range(start_col, start_col + span):
                            effort_by_col[col] += phase.effort_multiplier
                cells = _build_lane_cells(len(weeks), phase_segments)
                lane_rows.append({
                    "lane": lane,
                    "cells": cells,
                    "is_empty": len(phase_segments) == 0,
                    "is_last": False,  # set below
                })
            if lane_rows:
                lane_rows[-1]["is_last"] = True

            overallocated_cols = sorted(
                col for col, effort in enumerate(effort_by_col) if effort > 1.0
            )
            developer_rows.append({
                "developer": dev,
                "lanes": lane_rows,
                "lane_count": len(lane_rows),
                "leave_cells": leave_cells,
                "overallocated_cols": overallocated_cols,
            })

        all_projects = list(Project.objects.prefetch_related("semester_names").all())
        for p in all_projects:
            p.display_name = p.name_for_semester(semester)

        ctx["weeks"] = weeks
        ctx["weeks_json"] = json.dumps([w.isoformat() for w in weeks])
        ctx["developer_rows"] = developer_rows
        ctx["semester"] = semester
        ctx["is_observer"] = is_observer
        ctx["all_tags"] = Tag.objects.all() if not is_observer else []
        ctx["all_streams"] = Stream.objects.all() if not is_observer else []
        ctx["selected_tags"] = tag_filter
        ctx["selected_streams"] = stream_filter
        ctx["can_edit"] = user.role in (Role.ADMIN, Role.PM) or user.is_superuser
        ctx["projects"] = all_projects
        ctx["developers"] = devs
        return ctx
