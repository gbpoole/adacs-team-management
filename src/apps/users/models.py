from typing import ClassVar

from django.contrib.auth.models import AbstractUser
from django.db.models import CharField
from django.db.models import EmailField
from django.db.models import TextChoices
from django.urls import reverse
from django.utils.translation import gettext_lazy as _

from .managers import UserManager


class Role(TextChoices):
    PM = "pm", _("Project Manager")
    DEVELOPER = "developer", _("Developer")
    OBSERVER = "observer", _("Observer")


class User(AbstractUser):
    """
    Default custom user model for adacs-team-planning.
    If adding fields that need to be filled at user signup,
    check forms.SignupForm and forms.SocialSignupForms accordingly.
    """

    # First and last name do not cover name patterns around the globe
    name = CharField(_("Name of User"), blank=True, max_length=255)
    first_name = None  # type: ignore[assignment]
    last_name = None  # type: ignore[assignment]
    email = EmailField(_("email address"), unique=True)
    username = None  # type: ignore[assignment]
    role = CharField(
        _("Role"),
        max_length=20,
        choices=Role.choices,
        default=Role.DEVELOPER,
    )
    organisation = CharField(_("Organisation"), max_length=255, blank=True)

    USERNAME_FIELD = "email"
    REQUIRED_FIELDS = []

    objects: ClassVar[UserManager] = UserManager()

    def get_absolute_url(self) -> str:
        """Get URL for user's detail view.

        Returns:
            str: URL for user detail.

        """
        return reverse("users:detail", kwargs={"pk": self.id})
