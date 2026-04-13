from django.db import migrations


def migrate_observer_access(apps, schema_editor):
    """Copy ObserverProfile access to SemesterObserver for every existing semester."""
    ObserverProfile = apps.get_model("planning", "ObserverProfile")
    SemesterObserver = apps.get_model("planning", "SemesterObserver")
    Semester = apps.get_model("planning", "Semester")

    semesters = list(Semester.objects.all())
    if not semesters:
        return

    for profile in ObserverProfile.objects.select_related("user").prefetch_related(
        "project_access", "stream_access"
    ):
        project_pks = list(profile.project_access.values_list("pk", flat=True))
        stream_pks = list(profile.stream_access.values_list("pk", flat=True))
        if not project_pks and not stream_pks:
            continue
        for semester in semesters:
            obs, _ = SemesterObserver.objects.get_or_create(
                user=profile.user, semester=semester
            )
            if project_pks:
                obs.project_access.set(project_pks)
            if stream_pks:
                obs.stream_access.set(stream_pks)


class Migration(migrations.Migration):

    dependencies = [
        ("planning", "0011_semester_observer"),
    ]

    operations = [
        migrations.RunPython(migrate_observer_access, migrations.RunPython.noop),
    ]
