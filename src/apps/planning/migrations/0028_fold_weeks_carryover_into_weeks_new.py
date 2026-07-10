from django.db import migrations
from django.db.models import F


def fold_carryover(apps, schema_editor):
    """Fold stored carryover into weeks_new; carryover becomes live-computed."""
    ProjectAllocation = apps.get_model("planning", "ProjectAllocation")
    ProjectAllocation.objects.update(weeks_new=F("weeks_new") + F("weeks_carryover"))


class Migration(migrations.Migration):
    dependencies = [
        ("planning", "0027_developerprofile_preregistration_finalize"),
    ]

    operations = [
        migrations.RunPython(fold_carryover, migrations.RunPython.noop),
    ]
