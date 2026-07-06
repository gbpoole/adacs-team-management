from django.contrib.auth import get_user_model
from django.db.models.signals import post_save
from django.dispatch import receiver


@receiver(post_save, sender=get_user_model())
def link_developer_profile_on_registration(sender, instance, created, **kwargs):
    """Auto-link a pre-existing DeveloperProfile when a User registers with a matching email."""
    if created and instance.email:
        from apps.planning.models import DeveloperProfile  # noqa: PLC0415

        DeveloperProfile.objects.filter(
            email__iexact=instance.email, user__isnull=True
        ).update(user=instance)
