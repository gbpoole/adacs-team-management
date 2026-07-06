import contextlib

from django.apps import AppConfig
from django.utils.translation import gettext_lazy as _


class PlanningConfig(AppConfig):
    default_auto_field = "django.db.models.BigAutoField"
    name = "apps.planning"
    verbose_name = _("Planning")

    def ready(self):
        with contextlib.suppress(ImportError):
            import apps.planning.signals  # noqa: F401, PLC0415
