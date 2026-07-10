from django.contrib.auth import get_user_model
from django.db.models.signals import post_save
from django.dispatch import receiver


@receiver(post_save, sender=get_user_model())
def link_developer_profile_on_registration(sender, instance, created, **kwargs):
    """Link a pre-existing DeveloperProfile when a User registers with a matching
    email, and transfer any pre-registration access policy to the new user."""
    if not (created and instance.email):
        return
    from apps.planning.models import DeveloperProfile  # noqa: PLC0415
    from apps.planning.models import UserProjectAccess  # noqa: PLC0415

    profiles = DeveloperProfile.objects.filter(
        email__iexact=instance.email, user__isnull=True
    )
    linked_ids = list(profiles.values_list("pk", flat=True))
    profiles.update(user=instance)

    # Move any profile-keyed access policy onto the freshly registered user.
    for policy in UserProjectAccess.objects.filter(developer_profile_id__in=linked_ids):
        existing = UserProjectAccess.objects.filter(user=instance).first()
        if existing is None:
            # Set user and clear profile in one save so the "exactly one owner"
            # constraint is never transiently violated.
            policy.user = instance
            policy.developer_profile = None
            policy.save(update_fields=["user", "developer_profile"])
        else:
            existing.project_access.add(*policy.project_access.all())
            existing.stream_access.add(*policy.stream_access.all())
            existing.all_project_access = (
                existing.all_project_access or policy.all_project_access
            )
            existing.all_stream_access = (
                existing.all_stream_access or policy.all_stream_access
            )
            existing.save(update_fields=["all_project_access", "all_stream_access"])
            policy.delete()
