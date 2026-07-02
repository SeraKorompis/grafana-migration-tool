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

   Fill in `VENICE_API_KEY` in `.env` with your Venice AI API key.

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

## Project layout

```
backend/       FastAPI app — dashboard parsing, LLM-driven query translation
frontend/      React (Vite) app — step-through review UI
sample_data/   Example Grafana dashboard JSON exports for local testing
```

## Status

Scaffold only — hello world on both sides, no migration logic yet.
