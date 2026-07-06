from django.conf import settings
from django.db import migrations


def _get_or_create_profile(DeveloperProfile, user_pk, user_name, user_email):
    """Return an existing DeveloperProfile for user_pk, or create one."""
    profile, created = DeveloperProfile.objects.get_or_create(
        user_id=user_pk,
        defaults={
            "name": user_name or "",
            "email": user_email or None,
        },
    )
    return profile


def populate_leads_and_profile_fields(apps, schema_editor):
    DeveloperProfile = apps.get_model("planning", "DeveloperProfile")
    Project = apps.get_model("planning", "Project")
    app_label, model_name = settings.AUTH_USER_MODEL.split(".")
    User = apps.get_model(app_label, model_name)

    # Populate name/email on all existing profiles from their linked User
    for profile in DeveloperProfile.objects.filter(user_id__isnull=False):
        try:
            user = User.objects.get(pk=profile.user_id)
            profile.name = user.name or ""
            profile.email = user.email or None
            profile.save(update_fields=["name", "email"])
        except User.DoesNotExist:
            pass

    # Migrate Project.dev_lead (User FK) → Project.dev_lead_profile (DeveloperProfile FK)
    for project in Project.objects.filter(dev_lead_id__isnull=False):
        try:
            user = User.objects.get(pk=project.dev_lead_id)
            profile = _get_or_create_profile(
                DeveloperProfile, user.pk, user.name, user.email
            )
            project.dev_lead_profile_id = profile.pk
            project.save(update_fields=["dev_lead_profile"])
        except User.DoesNotExist:
            pass

    # Migrate Project.science_lead (User FK) → Project.science_lead_profile
    for project in Project.objects.filter(science_lead_id__isnull=False):
        try:
            user = User.objects.get(pk=project.science_lead_id)
            profile = _get_or_create_profile(
                DeveloperProfile, user.pk, user.name, user.email
            )
            project.science_lead_profile_id = profile.pk
            project.save(update_fields=["science_lead_profile"])
        except User.DoesNotExist:
            pass

    # Migrate Project.science_lead_name (text) → science_lead_profile with name only
    for project in Project.objects.filter(
        science_lead_profile_id__isnull=True, science_lead_name__gt=""
    ):
        profile = DeveloperProfile.objects.create(name=project.science_lead_name)
        project.science_lead_profile_id = profile.pk
        project.save(update_fields=["science_lead_profile"])


class Migration(migrations.Migration):

    dependencies = [
        ("planning", "0025_developerprofile_preregistration_schema"),
        migrations.swappable_dependency(settings.AUTH_USER_MODEL),
    ]

    operations = [
        migrations.RunPython(
            populate_leads_and_profile_fields,
            migrations.RunPython.noop,
        ),
    ]
