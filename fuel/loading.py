"""Loading data/stations.csv into the database. Shared by the load_stations command and
the migration that loads the stations the first time `migrate` runs."""

import csv
from decimal import Decimal
from pathlib import Path

STATIONS_FILE = Path(__file__).resolve().parent.parent / 'data' / 'stations.csv'
TEXT_FIELDS = ['name', 'address', 'city', 'state', 'placement']
DECIMAL_FIELDS = ['price_per_gallon', 'lowest_price', 'highest_price']
INTEGER_FIELDS = ['rack_id', 'listed_prices']
FLOAT_FIELDS = ['latitude', 'longitude']


def load_stations(station_model):
    """Insert or update every station in the file, and remove any no longer in it.

    Takes the model as an argument because a migration must use its own historical
    version of the model rather than importing fuel.models.
    """
    with open(STATIONS_FILE, encoding='utf-8', newline='') as f:
        stations = [
            station_model(
                opis_id=int(row['opis_id']),
                **{field: row[field] for field in TEXT_FIELDS},
                **{field: Decimal(row[field]) for field in DECIMAL_FIELDS},
                **{field: int(row[field]) for field in INTEGER_FIELDS},
                **{field: float(row[field]) for field in FLOAT_FIELDS},
            )
            for row in csv.DictReader(f)
        ]
    station_model.objects.bulk_create(
        stations, batch_size=1000, update_conflicts=True, unique_fields=['opis_id'],
        update_fields=TEXT_FIELDS + DECIMAL_FIELDS + INTEGER_FIELDS + FLOAT_FIELDS,
    )
    removed, _ = station_model.objects.exclude(opis_id__in=[s.opis_id for s in stations]).delete()
    return len(stations), removed
