"""Loads data/stations.csv the first time `migrate` runs on a database, so a fresh
clone needs no separate step. Django records applied migrations, so this never runs
again on the same database; use `python manage.py load_stations` to reload."""

from django.db import migrations

from fuel.loading import load_stations


def load(apps, schema_editor):
    load_stations(apps.get_model('fuel', 'FuelStation'))


def unload(apps, schema_editor):
    apps.get_model('fuel', 'FuelStation').objects.all().delete()


class Migration(migrations.Migration):

    dependencies = [
        ('fuel', '0002_price_range'),
    ]

    operations = [
        migrations.RunPython(load, unload),
    ]
