import datetime

from django.contrib import messages
from django.http import HttpResponse
from django.shortcuts import get_object_or_404
from django.views import View

from apps.planning.forms import PhaseCreateForm
from apps.planning.forms import PhaseEditForm
from apps.planning.models import DeveloperLane
from apps.planning.models import DeveloperProfile
from apps.planning.models import Phase
from apps.planning.models import _create_next_lane
from apps.planning.models import _delete_empty_lane
from apps.planning.models import _find_or_create_non_overlapping_lane
from apps.users.models import Role

from ._mixins import RoleRequiredMixin
from ._mixins import _get_next_url
from ._mixins import _redirect_or_hx_redirect
from ._semester import get_selected_semester


class PhaseCreateView(RoleRequiredMixin, View):
    allowed_roles = (Role.PM,)

    def post(self, request, *args, **kwargs):
        next_url = _get_next_url(request)
        form = PhaseCreateForm(request.POST)
        if not form.is_valid():
            for field_errors in form.errors.values():
                for err in field_errors:
                    messages.error(request, err)
            return _redirect_or_hx_redirect(request, next_url)
        cleaned = form.cleaned_data
        semester = get_selected_semester(request)
        developer = cleaned["developer"]
        project = cleaned["project"]
        lane_pk = cleaned.get("lane_pk")
        if lane_pk and lane_pk != "new":
            preferred_lane = get_object_or_404(DeveloperLane, pk=lane_pk)
        else:
            preferred_lane = _create_next_lane(developer, semester)
        lane = _find_or_create_non_overlapping_lane(
            developer,
            semester,
            cleaned["start_date"],
            cleaned["end_date"],
            preferred_lane,
        )
        Phase.objects.create(
            developer=developer,
            project=project,
            semester=semester,
            lane=lane,
            start_date=cleaned["start_date"],
            end_date=cleaned["end_date"],
            effort_multiplier=cleaned["effort_multiplier"],
        )
        return _redirect_or_hx_redirect(request, next_url)


class PhaseDeleteView(RoleRequiredMixin, View):
    allowed_roles = (Role.PM,)

    def post(self, request, pk, *args, **kwargs):
        phase = get_object_or_404(Phase, pk=pk)
        lane = phase.lane
        phase.delete()
        _delete_empty_lane(lane)
        return _redirect_or_hx_redirect(request, _get_next_url(request))


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
        next_url = _get_next_url(request)
        form = PhaseEditForm(request.POST)
        if not form.is_valid():
            for field_errors in form.errors.values():
                for err in field_errors:
                    messages.error(request, err)
            return _redirect_or_hx_redirect(request, next_url)
        cleaned = form.cleaned_data
        phase.project = cleaned["project"]
        phase.effort_multiplier = cleaned["effort_multiplier"]
        new_start = cleaned["start_date"]
        new_end = cleaned["end_date"]
        new_developer = cleaned["developer"]

        if new_developer.pk != phase.developer_id:
            phase.developer = new_developer
            preferred_lane, _ = DeveloperLane.objects.get_or_create(
                developer=phase.developer,
                semester=phase.semester,
                order=0,
            )
            update_fields = [
                "project_id",
                "start_date",
                "end_date",
                "effort_multiplier",
                "lane_id",
                "developer_id",
            ]
        else:
            preferred_lane = phase.lane
            update_fields = [
                "project_id",
                "start_date",
                "end_date",
                "effort_multiplier",
                "lane_id",
            ]

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
        return _redirect_or_hx_redirect(request, next_url)
