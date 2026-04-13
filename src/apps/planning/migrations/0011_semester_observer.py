import django.db.models.deletion
from django.conf import settings
from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ("planning", "0010_observer_stream_access"),
        migrations.swappable_dependency(settings.AUTH_USER_MODEL),
    ]

    operations = [
        migrations.CreateModel(
            name="SemesterObserver",
            fields=[
                ("id", models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name="ID")),
                (
                    "user",
                    models.ForeignKey(
                        on_delete=django.db.models.deletion.CASCADE,
                        related_name="semester_observer_records",
                        to=settings.AUTH_USER_MODEL,
                    ),
                ),
                (
                    "semester",
                    models.ForeignKey(
                        on_delete=django.db.models.deletion.CASCADE,
                        related_name="observer_records",
                        to="planning.semester",
                    ),
                ),
                (
                    "project_access",
                    models.ManyToManyField(
                        blank=True,
                        help_text="Projects this observer can view for this semester.",
                        related_name="semester_observer_access",
                        to="planning.project",
                    ),
                ),
                (
                    "stream_access",
                    models.ManyToManyField(
                        blank=True,
                        help_text="Streams this observer can view for this semester.",
                        related_name="semester_observer_stream_access",
                        to="planning.stream",
                    ),
                ),
            ],
            options={
                "verbose_name": "Semester Observer",
                "verbose_name_plural": "Semester Observers",
                "unique_together": {("user", "semester")},
            },
        ),
    ]
