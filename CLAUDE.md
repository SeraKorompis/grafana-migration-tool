# Grafana Migration Tool

Hackathon project. Reads an exported Grafana dashboard JSON, translates each panel's
query from one datasource query language to another (e.g. PromQL → Flux), explains its
reasoning per query, flags translations it's uncertain about, and lets a user step
through and approve/reject/edit each change before generating a final migrated
dashboard JSON.

## Architecture

- `/backend` — Python (FastAPI). Owns dashboard JSON parsing, per-panel query
  extraction, calls to the LLM (Venice API) for translation + reasoning + confidence
  flagging, and reassembly of the approved changes into a final migrated dashboard.
- `/frontend` — React (Vite). UI for uploading/loading a dashboard, stepping through
  panels one at a time, showing original query / translated query / reasoning /
  confidence, and approve/reject/edit controls. Talks to the backend over HTTP
  (backend on :8000, frontend dev server on :5173).
- `/sample_data` — Example Grafana dashboard JSON exports used for local dev/testing.

## Status

Scaffold only — hello world on both sides, no migration logic yet.

## Running locally

Backend:
```
cd backend
pip install -r requirements.txt
uvicorn main:app --reload
```

Frontend (requires Node.js):
```
cd frontend
npm install
npm run dev
```

## Config

Copy `.env.example` to `.env` and fill in `VENICE_API_KEY` (Venice AI is the LLM
provider used for query translation/reasoning).
