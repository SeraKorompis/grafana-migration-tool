from pathlib import Path
from typing import Any, Optional

from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel

from dashboard_exporter import build_migrated_dashboard
from dashboard_parser import load_dashboard, parse_dashboard
from schema_introspection import SchemaIntrospectionError, get_influxdb_schema, get_prometheus_metric_names
from schema_mapper import MappingError, propose_schema_mapping
from translator import TranslationError, translate_query

app = FastAPI(title="Grafana Migration Tool API")

SAMPLE_DATA_DIR = Path(__file__).resolve().parent.parent / "sample_data"
DEFAULT_DASHBOARD_FILE = "promotheus-sample-0.json"

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


class QueryDecision(BaseModel):
    panel_id: int
    ref_id: str
    status: str
    translated_query: Optional[str] = None


class ExportRequest(BaseModel):
    decisions: list[QueryDecision]
    target_language: str = "InfluxDB Flux"
    file: Optional[str] = None


def _resolve_dashboard_path(filename: Optional[str]) -> Path:
    name = filename or DEFAULT_DASHBOARD_FILE
    # filename is caller-controlled (query param / request body) — restrict to a
    # bare *.json filename inside sample_data to rule out path traversal.
    if name != Path(name).name or not name.endswith(".json"):
        raise HTTPException(status_code=400, detail=f"Invalid dashboard file: {name}")
    path = SAMPLE_DATA_DIR / name
    if not path.is_file():
        raise HTTPException(status_code=404, detail=f"Dashboard file not found: {name}")
    return path


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


@app.get("/schema")
async def get_schema():
    """Live schema pulled straight from the running Prometheus/InfluxDB instances
    (see docker-compose.yml), for grounding translation in what's actually there.
    """
    result = {}

    try:
        result["prometheus"] = {"metric_names": await get_prometheus_metric_names()}
    except SchemaIntrospectionError as exc:
        result["prometheus"] = {"error": str(exc)}

    try:
        result["influxdb"] = {"measurements": await get_influxdb_schema()}
    except SchemaIntrospectionError as exc:
        result["influxdb"] = {"error": str(exc)}

    return result


@app.post("/propose-mapping")
async def propose_mapping():
    """Ask the LLM to propose source-metric -> target-measurement.field mappings,
    grounded in the live schema of both the Prometheus and InfluxDB instances
    (see docker-compose.yml).
    """
    try:
        prometheus_schema = {"metric_names": await get_prometheus_metric_names()}
    except SchemaIntrospectionError as exc:
        raise HTTPException(status_code=502, detail=f"Prometheus schema unavailable: {exc}") from exc

    try:
        influxdb_schema = {"measurements": await get_influxdb_schema()}
    except SchemaIntrospectionError as exc:
        raise HTTPException(status_code=502, detail=f"InfluxDB schema unavailable: {exc}") from exc

    try:
        mappings = await propose_schema_mapping(prometheus_schema, influxdb_schema)
    except MappingError as exc:
        raise HTTPException(status_code=502, detail=str(exc)) from exc

    return {"mappings": mappings}


@app.get("/dashboards")
def list_dashboards():
    files = sorted(p.name for p in SAMPLE_DATA_DIR.glob("*.json"))
    return {"files": files, "default": DEFAULT_DASHBOARD_FILE}


@app.get("/parse")
def parse_sample_dashboard(file: Optional[str] = None):
    dashboard = load_dashboard(_resolve_dashboard_path(file))
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


@app.post("/export")
def export_dashboard(request: ExportRequest):
    dashboard = load_dashboard(_resolve_dashboard_path(request.file))
    decisions = {
        (d.panel_id, d.ref_id): {"status": d.status, "translated_query": d.translated_query}
        for d in request.decisions
    }
    migrated = build_migrated_dashboard(dashboard, decisions, request.target_language)
    return {"dashboard": migrated}
