from django.conf import settings
from django.db import migrations, models
import django.db.models.deletion
import django.utils.timezone


def set_site_name(apps, schema_editor):
    """Troca o "example.com" padrão, que aparecia nos e-mails enviados pelo site."""
    apps.get_model("sites", "Site").objects.update_or_create(
        pk=settings.SITE_ID, defaults={"domain": "127.0.0.1:8000", "name": "Rolêflix"}
    )


class Migration(migrations.Migration):

    dependencies = [
        ("sites", "0002_alter_domain_unique"),
        migrations.swappable_dependency(settings.AUTH_USER_MODEL),
        ("roleflix", "0002_notification"),
    ]

    operations = [
        migrations.CreateModel(
            name="AlbumView",
            fields=[
                ("id", models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name="ID")),
                ("viewed_at", models.DateTimeField(default=django.utils.timezone.now)),
                ("album", models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, to="roleflix.album")),
                ("user", models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, to=settings.AUTH_USER_MODEL)),
            ],
            options={"unique_together": {("user", "album")}},
        ),
        migrations.RunPython(set_site_name, migrations.RunPython.noop),
    ]
