import datetime

from django.contrib import messages
from django.http import HttpResponse
from django.shortcuts import get_object_or_404
from django.shortcuts import redirect
from django.views import View

from apps.planning.models import DeveloperLane
from apps.planning.models import DeveloperProfile
from apps.planning.models import Phase
from apps.planning.models import _create_next_lane
from apps.planning.models import _delete_empty_lane
from apps.planning.models import _find_or_create_non_overlapping_lane
from apps.users.models import Role

from ._mixins import RoleRequiredMixin
from ._mixins import _get_next_url
from ._semester import get_selected_semester


class PhaseCreateView(RoleRequiredMixin, View):
    allowed_roles = (Role.PM,)

    def post(self, request, *args, **kwargs):
        developer_id = request.POST.get("developer")
        project_id = request.POST.get("project")
        next_url = _get_next_url(request)
        try:
            start_date = datetime.date.fromisoformat(request.POST.get("start_date", ""))
            end_date = datetime.date.fromisoformat(request.POST.get("end_date", ""))
            effort_multiplier = float(request.POST.get("effort_multiplier", 1.0))
        except ValueError:
            messages.error(request, "Invalid date or effort value.")
            return redirect(next_url)
        if end_date < start_date:
            messages.error(request, "End date must not be before start date.")
            return redirect(next_url)
        semester = get_selected_semester(request)
        developer = get_object_or_404(DeveloperProfile, pk=developer_id)
        lane_pk = request.POST.get("lane_pk")
        if lane_pk and lane_pk != "new":
            preferred_lane = get_object_or_404(DeveloperLane, pk=lane_pk)
        else:
            preferred_lane = _create_next_lane(developer, semester)
        lane = _find_or_create_non_overlapping_lane(
            developer,
            semester,
            start_date,
            end_date,
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
        return redirect(next_url)


class PhaseDeleteView(RoleRequiredMixin, View):
    allowed_roles = (Role.PM,)

    def post(self, request, pk, *args, **kwargs):
        phase = get_object_or_404(Phase, pk=pk)
        lane = phase.lane
        phase.delete()
        _delete_empty_lane(lane)
        return redirect(_get_next_url(request))


class PhaseUpdateView(RoleRequiredMixin, View):
    allowed_roles = (Role.PM,)

    def post(self, request, pk, *args, **kwargs):
        phase = get_object_or_404(Phase, pk=pk)
        old_lane = phase.lane
        try:
            new_start = datetime.date.fromisoformat(request.POST.get("start_date", ""))
            new_end = datetime.date.fromisoformat(request.POST.get("end_date", ""))
        except ValueError:
            return HttpResponse(status=400)
        if new_end < new_start:
            return HttpResponse(status=400)
        update_fields = ["start_date", "end_date"]
        lane_pk = request.POST.get("lane_pk")
        if lane_pk == "new":
            developer = get_object_or_404(
                DeveloperProfile, pk=request.POST.get("developer_pk"),
            )
            preferred_lane = _create_next_lane(developer, phase.semester)
            phase.developer = developer
            update_fields.append("developer_id")
        elif lane_pk:
            preferred_lane = get_object_or_404(DeveloperLane, pk=lane_pk)
            phase.developer = preferred_lane.developer
            update_fields.append("developer_id")
        else:
            preferred_lane = phase.lane
        lane = _find_or_create_non_overlapping_lane(
            phase.developer,
            phase.semester,
            new_start,
            new_end,
            preferred_lane,
            exclude_phase_pk=phase.pk,
        )
        phase.start_date = new_start
        phase.end_date = new_end
        phase.lane = lane
        update_fields.append("lane_id")
        phase.save(update_fields=list(dict.fromkeys(update_fields)))
        if lane != old_lane:
            _delete_empty_lane(old_lane)
        return HttpResponse(status=204)


class PhaseEditView(RoleRequiredMixin, View):
    allowed_roles = (Role.PM,)

    def post(self, request, pk, *args, **kwargs):
        phase = get_object_or_404(Phase, pk=pk)
        old_lane = phase.lane
        phase.project_id = request.POST.get("project")
        try:
            new_start = datetime.date.fromisoformat(request.POST.get("start_date", ""))
            new_end = datetime.date.fromisoformat(request.POST.get("end_date", ""))
            phase.effort_multiplier = float(request.POST.get("effort_multiplier", 1.0))
        except (ValueError, TypeError):
            messages.error(request, "Invalid date or effort value.")
            return redirect(_get_next_url(request))
        if new_end < new_start:
            messages.error(request, "End date must not be before start date.")
            return redirect(_get_next_url(request))
        new_developer_id = request.POST.get("developer")
        update_fields = [
            "project_id",
            "start_date",
            "end_date",
            "effort_multiplier",
            "lane_id",
        ]
        try:
            new_developer_id_int = int(new_developer_id) if new_developer_id else None
        except (ValueError, TypeError):
            messages.error(request, "Invalid developer.")
            return redirect(_get_next_url(request))
        if new_developer_id_int and new_developer_id_int != phase.developer_id:
            phase.developer = get_object_or_404(
                DeveloperProfile, pk=new_developer_id_int,
            )
            update_fields.append("developer_id")
            # New developer — preferred lane is the first lane for them in this semester
            preferred_lane, _ = DeveloperLane.objects.get_or_create(
                developer=phase.developer,
                semester=phase.semester,
                order=0,
            )
        else:
            preferred_lane = phase.lane
        lane = _find_or_create_non_overlapping_lane(
            phase.developer,
            phase.semester,
            new_start,
            new_end,
            preferred_lane,
            exclude_phase_pk=phase.pk,
        )
        phase.start_date = new_start
        phase.end_date = new_end
        phase.lane = lane
        phase.save(update_fields=list(dict.fromkeys(update_fields)))
        if lane != old_lane:
            _delete_empty_lane(old_lane)
        return redirect(_get_next_url(request))
