from django.db import migrations
from django.db import models


class Migration(migrations.Migration):
    dependencies = [
        ("planning", "0007_project_streams_m2m"),
    ]

    operations = [
        migrations.RemoveField(
            model_name="project",
            name="stream",
        ),
        migrations.AlterField(
            model_name="project",
            name="streams",
            field=models.ManyToManyField(blank=True, related_name="projects", to="planning.stream"),
        ),
    ]
