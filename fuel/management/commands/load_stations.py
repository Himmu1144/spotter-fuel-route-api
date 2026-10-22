from django.core.management.base import BaseCommand
from django.db import transaction

from fuel.loading import load_stations
from fuel.models import FuelStation


class Command(BaseCommand):
    help = ('Reload data/stations.csv into the database, e.g. after rebuilding it. '
            '`migrate` already loads it once on a new database. Safe to run again: it updates in place.')

    def handle(self, *args, **options):
        with transaction.atomic():
            loaded, removed = load_stations(FuelStation)
        self.stdout.write(self.style.SUCCESS(
            f'Loaded {loaded} stations ({removed} no longer in the file removed).'))
