import datetime

from django.contrib import messages
from django.http import HttpResponse
from django.shortcuts import get_object_or_404
from django.shortcuts import redirect
from django.urls import reverse
from django.utils.http import url_has_allowed_host_and_scheme
from django.views import View
from django.views.generic import ListView

from apps.planning.models import DeveloperProfile
from apps.planning.models import Leave
from apps.users.models import Role

from ._mixins import PMOrHasDeveloperProfileMixin
from ._mixins import _get_next_url


def _check_leave_ownership(user, leave):
    if user.role != Role.PM and not user.is_superuser:
        try:
            if leave.developer != user.developer_profile:
                return HttpResponse(status=403)
        except DeveloperProfile.DoesNotExist:
            return HttpResponse(status=403)
    return None


class LeaveView(PMOrHasDeveloperProfileMixin, ListView):
    model = Leave
    template_name = "planning/leave.html"
    context_object_name = "leave_periods"

    def get_queryset(self):
        qs = Leave.objects.select_related("developer__user").order_by("start_date")
        user = self.request.user
        if user.role != Role.PM and not user.is_superuser:
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
        ctx["can_edit"] = user.role == Role.PM or user.is_superuser
        ctx["is_developer"] = user.role != Role.PM and not user.is_superuser
        ctx["show_past"] = bool(self.request.GET.get("show_past"))
        ctx["developers"] = DeveloperProfile.objects.select_related("user").order_by("user__name")
        if ctx["is_developer"]:
            try:
                ctx["my_developer_id"] = user.developer_profile.pk
            except DeveloperProfile.DoesNotExist:
                ctx["my_developer_id"] = None
        return ctx


class LeaveCreateView(PMOrHasDeveloperProfileMixin, View):
    def post(self, request, *args, **kwargs):
        developer_id = request.POST.get("developer")
        user = request.user
        if user.role != Role.PM and not user.is_superuser:
            try:
                developer_id = user.developer_profile.pk
            except DeveloperProfile.DoesNotExist:
                return HttpResponse(status=403)
        next_url = _get_next_url(request, default=reverse("planning:leave"))
        try:
            start_date = datetime.date.fromisoformat(request.POST.get("start_date", ""))
            end_date = datetime.date.fromisoformat(request.POST.get("end_date", ""))
        except ValueError:
            messages.error(request, "Invalid date format.")
            return redirect(next_url)
        if end_date < start_date:
            messages.error(request, "End date must not be before start date.")
            return redirect(next_url)
        Leave.objects.create(
            developer_id=developer_id,
            start_date=start_date,
            end_date=end_date,
        )
        return redirect(next_url)


class LeaveDeleteView(PMOrHasDeveloperProfileMixin, View):
    def post(self, request, pk, *args, **kwargs):
        leave = get_object_or_404(Leave, pk=pk)
        if denied := _check_leave_ownership(request.user, leave):
            return denied
        leave.delete()
        return redirect("planning:leave")


class LeaveUpdateView(PMOrHasDeveloperProfileMixin, View):

    def post(self, request, pk, *args, **kwargs):
        leave = get_object_or_404(Leave, pk=pk)
        if denied := _check_leave_ownership(request.user, leave):
            return denied
        try:
            leave.start_date = datetime.date.fromisoformat(request.POST.get("start_date", ""))
            leave.end_date = datetime.date.fromisoformat(request.POST.get("end_date", ""))
        except ValueError:
            return HttpResponse(status=400)
        if leave.end_date < leave.start_date:
            return HttpResponse(status=400)
        leave.save(update_fields=["start_date", "end_date"])
        next_url = request.POST.get("next")
        if next_url and url_has_allowed_host_and_scheme(next_url, allowed_hosts={request.get_host()}):
            return redirect(next_url)
        return HttpResponse(status=204)
