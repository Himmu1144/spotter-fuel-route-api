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

## Use it

```
GET /api/route/?start=Seattle, WA&finish=Miami, FL
```

Returns, summary first:

- `map_url`: open it in a browser to see the route and numbered fuel stops on a map
- `summary`: distance, driving time, number of stops, fuel cost, gallons bought and used
- `compared_to_cheapest`: what the absolute cheapest plan would cost, and how many stops it needs
- `stops`: each stop in order, with its mile along the route, price, gallons and cost
- `map`: the route and stops as GeoJSON (paste into geojson.io to view)
- `meta`: which routing server answered, how many external calls were made, and where the time went

Add `&mode=cheapest` for the absolute cheapest plan. The default, `balanced`, takes the fewest stops that cost no more than 1% above the cheapest: Seattle to Miami is 8 stops for $851.57, against 18 stops for $848.09.

Errors come back as `{"error": {"code", "message"}}`: 400 for input it can't read, 422 when there's no road route or a stretch longer than one tank has no station, 502 when the routing service is down.

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

Cleaning: 620 Canadian rows dropped (trips start and finish in the USA, and the file doesn't say what currency those prices are in); 905 duplicate rows merged into one row per station ID, priced at the median of its listed prices (there are no dates to pick the latest, and the lowest would favour stations that are listed more often); stray spaces trimmed. 6,626 US stations, all placed: 6,605 at their town's centre, 21 from hand-checked lookups in `data/place_fixes.csv`.
