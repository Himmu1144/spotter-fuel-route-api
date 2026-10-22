from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('fuel', '0001_initial'),
    ]

    operations = [
        migrations.AddField(
            model_name='fuelstation',
            name='listed_prices',
            field=models.PositiveSmallIntegerField(default=1),
        ),
        # Existing rows get their real values when the stations are (re)loaded.
        migrations.AddField(
            model_name='fuelstation',
            name='lowest_price',
            field=models.DecimalField(decimal_places=8, default=0, max_digits=10),
            preserve_default=False,
        ),
        migrations.AddField(
            model_name='fuelstation',
            name='highest_price',
            field=models.DecimalField(decimal_places=8, default=0, max_digits=10),
            preserve_default=False,
        ),
    ]
