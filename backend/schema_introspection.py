import os

import httpx
from dotenv import load_dotenv

load_dotenv()

PROMETHEUS_URL = os.environ.get("PROMETHEUS_URL", "http://localhost:9090")
INFLUXDB_URL = os.environ.get("INFLUXDB_URL", "http://localhost:8086")
INFLUXDB_TOKEN = os.environ.get("INFLUXDB_TOKEN", "dev-token-please-change")
INFLUXDB_BUCKET = os.environ.get("INFLUXDB_BUCKET", "ecommerce")

REQUEST_TIMEOUT_SECONDS = 10


class SchemaIntrospectionError(RuntimeError):
    pass


async def _prometheus_get(client: httpx.AsyncClient, path: str, params: dict) -> dict:
    try:
        response = await client.get(f"{PROMETHEUS_URL}{path}", params=params)
        response.raise_for_status()
    except httpx.HTTPError as exc:
        raise SchemaIntrospectionError(f"Prometheus request failed: {exc}") from exc

    body = response.json()
    if body.get("status") != "success":
        raise SchemaIntrospectionError(f"Unexpected Prometheus response: {body}")
    return body["data"]


async def get_prometheus_schema() -> dict[str, dict[str, list[str]]]:
    """Return {metric_name: {"labels": [...]}} for every metric currently scraped.

    Label names come from unioning the label keys across every actual series for that
    metric (via /api/v1/series) rather than /api/v1/labels, which returns every label
    name in the whole instance with no per-metric breakdown.
    """
    async with httpx.AsyncClient(timeout=REQUEST_TIMEOUT_SECONDS) as client:
        metric_names = sorted(await _prometheus_get(client, "/api/v1/label/__name__/values", {}))

        schema = {}
        for metric in metric_names:
            series_list = await _prometheus_get(client, "/api/v1/series", {"match[]": metric})
            labels = {key for series in series_list for key in series}
            labels.discard("__name__")
            schema[metric] = {"labels": sorted(labels)}
        return schema


async def _influxql(client: httpx.AsyncClient, query: str) -> list[list[str]]:
    """Run one InfluxQL statement via InfluxDB 2.x's v1-compatibility /query endpoint."""
    response = await client.get(
        f"{INFLUXDB_URL}/query",
        params={"db": INFLUXDB_BUCKET, "q": query},
        headers={"Authorization": f"Token {INFLUXDB_TOKEN}"},
    )
    response.raise_for_status()
    series = response.json().get("results", [{}])[0].get("series", [])
    return series[0]["values"] if series else []


async def get_influxdb_schema() -> dict[str, dict[str, list[str]]]:
    """Return {measurement: {"fields": [...], "tags": [...]}} for the live InfluxDB bucket."""
    try:
        async with httpx.AsyncClient(timeout=REQUEST_TIMEOUT_SECONDS) as client:
            measurements = [row[0] for row in await _influxql(client, "SHOW MEASUREMENTS")]

            schema = {}
            for measurement in measurements:
                fields = [row[0] for row in await _influxql(client, f'SHOW FIELD KEYS FROM "{measurement}"')]
                tags = [row[0] for row in await _influxql(client, f'SHOW TAG KEYS FROM "{measurement}"')]
                schema[measurement] = {"fields": fields, "tags": tags}
            return schema
    except httpx.HTTPError as exc:
        raise SchemaIntrospectionError(f"InfluxDB request failed: {exc}") from exc
