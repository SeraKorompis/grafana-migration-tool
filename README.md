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

## Project layout

```
backend/       FastAPI app — dashboard parsing, LLM-driven query translation
frontend/      React (Vite) app — step-through review UI
sample_data/   promotheus-sample-0.json: a real 15-panel Node Exporter dashboard export
```

## Status

The full flow described at the top is working end-to-end: parse (`GET /parse`),
Venice-backed translation (`POST /translate`), a review UI to approve/reject/edit each
query with decisions tracked across the dashboard, and export (`POST /export`) to
download a migrated Grafana dashboard JSON.
