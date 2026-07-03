import json
import os

import httpx
from dotenv import load_dotenv

load_dotenv()

VENICE_API_BASE_URL = os.environ.get("VENICE_API_BASE_URL", "https://api.venice.ai/api/v1")
VENICE_API_KEY = os.environ.get("VENICE_API_KEY")

# Grafana panel queries routinely embed internal metric names, label values,
# and business logic (e.g. job="checkout-service", mountpoint="/var/lib/pg-primary").
# We deliberately use Venice rather than a standard cloud LLM provider, and within
# Venice we pin to a model whose `model_spec.privacy` is "private" — hosted
# directly by Venice with zero data retention — rather than one of Venice's
# "anonymized" proxy-tier models. Anonymized-tier requests are forwarded to a
# third-party provider (OpenAI, Anthropic, Google, xAI, ...) under Venice's
# account and get logged by whichever provider actually serves them, which
# would defeat the point of routing sensitive query content through a
# privacy-focused provider in the first place.
#
# zai-org-glm-4.7 is Venice's "private" + "most_intelligent" + "function_calling_default"
# text model (open-weight GLM-4.7) as of this writing — confirmed via GET /models.
TRANSLATION_MODEL = "zai-org-glm-4.7"

REQUEST_TIMEOUT_SECONDS = 60

SYSTEM_PROMPT = """You are a query translation assistant for a Grafana dashboard migration tool. \
You translate a single monitoring query from one query language to another.

Respond with ONLY a JSON object (no markdown fences, no commentary outside the JSON) matching \
exactly this shape:

{
  "translated_query": string,
  "confidence": "high" | "medium" | "low",
  "syntax_reasoning": string,
  "mapping_reasoning": string,
  "schema_mapping_applicable": boolean,
  "mapping_used": string[],
  "needs_review": boolean
}

Rules:
- "syntax_reasoning" explains ONLY the language/syntax translation choices (e.g. how functions, \
operators, or variables like $node/$__rate_interval were carried over or mapped between the two \
query languages). Do not discuss schema/metric-name mapping here.
- "schema_mapping_applicable" is false only when the query has no metric/measurement name at all \
(e.g. it's built purely from macros/timing with nothing to map). It is true whenever the query \
references at least one metric, even if that metric turns out not to be covered by the confirmed \
mapping below.
- "mapping_used" must list the exact "source" metric names (from the confirmed schema mapping \
given below the query) that this query's metrics were matched against and used for. Leave it as \
an empty list whenever no confirmed mapping entry was used (including when "schema_mapping_applicable" \
is false, or the query's metric isn't covered by the mapping, or no mapping was given at all).
- "mapping_reasoning" explains ONLY the schema-mapping side: if "schema_mapping_applicable" is \
false, briefly say there's no metric to map; if a confirmed mapping entry was used, explain which \
one(s) and why; if the query references a metric with no confirmed mapping entry, say so \
explicitly and note the target name is a guess. Do not discuss syntax/language translation here.
- Set "needs_review" to true whenever the source query uses label filters, regex matching, \
boolean/comparison operators, or functions that do not have a clean 1:1 equivalent in the \
target language. Set it to false only when the translation is a direct, unambiguous mapping.
- If you set "needs_review" to true, "confidence" should generally be "medium" or "low".
- If a confirmed schema mapping is given below the query, and the query references one of its \
source metrics, use that mapping's exact measurement and field names rather than guessing. \
"measurement" and "field" are separate attributes in the target schema (e.g. in Flux, separate \
`r["_measurement"] == "<measurement>"` and `r["_field"] == "<field>"` filters) - never \
concatenate them into a single "measurement.field" string in the translated query.
- If a confirmed schema mapping is given but the query references a metric NOT covered by it, \
you must still translate it (guessing a measurement/field the same way you would if no mapping \
were given at all), but set "needs_review" to true regardless of how direct the translation \
otherwise looks.
"""


class TranslationError(RuntimeError):
    pass


def _build_mapping_context(schema_mapping: list[dict] | None) -> str:
    if not schema_mapping:
        return ""
    lines = []
    for m in schema_mapping:
        measurement, _, field = m["target"].partition(".")
        lines.append(f'- {m["source"]} -> measurement="{measurement}", field="{field}"')
    return "\n\nConfirmed schema mapping (source metric -> target measurement/field):\n" + "\n".join(lines)


def _build_user_prompt(
    query: str, source_language: str, target_language: str, schema_mapping: list[dict] | None = None
) -> str:
    return (
        f"Source query language: {source_language}\n"
        f"Target query language: {target_language}\n"
        f"Query to translate:\n{query}"
        f"{_build_mapping_context(schema_mapping)}"
    )


async def translate_query(
    query: str, source_language: str, target_language: str, schema_mapping: list[dict] | None = None
) -> dict:
    """Translate a single query string via Venice's chat completions API.

    `schema_mapping`, if given, is the user-confirmed list of {source, target, ...} entries
    from POST /propose-mapping - grounding the translation in the real target schema instead
    of guessed measurement/field names.

    Returns a dict with keys: translated_query, confidence, syntax_reasoning, mapping_reasoning,
    schema_mapping_applicable, mapping_used, needs_review. Raises TranslationError if the API
    call fails or the model's response isn't valid JSON matching the expected shape.
    """
    if not VENICE_API_KEY:
        raise TranslationError("VENICE_API_KEY is not set")

    payload = {
        "model": TRANSLATION_MODEL,
        "messages": [
            {"role": "system", "content": SYSTEM_PROMPT},
            {
                "role": "user",
                "content": _build_user_prompt(query, source_language, target_language, schema_mapping),
            },
        ],
        "response_format": {"type": "json_object"},
        "temperature": 0.2,
        # zai-org-glm-4.7 is a reasoning model: with thinking enabled it puts its
        # entire answer in `reasoning_content` and leaves `content` empty, which
        # breaks response_format=json_object parsing. We don't need a visible
        # chain-of-thought here since the JSON schema already has its own
        # "syntax_reasoning"/"mapping_reasoning" fields, so disable thinking to
        # get a reliable `content`.
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
            raise TranslationError(f"Venice API request failed: {exc}") from exc

    body = response.json()
    try:
        content = body["choices"][0]["message"]["content"]
    except (KeyError, IndexError) as exc:
        raise TranslationError(f"Unexpected Venice API response shape: {body}") from exc

    try:
        result = json.loads(content)
    except json.JSONDecodeError as exc:
        raise TranslationError(f"Model did not return valid JSON: {content}") from exc

    required_keys = {
        "translated_query",
        "confidence",
        "syntax_reasoning",
        "mapping_reasoning",
        "schema_mapping_applicable",
        "mapping_used",
        "needs_review",
    }
    missing = required_keys - result.keys()
    if missing:
        raise TranslationError(f"Model response missing fields {missing}: {result}")

    return result
