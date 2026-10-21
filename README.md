# Fuel Route API

A Django API that takes a start and finish in the USA, returns the driving route on a map, picks cost-effective fuel stops for a vehicle with a 500-mile range, and totals the fuel cost at 10 miles per gallon.

Work in progress.

## Run locally

Requires Python 3.12 or newer.

```bash
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
python manage.py migrate
python manage.py runserver
```

Check it's up: <http://127.0.0.1:8000/api/health/>
