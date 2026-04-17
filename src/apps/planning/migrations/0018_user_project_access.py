from django.conf import settings
from django.db import migrations
from django.db import models


def forwards_copy_semester_observer_access(apps, schema_editor):
    SemesterObserver = apps.get_model("planning", "SemesterObserver")
    UserProjectAccess = apps.get_model("planning", "UserProjectAccess")

    for user_id in set(SemesterObserver.objects.values_list("user_id", flat=True)):
        access, _ = UserProjectAccess.objects.get_or_create(user_id=user_id)
        rows = SemesterObserver.objects.filter(user_id=user_id)
        project_ids = set()
        stream_ids = set()
        for row in rows:
            project_ids.update(row.project_access.values_list("pk", flat=True))
            stream_ids.update(row.stream_access.values_list("pk", flat=True))
        if project_ids:
            access.project_access.set(project_ids)
        if stream_ids:
            access.stream_access.set(stream_ids)


class Migration(migrations.Migration):
    dependencies = [
        ("planning", "0017_remove_observerprofile_and_allocationtype"),
    ]

    operations = [
        migrations.CreateModel(
            name="UserProjectAccess",
            fields=[
                (
                    "id",
                    models.BigAutoField(
                        auto_created=True,
                        primary_key=True,
                        serialize=False,
                        verbose_name="ID",
                    ),
                ),
                (
                    "user",
                    models.OneToOneField(
                        on_delete=models.deletion.CASCADE,
                        related_name="project_access_policy",
                        to=settings.AUTH_USER_MODEL,
                    ),
                ),
                (
                    "project_access",
                    models.ManyToManyField(
                        blank=True,
                        help_text="Projects this user can view.",
                        related_name="user_project_access_policies",
                        to="planning.project",
                    ),
                ),
                (
                    "stream_access",
                    models.ManyToManyField(
                        blank=True,
                        help_text="Streams this user can view.",
                        related_name="user_stream_access_policies",
                        to="planning.stream",
                    ),
                ),
            ],
            options={
                "verbose_name": "User Project Access",
                "verbose_name_plural": "User Project Access",
            },
        ),
        migrations.RunPython(
            forwards_copy_semester_observer_access,
            migrations.RunPython.noop,
        ),
    ]
