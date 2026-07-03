import json
import os

import httpx
from dotenv import load_dotenv

load_dotenv()

VENICE_API_BASE_URL = os.environ.get("VENICE_API_BASE_URL", "https://api.venice.ai/api/v1")
VENICE_API_KEY = os.environ.get("VENICE_API_KEY")

# Same "private" (zero-retention) Venice model used for translation - see the
# comment in translator.py for why we pin to this one specifically.
MAPPING_MODEL = "zai-org-glm-4.7"

REQUEST_TIMEOUT_SECONDS = 60

SYSTEM_PROMPT = """You are a schema-mapping assistant for a Grafana dashboard migration tool. \
You are given the live schema of a source Prometheus instance (its metric names) and a target \
InfluxDB instance (its measurements, each with its field keys and tag keys). Propose which \
source metric corresponds to which target measurement/field.

Respond with ONLY a JSON object (no markdown fences, no commentary outside the JSON) matching \
exactly this shape:

{
  "mappings": [
    {
      "source": string,
      "target": string,
      "confidence": "high" | "medium" | "low",
      "reasoning": string
    }
  ]
}

Where "source" is a Prometheus metric name and "target" is "<measurement>.<field>" built from \
the given InfluxDB schema.

Rules:
- Propose exactly one mapping per source metric given, even when unsure - use "low" confidence \
and explain the uncertainty in "reasoning" rather than omitting the metric.
- Only use measurement/field combinations that actually appear in the given InfluxDB schema; \
never invent one.
- Base each mapping on the underlying business concept the names suggest (e.g. "orders_total" \
and a "sales" measurement with a "count" field both describe order counts), not on string \
similarity alone - source and target names will often differ deliberately.
- Prometheus's own internal metrics (e.g. "up", "scrape_*") must be omitted from "mappings" \
entirely - do not include an entry for them, not even a low-confidence placeholder one.
"""


class MappingError(RuntimeError):
    pass


def _build_user_prompt(prometheus_schema: dict, influxdb_schema: dict) -> str:
    return (
        "Source (Prometheus) schema:\n"
        f"{json.dumps(prometheus_schema, indent=2)}\n\n"
        "Target (InfluxDB) schema:\n"
        f"{json.dumps(influxdb_schema, indent=2)}"
    )


async def propose_schema_mapping(prometheus_schema: dict, influxdb_schema: dict) -> list[dict]:
    """Ask Venice to propose source-metric -> target-measurement.field mappings.

    `prometheus_schema` and `influxdb_schema` are the dicts returned under GET /schema's
    "prometheus" and "influxdb" keys respectively (e.g. {"metric_names": [...]} and
    {"measurements": {...}}). Returns a list of dicts with keys: source, target,
    confidence, reasoning. Raises MappingError on failure.
    """
    if not VENICE_API_KEY:
        raise MappingError("VENICE_API_KEY is not set")

    payload = {
        "model": MAPPING_MODEL,
        "messages": [
            {"role": "system", "content": SYSTEM_PROMPT},
            {"role": "user", "content": _build_user_prompt(prometheus_schema, influxdb_schema)},
        ],
        "response_format": {"type": "json_object"},
        "temperature": 0.2,
        "venice_parameters": {"disable_thinking": True},
    }

    async with httpx.AsyncClient(timeout=REQUEST_TIMEOUT_SECONDS) as client:
        try:
            response = await client.post(
                f"{VENICE_API_BASE_URL}/chat/completions",
                headers={"Authorization": f"Bearer {VENICE_API_KEY}"},
                json=payload,
            )
            response.raise_for_status()
        except httpx.HTTPError as exc:
            raise MappingError(f"Venice API request failed: {exc}") from exc

    body = response.json()
    try:
        content = body["choices"][0]["message"]["content"]
    except (KeyError, IndexError) as exc:
        raise MappingError(f"Unexpected Venice API response shape: {body}") from exc

    try:
        result = json.loads(content)
    except json.JSONDecodeError as exc:
        raise MappingError(f"Model did not return valid JSON: {content}") from exc

    mappings = result.get("mappings")
    if not isinstance(mappings, list):
        raise MappingError(f"Model response missing 'mappings' list: {result}")

    required_keys = {"source", "target", "confidence", "reasoning"}
    for mapping in mappings:
        missing = required_keys - mapping.keys()
        if missing:
            raise MappingError(f"Mapping entry missing fields {missing}: {mapping}")

    return mappings
