from django.db.models import Count
from django.shortcuts import get_object_or_404
from django.shortcuts import redirect
from django.views import View
from django.views.generic import ListView

from apps.planning.models import COLOUR_PALETTE
from apps.planning.models import Stream
from apps.users.models import Role

from ._mixins import RoleRequiredMixin


class StreamsView(RoleRequiredMixin, ListView):
    template_name = "planning/streams.html"
    context_object_name = "streams"
    allowed_roles = (Role.ADMIN, Role.PM)

    def get_queryset(self):
        return Stream.objects.annotate(
            project_count=Count("projects", distinct=True),
        )

    def get_context_data(self, **kwargs):
        ctx = super().get_context_data(**kwargs)
        ctx["colour_palette"] = COLOUR_PALETTE
        return ctx


class StreamCreateView(RoleRequiredMixin, View):
    allowed_roles = (Role.ADMIN, Role.PM)

    def post(self, request, *args, **kwargs):
        name = request.POST.get("name", "").strip()
        if not name:
            return redirect("planning:streams")
        colour = request.POST.get("colour", "").strip()
        stream = Stream(name=name, colour=colour)
        stream.save()
        return redirect("planning:streams")


class StreamUpdateView(RoleRequiredMixin, View):
    allowed_roles = (Role.ADMIN, Role.PM)

    def post(self, request, pk, *args, **kwargs):
        stream = get_object_or_404(Stream, pk=pk)
        name = request.POST.get("name", "").strip()
        if name:
            stream.name = name
        colour = request.POST.get("colour", "").strip()
        if colour:
            stream.colour = colour
        stream.save()
        return redirect("planning:streams")


class StreamDeleteView(RoleRequiredMixin, View):
    allowed_roles = (Role.ADMIN, Role.PM)

    def post(self, request, pk, *args, **kwargs):
        stream = get_object_or_404(Stream, pk=pk)
        stream.delete()
        return redirect("planning:streams")
