"""
Migration: replace ProjectSemesterName with direct name+semester on Project.

Each project now belongs to exactly one semester, enforced at the schema level.
For projects with multiple ProjectSemesterName records (one project spanning
multiple semesters), new Project instances are created per extra semester,
and Phase/ProjectAllocation records are repointed accordingly.

Also removes the now-redundant continuation_of_semester field.
"""

from collections import defaultdict

import django.db.models.deletion
from django.db import migrations
from django.db import models


def _split_multi_semester_projects(apps, schema_editor):
    Project = apps.get_model("planning", "Project")
    ProjectSemesterName = apps.get_model("planning", "ProjectSemesterName")
    Phase = apps.get_model("planning", "Phase")
    ProjectAllocation = apps.get_model("planning", "ProjectAllocation")

    # Group PSNs by project, sorted by semester (oldest first)
    psns_by_project = defaultdict(list)
    for psn in ProjectSemesterName.objects.select_related("semester").order_by(
        "semester__year", "semester__semester_type"
    ):
        psns_by_project[psn.project_id].append(psn)

    # (original_project_pk, semester_pk) -> final project pk
    pk_map = {}

    for project in list(Project.objects.prefetch_related("streams", "tags").all()):
        psns = psns_by_project.get(project.pk, [])
        if not psns:
            # Orphan project with no semester names — assign a dummy name;
            # it will be deleted below when we enforce NOT NULL on semester.
            project.name = f"Project #{project.pk}"
            # Leave semester_id as NULL — handled by deletion below.
            project.save()
            continue

        # First PSN: populate the existing Project row.
        first_psn = psns[0]
        project.name = first_psn.name
        project.semester_id = first_psn.semester_id
        project.save()
        pk_map[(project.pk, first_psn.semester_id)] = project.pk

        # Additional PSNs: clone the project for each extra semester.
        streams = list(project.streams.all())
        tags = list(project.tags.all())
        for psn in psns[1:]:
            new_project = Project(
                name=psn.name,
                semester_id=psn.semester_id,
                colour=project.colour,
                continuation_of_id=project.continuation_of_id,
                dev_lead_id=project.dev_lead_id,
                science_lead_id=project.science_lead_id,
                science_lead_name=project.science_lead_name,
            )
            new_project.save()
            new_project.streams.set(streams)
            new_project.tags.set(tags)
            pk_map[(project.pk, psn.semester_id)] = new_project.pk

            Phase.objects.filter(
                project_id=project.pk, semester_id=psn.semester_id
            ).update(project_id=new_project.pk)
            ProjectAllocation.objects.filter(
                project_id=project.pk, semester_id=psn.semester_id
            ).update(project_id=new_project.pk)

    # Delete orphan projects that still have no semester assigned.
    Project.objects.filter(semester_id__isnull=True).delete()

    # Fix continuation_of references using the pk_map.
    # continuation_of_semester tells us which semester version was intended.
    for project in Project.objects.filter(continuation_of__isnull=False):
        old_cont_id = project.continuation_of_id
        cont_sem_id = project.continuation_of_semester_id
        if cont_sem_id:
            new_cont_pk = pk_map.get((old_cont_id, cont_sem_id))
            if new_cont_pk is not None and new_cont_pk != project.continuation_of_id:
                project.continuation_of_id = new_cont_pk
                project.save()


class Migration(migrations.Migration):

    dependencies = [
        ("planning", "0022_project_continuation_of_semester"),
    ]

    operations = [
        # 1. Add name (nullable temporarily) and semester FK (nullable temporarily).
        migrations.AddField(
            model_name="project",
            name="name",
            field=models.CharField(
                blank=True,
                default="",
                max_length=255,
                verbose_name="name",
            ),
            preserve_default=False,
        ),
        migrations.AddField(
            model_name="project",
            name="semester",
            field=models.ForeignKey(
                null=True,
                blank=True,
                on_delete=django.db.models.deletion.CASCADE,
                related_name="projects",
                to="planning.semester",
                verbose_name="semester",
            ),
            preserve_default=False,
        ),
        # 2. Data migration.
        migrations.RunPython(
            _split_multi_semester_projects,
            migrations.RunPython.noop,
        ),
        # 3. Make name required and semester non-nullable.
        migrations.AlterField(
            model_name="project",
            name="name",
            field=models.CharField(max_length=255, verbose_name="name"),
        ),
        migrations.AlterField(
            model_name="project",
            name="semester",
            field=models.ForeignKey(
                on_delete=django.db.models.deletion.CASCADE,
                related_name="projects",
                to="planning.semester",
            ),
        ),
        # 4. Remove continuation_of_semester (no longer needed).
        migrations.RemoveField(
            model_name="project",
            name="continuation_of_semester",
        ),
        # 5. Drop ProjectSemesterName.
        migrations.DeleteModel(
            name="ProjectSemesterName",
        ),
    ]
