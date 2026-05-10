from django.contrib import messages
from django.db.models import Count
from django.shortcuts import get_object_or_404
from django.shortcuts import redirect
from django.views import View
from django.views.generic import ListView

from apps.planning.models import COLOUR_PALETTE
from apps.planning.models import Tag
from apps.users.models import Role

from ._mixins import RoleRequiredMixin


class TagsView(RoleRequiredMixin, ListView):
    template_name = "planning/tags.html"
    context_object_name = "tags"
    allowed_roles = (Role.PM,)

    def get_queryset(self):
        return Tag.objects.annotate(
            developer_count=Count("developers", distinct=True),
            project_count=Count("projects", distinct=True),
        )

    def get_context_data(self, **kwargs):
        ctx = super().get_context_data(**kwargs)
        ctx["colour_palette"] = COLOUR_PALETTE
        return ctx


class TagCreateView(RoleRequiredMixin, View):
    allowed_roles = (Role.PM,)

    def post(self, request, *args, **kwargs):
        name = request.POST.get("name", "").strip()
        if not name:
            return redirect("planning:tags")
        if "||" in name or "\t" in name:
            messages.error(request, "Tag name may not contain '||' or tab characters.")
            return redirect("planning:tags")
        colour = request.POST.get("colour", "").strip()
        tag = Tag(name=name, colour=colour)
        tag.save()
        return redirect("planning:tags")


class TagUpdateView(RoleRequiredMixin, View):
    allowed_roles = (Role.PM,)

    def post(self, request, pk, *args, **kwargs):
        tag = get_object_or_404(Tag, pk=pk)
        name = request.POST.get("name", "").strip()
        if name:
            if "||" in name or "\t" in name:
                messages.error(
                    request, "Tag name may not contain '||' or tab characters."
                )
                return redirect("planning:tags")
            tag.name = name
        colour = request.POST.get("colour", "").strip()
        if colour:
            tag.colour = colour
        tag.save()
        return redirect("planning:tags")


class TagDeleteView(RoleRequiredMixin, View):
    allowed_roles = (Role.PM,)

    def post(self, request, pk, *args, **kwargs):
        tag = get_object_or_404(Tag, pk=pk)
        tag.delete()
        return redirect("planning:tags")
