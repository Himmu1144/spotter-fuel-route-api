import csv
from decimal import Decimal
from pathlib import Path

from django.conf import settings
from django.core.management.base import BaseCommand
from django.db import transaction

from fuel.models import FuelStation

STATIONS_FILE = Path(settings.BASE_DIR) / 'data' / 'stations.csv'
UPDATE_FIELDS = ['name', 'address', 'city', 'state', 'rack_id', 'price_per_gallon',
                 'latitude', 'longitude', 'placement']


class Command(BaseCommand):
    help = 'Load data/stations.csv into the database. Safe to run again: it updates in place.'

    def handle(self, *args, **options):
        with open(STATIONS_FILE, encoding='utf-8', newline='') as f:
            stations = [
                FuelStation(
                    opis_id=int(row['opis_id']),
                    name=row['name'],
                    address=row['address'],
                    city=row['city'],
                    state=row['state'],
                    rack_id=int(row['rack_id']),
                    price_per_gallon=Decimal(row['price_per_gallon']),
                    latitude=float(row['latitude']),
                    longitude=float(row['longitude']),
                    placement=row['placement'],
                )
                for row in csv.DictReader(f)
            ]

        with transaction.atomic():
            FuelStation.objects.bulk_create(
                stations, batch_size=1000,
                update_conflicts=True, unique_fields=['opis_id'], update_fields=UPDATE_FIELDS,
            )
            removed, _ = FuelStation.objects.exclude(
                opis_id__in=[s.opis_id for s in stations]).delete()

        self.stdout.write(self.style.SUCCESS(
            f'Loaded {len(stations)} stations ({removed} no longer in the file removed).'))
