from django.db import migrations
from django.db import models


def forward_migrate(apps, schema_editor):
    Project = apps.get_model("planning", "Project")
    for project in Project.objects.select_related("stream").exclude(stream=None):
        project.streams.add(project.stream)


class Migration(migrations.Migration):
    dependencies = [
        ("planning", "0006_add_phase_indexes"),
    ]

    operations = [
        migrations.AddField(
            model_name="project",
            name="streams",
            field=models.ManyToManyField(blank=True, related_name="+", to="planning.stream"),
        ),
        migrations.RunPython(forward_migrate, migrations.RunPython.noop),
    ]
