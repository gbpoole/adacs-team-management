from django.db import migrations, models


def reassign_developer_observer_users(apps, schema_editor):
    User = apps.get_model("users", "User")
    User.objects.filter(role__in=["developer", "observer"]).update(role="user")


class Migration(migrations.Migration):

    dependencies = [
        ("users", "0004_remove_admin_role"),
    ]

    operations = [
        migrations.RunPython(reassign_developer_observer_users, migrations.RunPython.noop),
        migrations.AlterField(
            model_name="user",
            name="role",
            field=models.CharField(
                choices=[
                    ("pm", "Project Manager"),
                    ("user", "User"),
                ],
                default="user",
                max_length=20,
                verbose_name="Role",
            ),
        ),
    ]
