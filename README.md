# Grafana Migration Tool

Reads an exported Grafana dashboard JSON, translates each panel's query from one
datasource query language to another (e.g. PromQL → Flux), explains its reasoning per
query, flags translations it's uncertain about, and lets a user step through and
approve/reject/edit each change before generating a final migrated dashboard.

See [CLAUDE.md](./CLAUDE.md) for architecture details.

## Prerequisites

- Python 3.11+
- Node.js 18+ and npm

## Setup

1. Clone the repo and copy the env file:

   ```
   cp .env.example .env
   ```

   Fill in `VENICE_API_KEY` in `.env` with your Venice AI API key. When generating the
   key on Venice, choose **Inference Only** (not Admin) — an Admin-only key returns
   401 on `/chat/completions` even though it looks valid.

2. Backend:

   ```
   cd backend
   python -m venv .venv
   .venv\Scripts\activate      # macOS/Linux: source .venv/bin/activate
   pip install -r requirements.txt
   uvicorn main:app --reload
   ```

   Runs at http://localhost:8000. Check http://localhost:8000/health.

3. Frontend (in a separate terminal):

   ```
   cd frontend
   npm install
   npm run dev
   ```

   Runs at http://localhost:5173.

## Usage

With both servers running, open http://localhost:5173. The sidebar lists every panel
parsed from `sample_data/promotheus-sample-0.json`. Pick a target query language from
the dropdown, click a panel to translate its queries, and for each one:

- **Approve** — accept the translation as-is
- **Reject** — flag it as not usable
- **Edit** — open a text box pre-filled with the translation, correct it, and save that
  as the approved version

Decisions persist as you move between panels. The bar under the header tracks
approved/rejected/edited/pending counts across the whole dashboard, and panels with
all their queries decided get a checkmark in the sidebar.

Once you've made at least one decision, an **Export Dashboard** button appears in the
header. It shows a summary of how many queries will be exported migrated vs. left as
original/flagged, then downloads a new Grafana dashboard JSON: approved/edited queries
get their migrated query text, rejected/pending queries keep their original (still
working) query with a `migrationNote` field flagging them for manual attention. The
file's `uid`/title are suffixed so importing it into Grafana won't overwrite the
original dashboard.

## Schema introspection sandbox

For grounding query translation in a real schema instead of a guessed one, a
docker-compose stack spins up two live data sources plus two fake data generators:

- **Prometheus** (`:9090`), scraping the fake exporter every 15s.
- **`fake-exporter`** (`:9105`) — a small Python script
  (`schema-sources/fake_prometheus_exporter.py`) that serves synthetic e-commerce
  metrics in Prometheus exposition format: `orders_total{status,region}`,
  `revenue_dollars_total{currency,region}`, `active_users_gauge{plan}`, and
  `checkout_errors_total{error_type}`. Values drift a little on every scrape
  (small counter increments, a gauge wobbling in the 200–400 range) so it behaves
  like a real small e-commerce backend instead of a static fixture.
- **InfluxDB v2.7** (`:8086`) — the migration target, pre-initialized via env vars
  (org `hackathon`, bucket `ecommerce`, admin token `dev-token-please-change`).
- **`influx-seeder`** — runs `schema-sources/seed_influxdb.py` against InfluxDB,
  writing data representing the same business concepts as the Prometheus side but
  under deliberately different measurement/tag/field names (see table below) - the
  kind of naming drift a real migration hits, so translation has a genuinely
  different target schema to ground against instead of assuming names carry over
  1:1. It backfills 6 hours of history on startup, then keeps writing a fresh point
  every 60s indefinitely (like `fake-exporter`, so panels stay backed by live data
  instead of going flat past the initial backfill).

| Prometheus                              | InfluxDB                         |
| ---------------------------------------- | --------------------------------- |
| `orders_total{status,region}`            | `sales{region,status}` field `count` |
| `revenue_dollars_total{currency,region}` | `revenue{region,currency}` field `amount` |
| `active_users_gauge{plan}`               | `users{plan}` field `active`     |
| `checkout_errors_total{error_type}`      | `errors{type}` field `count`     |

Run it with:

```
docker-compose up
```

Then:

- Prometheus UI: http://localhost:9090 — try the query `orders_total` or
  `rate(revenue_dollars_total[5m])` under **Graph**.
- Raw exporter output: http://localhost:9105/metrics
- InfluxDB UI: http://localhost:8086 — log in with `admin` / `adminpassword`, or
  query directly, e.g.:

  ```
  from(bucket: "ecommerce") |> range(start: -6h) |> filter(fn: (r) => r._measurement == "sales")
  ```
- `docker-compose logs -f influx-seeder` to watch it write a fresh point every 60s.

To re-seed on demand without the loop (e.g. against a bucket you reset by hand),
`python schema-sources/seed_influxdb.py` still works standalone - set `SEED_LOOP=1`
in its environment to make a standalone run loop too.

`docker-compose down` to stop, or `docker-compose down -v` to also drop the
InfluxDB data volume.

With the stack up and the backend running, `GET /schema` queries both live instances
and returns their actual current schema — Prometheus metric names (via
`/api/v1/label/__name__/values`) and InfluxDB measurements/fields/tags (via
`SHOW MEASUREMENTS`/`SHOW FIELD KEYS`/`SHOW TAG KEYS` against InfluxDB's v1-compat
API). Each source is independent: if one is unreachable, that side comes back as
`{"error": "..."}` instead of failing the whole request. Connection settings default
to the `docker-compose.yml` values and can be overridden in `.env` (see
`.env.example`).

## Project layout

```
backend/          FastAPI app — dashboard parsing, LLM-driven query translation
frontend/          React (Vite) app — step-through review UI
sample_data/       Example Grafana dashboard JSON exports for local dev/testing
schema-sources/    Fake Prometheus exporter, Prometheus scrape config, and an
                   InfluxDB seed script for the schema-introspection sandbox
                   (see docker-compose.yml)
```

## Status

The full flow described at the top is working end-to-end: parse (`GET /parse`),
Venice-backed translation (`POST /translate`), a review UI to approve/reject/edit each
query with decisions tracked across the dashboard, and export (`POST /export`) to
download a migrated Grafana dashboard JSON.

The schema introspection sandbox (Prometheus + fake exporter + InfluxDB via
`docker-compose up`) is in place, and the backend can now pull each side's live
schema via `GET /schema`. That schema isn't wired into translation yet, though —
`POST /translate` still only sees the query text, not the real metric/measurement
names, so grounding translation in the live schema is the next step.
