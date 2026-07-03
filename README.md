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
docker-compose stack spins up two live data sources plus a fake data generator:

- **Prometheus** (`:9090`), scraping the fake exporter every 15s.
- **`fake-exporter`** (`:9105`) — a small Python script
  (`schema-sources/fake_prometheus_exporter.py`) that serves synthetic e-commerce
  metrics in Prometheus exposition format: `orders_total{status,region}`,
  `revenue_dollars_total{currency,region}`, `active_users_gauge{plan}`, and
  `checkout_errors_total{error_type}`. Values drift a little on every scrape
  (small counter increments, a gauge wobbling in the 200–400 range) so it behaves
  like a real small e-commerce backend instead of a static fixture.
- **InfluxDB** (`:8086`) — the migration target, pre-initialized via env vars
  (org `hackathon`, bucket `ecommerce`, admin token `dev-token-please-change`).

Run it with:

```
docker-compose up
```

Once InfluxDB is up, seed it once with data representing the same business
concepts as the Prometheus side, but under deliberately different
measurement/tag/field names — the kind of naming drift a real migration hits,
so translation has a genuinely different target schema to ground against
instead of assuming names carry over 1:1:

```
python schema-sources/seed_influxdb.py
```

| Prometheus                              | InfluxDB                         |
| ---------------------------------------- | --------------------------------- |
| `orders_total{status,region}`            | `sales{region,status}` field `count` |
| `revenue_dollars_total{currency,region}` | `revenue{region,currency}` field `amount` |
| `active_users_gauge{plan}`               | `users{plan}` field `active`     |
| `checkout_errors_total{error_type}`      | `errors{type}` field `count`     |

Then:

- Prometheus UI: http://localhost:9090 — try the query `orders_total` or
  `rate(revenue_dollars_total[5m])` under **Graph**.
- Raw exporter output: http://localhost:9105/metrics
- InfluxDB UI: http://localhost:8086 — log in with `admin` / `adminpassword`, or
  query directly, e.g.:

  ```
  from(bucket: "ecommerce") |> range(start: -6h) |> filter(fn: (r) => r._measurement == "sales")
  ```

`docker-compose down` to stop, or `docker-compose down -v` to also drop the
InfluxDB data volume.

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
`docker-compose up`) is in place, but the backend doesn't query it yet — translation
is still based on the query text alone, not a live schema lookup.
