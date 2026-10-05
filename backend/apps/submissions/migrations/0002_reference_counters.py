"""Compteurs des références pour les éditions existantes (créés hors contention)."""

from django.db import migrations


def create_counters(apps, schema_editor):
    Edition = apps.get_model("conferences", "Edition")
    Counter = apps.get_model("core", "Counter")
    for edition in Edition.objects.all():
        Counter.objects.get_or_create(scope=f"submission:{edition.pk}")


class Migration(migrations.Migration):
    dependencies = [
        ("submissions", "0001_initial"),
        ("core", "0004_counter"),
        ("conferences", "0004_submission_settings"),
    ]

    operations = [migrations.RunPython(create_counters, migrations.RunPython.noop)]
