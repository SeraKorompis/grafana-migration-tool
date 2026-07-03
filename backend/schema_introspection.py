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


async def get_prometheus_metric_names() -> list[str]:
    """Return every metric name currently scraped by the live Prometheus instance."""
    async with httpx.AsyncClient(timeout=REQUEST_TIMEOUT_SECONDS) as client:
        try:
            response = await client.get(f"{PROMETHEUS_URL}/api/v1/label/__name__/values")
            response.raise_for_status()
        except httpx.HTTPError as exc:
            raise SchemaIntrospectionError(f"Prometheus request failed: {exc}") from exc

    body = response.json()
    if body.get("status") != "success":
        raise SchemaIntrospectionError(f"Unexpected Prometheus response: {body}")
    return sorted(body["data"])


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
