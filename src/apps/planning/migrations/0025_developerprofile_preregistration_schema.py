import django.db.models.deletion
from django.conf import settings
from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ("planning", "0024_alter_project_name_and_more"),
        migrations.swappable_dependency(settings.AUTH_USER_MODEL),
    ]

    operations = [
        # Make DeveloperProfile.user optional so profiles can exist pre-registration
        migrations.AlterField(
            model_name="developerprofile",
            name="user",
            field=models.OneToOneField(
                blank=True,
                null=True,
                on_delete=django.db.models.deletion.SET_NULL,
                related_name="developer_profile",
                to=settings.AUTH_USER_MODEL,
            ),
        ),
        migrations.AddField(
            model_name="developerprofile",
            name="name",
            field=models.CharField(blank=True, max_length=255, verbose_name="name"),
        ),
        migrations.AddField(
            model_name="developerprofile",
            name="email",
            field=models.EmailField(
                blank=True, null=True, unique=True, verbose_name="email"
            ),
        ),
        # Temporary columns: new DeveloperProfile FKs on Project.
        # Old dev_lead/science_lead (User FKs) remain until migration 0027.
        migrations.AddField(
            model_name="project",
            name="dev_lead_profile",
            field=models.ForeignKey(
                blank=True,
                null=True,
                on_delete=django.db.models.deletion.SET_NULL,
                related_name="dev_lead_projects",
                to="planning.developerprofile",
            ),
        ),
        migrations.AddField(
            model_name="project",
            name="science_lead_profile",
            field=models.ForeignKey(
                blank=True,
                null=True,
                on_delete=django.db.models.deletion.SET_NULL,
                related_name="science_lead_projects",
                to="planning.developerprofile",
            ),
        ),
    ]
