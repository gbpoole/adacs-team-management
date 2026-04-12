from django.contrib.auth.mixins import LoginRequiredMixin
from django.core.exceptions import PermissionDenied


def _get_next_url(request, default="/planning/planning/"):
    return request.POST.get("next") or request.META.get("HTTP_REFERER", default)


def _update_user_profile_fields(user, post):
    user.name = post.get("name", "").strip()
    user.organisation = post.get("organisation", "").strip()
    user.save(update_fields=["name", "organisation"])


class RoleRequiredMixin(LoginRequiredMixin):
    """Restrict access to users whose role is in ``allowed_roles``."""

    allowed_roles: tuple[str, ...] = ()

    def dispatch(self, request, *args, **kwargs):
        if request.user.is_authenticated:
            role = request.user.role
            if not (role in self.allowed_roles or request.user.is_superuser):
                raise PermissionDenied
        return super().dispatch(request, *args, **kwargs)
