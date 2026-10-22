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
python manage.py load_stations
python manage.py runserver
```

Check it's up: <http://127.0.0.1:8000/api/health/> (shows how many stations are loaded)

Runs on SQLite with no setup. To use Postgres instead, start one with `docker compose up -d` and set `DATABASE_URL` as shown in `.env.example`.

## What to send

`start` and `finish` each take one of two formats:

- a city and state: `Chicago, IL` or `Chicago, Illinois`
- coordinates, latitude first: `41.88,-87.63`

Anything else gets a 400 with a message saying what to send. Small typos are corrected (`Chicgo, Ilinois` becomes Chicago, IL) and the response says what it was read as; names too far off get suggestions instead of a guess. Place names are looked up in a local list, so the only external call per request is the route itself.

## The station data

The price file has no coordinates, so stations are placed on the map once, offline, and the result (`data/stations.csv`) is committed. To rebuild it:

```bash
python scripts/build_places.py     # US place list from GeoNames -> data/us_places.csv.gz
python scripts/build_stations.py   # clean the price file and place each station -> data/stations.csv
```

Cleaning: 620 Canadian rows dropped (trips start and finish in the USA, and the file doesn't say what currency those prices are in); 905 duplicate rows merged (one row per station ID, at its lowest listed price); stray spaces trimmed. 6,626 US stations, all placed: 6,604 at their town's centre, 22 from hand-checked lookups in `data/place_fixes.csv`.
