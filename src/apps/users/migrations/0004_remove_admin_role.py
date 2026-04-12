from django.db import migrations, models


def reassign_admin_users(apps, schema_editor):
    User = apps.get_model("users", "User")
    User.objects.filter(role="admin").update(role="pm")


class Migration(migrations.Migration):

    dependencies = [
        ("users", "0003_remove_emoji"),
    ]

    operations = [
        migrations.RunPython(reassign_admin_users, migrations.RunPython.noop),
        migrations.AlterField(
            model_name="user",
            name="role",
            field=models.CharField(
                choices=[
                    ("pm", "Project Manager"),
                    ("developer", "Developer"),
                    ("observer", "Observer"),
                ],
                default="developer",
                max_length=20,
                verbose_name="Role",
            ),
        ),
    ]
