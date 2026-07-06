from django.conf import settings
from django.db import migrations


class Migration(migrations.Migration):

    dependencies = [
        ("planning", "0026_developerprofile_preregistration_data"),
        migrations.swappable_dependency(settings.AUTH_USER_MODEL),
    ]

    operations = [
        # Remove old Project lead fields (User FKs and external name text field)
        migrations.RemoveField(model_name="project", name="dev_lead"),
        migrations.RemoveField(model_name="project", name="science_lead"),
        migrations.RemoveField(model_name="project", name="science_lead_name"),
        # Rename temp columns to their final names
        migrations.RenameField(
            model_name="project",
            old_name="dev_lead_profile",
            new_name="dev_lead",
        ),
        migrations.RenameField(
            model_name="project",
            old_name="science_lead_profile",
            new_name="science_lead",
        ),
    ]
