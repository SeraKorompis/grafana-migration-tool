from pathlib import Path
from typing import Any, Optional

from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel

from dashboard_parser import load_dashboard, parse_dashboard
from translator import TranslationError, translate_query

app = FastAPI(title="Grafana Migration Tool API")

SAMPLE_DASHBOARD_PATH = (
    Path(__file__).resolve().parent.parent / "sample_data" / "promotheus-sample-0.json"
)

DATASOURCE_TYPE_TO_QUERY_LANGUAGE = {
    "prometheus": "PromQL",
    "loki": "LogQL",
    "influxdb": "InfluxDB Flux",
    "elasticsearch": "Elasticsearch Lucene/DSL",
    "mysql": "SQL",
    "postgres": "SQL",
}


class PanelQuery(BaseModel):
    ref_id: Optional[str] = None
    expr: str


class Panel(BaseModel):
    id: Optional[int] = None
    title: Optional[str] = None
    datasource: Optional[Any] = None
    queries: list[PanelQuery]


class TranslateRequest(BaseModel):
    panel: Panel
    target_language: str = "InfluxDB Flux"


def _source_language_for(datasource: Any) -> str:
    ds_type = datasource.get("type") if isinstance(datasource, dict) else datasource
    if isinstance(ds_type, str) and ds_type:
        return DATASOURCE_TYPE_TO_QUERY_LANGUAGE.get(ds_type, ds_type)
    return "the source query language"

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


@app.post("/translate")
async def translate_panel(request: TranslateRequest):
    source_language = _source_language_for(request.panel.datasource)

    translations = []
    for query in request.panel.queries:
        try:
            result = await translate_query(query.expr, source_language, request.target_language)
        except TranslationError as exc:
            raise HTTPException(status_code=502, detail=str(exc)) from exc
        translations.append({"ref_id": query.ref_id, "source_expr": query.expr, **result})

    return {
        "panel_id": request.panel.id,
        "panel_title": request.panel.title,
        "source_language": source_language,
        "target_language": request.target_language,
        "translations": translations,
    }
