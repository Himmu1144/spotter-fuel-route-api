# Fuel Route API

A Django API that takes a start and finish in the USA, returns the driving route on a map, picks cost-effective fuel stops for a vehicle with a 500-mile range, and totals the fuel cost at 10 miles per gallon.

Work in progress.

## Run locally

Requires Python 3.12 or newer.

```bash
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
python manage.py migrate      # creates the tables and loads the 6,626 fuel stations (once)
python manage.py runserver
```

Check it's up: <http://127.0.0.1:8000/api/health/> (shows how many stations are loaded)

Runs on SQLite with an in-memory cache and no setup. To run on Postgres and Redis instead, start them with `docker compose up -d` and set `DATABASE_URL` and `REDIS_URL` as shown in `.env.example`.

## Use it

```
GET /api/route/?start=Seattle, WA&finish=Miami, FL
```

Returns, summary first:

- `map_url`: open it in a browser to see the route and numbered fuel stops on a map
- `summary`: distance, driving time, number of stops, a one-line description of the plan, and two totals: `fuel_bought_usd` (fuel bought on the way) and `trip_fuel_cost_usd` (all the fuel the trip burns, counting the full tank it starts with)
- `compared_to_cheapest`: what the absolute cheapest plan would cost, and how many stops it needs
- `stops`: each stop in order, with its mile along the route, price (and how that price was worked out), gallons and cost
- `map`: the route and stops as GeoJSON (paste into geojson.io to view)
- `meta`: which routing server answered, how many external calls were made, whether the route came from the cache, and where the time went

Add `&mode=cheapest` for the absolute cheapest plan. The default, `balanced`, takes the fewest stops that cost no more than 1% above the cheapest: Seattle to Miami is 8 stops for $852.39, against 20 stops for $848.75. Each stop also says why it buys the amount it does, and how its price and location were worked out.

Errors come back as `{"error": {"code", "message"}}`: 400 for input it can't read, 422 when there's no road route or a stretch longer than one tank has no station (with a `gap` saying where), 502 when the routing service is down.

## Speed and external calls

A new trip makes exactly one external call (OSRM) and takes about 1 to 1.5 seconds, nearly all of it the routing call. Repeating a trip makes none: the route is cached for a day by the resolved start and finish (so "Chicago" and "Chicago, IL" share it), and the answer takes about 100 ms. Only the route is cached, not the fuel plan, so reloading prices never serves a stale plan. The cache is in memory by default; set `REDIS_URL` to share it across server processes (`docker compose up -d` starts a Redis).

## What to send

`start` and `finish` each take one of two formats:

- a city and state: `Chicago, IL` or `Chicago, Illinois`
- coordinates, latitude first: `41.88,-87.63`

A city with no state is accepted when it's far bigger than every other US place with that name (`Chicago`, `Los Angeles`); ambiguous names like `Portland` get a 400 listing the options. Anything else gets a 400 with a message saying what to send. Small typos are corrected (`Chicgo, Ilinois` becomes Chicago, IL) and the response says what it was read as; names too far off get suggestions instead of a guess. Place names are looked up in a local list, so the only external call per request is the route itself.

## Known data gap

The price list has no stations on I-5 between Halsey, Oregon and southern California, and none in central or northern California (its 16 California stations are all in the south-east). Trips that would have to refuel there, like San Francisco to Seattle, return a 422 that names the gap rather than inventing a stop.

## The station data

The price file has no coordinates, so stations are placed on the map once, offline, and the result (`data/stations.csv`) is committed. `migrate` loads it into the database the first time it runs; after rebuilding the file, reload it with `python manage.py load_stations`. To rebuild it:

```bash
python scripts/build_places.py     # US place list from GeoNames -> data/us_places.csv.gz
python scripts/fetch_exits.py      # numbered motorway exits from OpenStreetMap -> data/osm_exits.csv (slow: public servers)
python scripts/build_stations.py   # clean the price file and place each station -> data/stations.csv
```

Cleaning: 620 Canadian rows dropped (trips start and finish in the USA, and the file doesn't say what currency those prices are in); 905 duplicate rows merged into one row per station ID, priced at the median of its listed prices (there are no dates to pick the latest, and the lowest would favour stations that are listed more often); stray spaces trimmed. 6,626 US stations, all placed: 3,389 at the highway exit their address names ("I-80, EXIT 439"), matched against OpenStreetMap's exits (`scripts/fetch_exits.py`, `data/osm_exits.csv`); the rest at their town's centre, 8 of those from hand-checked lookups in `data/place_fixes.csv`. A station counts as on the route within 3 miles if it's at a known exit, or 10 miles if it's placed at its town's centre, since that position is approximate.
