from django.db import models


class FuelStation(models.Model):
    """A truck stop from the price file, placed on the map once, offline."""

    class Placement(models.TextChoices):
        EXIT = 'exit', 'Highway exit'
        TOWN = 'town', 'Town centre'
        MANUAL = 'manual', 'Looked up by hand'

    opis_id = models.PositiveIntegerField(unique=True)
    name = models.CharField(max_length=120)
    address = models.CharField(max_length=200)
    city = models.CharField(max_length=80)
    state = models.CharField(max_length=2)
    rack_id = models.PositiveIntegerField()
    # The file lists some stations several times with different prices and no dates.
    # price_per_gallon is the median of them; the count and range explain where it came from.
    price_per_gallon = models.DecimalField(max_digits=10, decimal_places=8)
    listed_prices = models.PositiveSmallIntegerField(default=1)
    lowest_price = models.DecimalField(max_digits=10, decimal_places=8)
    highest_price = models.DecimalField(max_digits=10, decimal_places=8)
    latitude = models.FloatField()
    longitude = models.FloatField()
    placement = models.CharField(max_length=10, choices=Placement)

    class Meta:
        indexes = [
            # Finding stations near a route starts with a box of latitudes and longitudes.
            models.Index(fields=['latitude', 'longitude'], name='station_lat_lon_idx'),
        ]

    def __str__(self):
        return f'{self.name} ({self.city}, {self.state})'
