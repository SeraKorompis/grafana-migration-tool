from pathlib import Path

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from dashboard_parser import load_dashboard, parse_dashboard

app = FastAPI(title="Grafana Migration Tool API")

SAMPLE_DASHBOARD_PATH = (
    Path(__file__).resolve().parent.parent / "sample_data" / "promotheus-sample-0.json"
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:5173"],
    allow_methods=["*"],
    allow_headers=["*"],
)


@app.get("/")
def read_root():
    return {"message": "Hello World"}


@app.get("/health")
def health_check():
    return {"status": "ok"}


@app.get("/parse")
def parse_sample_dashboard():
    dashboard = load_dashboard(SAMPLE_DASHBOARD_PATH)
    return parse_dashboard(dashboard)
