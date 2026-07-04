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
- When translating to Flux: `aggregateWindow`'s `fn` argument only accepts genuine Flux reducers \
(`mean`, `sum`, `count`, `min`, `max`, `last`, `first`, etc.). PromQL counter functions like \
`rate`, `irate`, and `increase` are NOT valid `fn` values (e.g. `aggregateWindow(fn: rate, ...)` \
or `aggregateWindow(fn: increase, ...)` are invalid Flux and will fail at query time). Instead:
  - For `rate()`/`irate()`, use `derivative(unit: <window>, nonNegative: true)`.
  - For `increase()`, use `aggregateWindow(every: <window>, fn: last, createEmpty: false)` \
followed by `difference(nonNegative: true)` (this gives the increase within each window, \
matching PromQL's `increase()` more closely than a raw derivative would).
- When translating to a Flux `from(bucket: "...")` call: if a target bucket name is given below \
the query, use that exact name verbatim - never invent a placeholder like "your-bucket" or leave \
it blank. If no bucket name is given below the query and the translation still needs one, use an \
obviously-fake placeholder (e.g. "REPLACE_ME_BUCKET") AND set "needs_review" to true - a query \
with a guessed bucket name is not safe to trust silently.
- Aggregation/grouping in Flux vs PromQL - Flux tables are grouped by ALL tags by default:
  - A PromQL aggregation with an explicit "by (...)" clause keeps exactly those labels as \
separate groups and merges away everything else. If Flux's default per-tag grouping doesn't \
already match those columns, add `group(columns: [<by-columns>])` to reshape down to exactly the \
"by" columns. This is a RESHAPE only - never follow it with an additional flattening aggregate \
call, since the "by" clause deliberately keeps those groups separate rather than collapsing them.
  - A PromQL aggregation with NO "by"/"without" clause implicitly merges across ALL labels into a \
single result. Translate this with `group(columns: [])` (or `group(columns: ["_measurement", \
"_field"])` to keep those but drop the tag columns) followed by exactly one flattening aggregate \
call (see the panel-type rules below for which one) - otherwise Flux silently keeps each tag \
combination as its own separate number instead of merging them the way PromQL does. Always set \
"needs_review" to true for this implicit-full-merge case, even when the rest of the translation \
looks direct, since it's easy to introduce incorrectly.
- The target Grafana panel type (given below the query, if known) determines what the pipeline's \
final step may be:
  - "stat"/"gauge" panels expect a single current value. Only when the source query is the \
implicit-full-merge case above should the pipeline end with a flattening aggregate call: `sum()` \
for a counter-derived total (the query used `rate()`/`irate()`/`increase()`), or, for a bare \
aggregation over a gauge-type metric with none of those functions, `last()` per tag-group FIRST \
(before the `group(columns: [])` merge) then `sum()` - never sum a gauge's raw samples over the \
whole visible range, that adds up hundreds of samples into a meaningless inflated number instead \
of reporting its current value.
    Worked example: PromQL `sum(some_gauge{plan=~"a|b"})` on a "gauge" panel with two matching \
tag-groups (plan="a", plan="b") MUST call `last()` BEFORE `group(columns: [])`, never after:
        |> filter(...)
        |> last()
        |> group(columns: [])
        |> sum()
    Putting `group(columns: [])` before `last()` is wrong and silently produces a bad number: it \
merges both tag-groups' raw samples into one table first, so `last()` then returns only whichever \
single sample happens to be most recent across BOTH groups combined - discarding the other \
group's value entirely - instead of each group's own latest value being captured and then summed.
  - "timeseries"/"graph" panels plot a line over time and need the `_time` column preserved on \
every output row, REGARDLESS of whether the source query used "by" or implicit full-merge. Do NOT \
end the pipeline with a bare flattening aggregate call (a trailing `sum()`/`mean()`/`last()` with \
no window) - it drops `_time` and breaks the chart ("Data is missing a time field"). Stop after \
`aggregateWindow(...)` (or `derivative`/`difference`), which already produces one row per time \
bucket - even the implicit-full-merge case feeding a timeseries panel should stop there, using \
`group(columns: [])` only to merge tags and never following it with a flattening call.
  - If the panel type is missing or doesn't clearly indicate either case, prefer preserving \
`_time` (the timeseries-safe approach) and set "needs_review" to true.
  - Worked example: PromQL `sum by (mode) (rate(cpu_seconds_total[5m]))` on a "timeseries" panel \
must end at `group()`, with NO trailing `sum()`/other flatten, even though the PromQL function is \
literally named "sum":
      from(bucket: "...")
        |> range(...)
        |> filter(fn: (r) => r["_measurement"] == "...")
        |> filter(fn: (r) => r["_field"] == "...")
        |> derivative(unit: 5m, nonNegative: true)
        |> group(columns: ["mode"])
    Do NOT add `|> sum()` after that `group()` - the PromQL function being literally named "sum" \
does not mean the Flux translation needs a trailing `sum()` call; the "by" clause already did the \
only aggregation this query needs (reshaping per-mode), and a timeseries panel must keep `_time`.
- If the confirmed schema mapping given below the query includes label -> tag mappings for a \
metric's labels (shown indented under that metric's measurement/field line), use those exact \
target tag names when translating that metric's label filters/grouping - do NOT assume a \
Prometheus label name carries over to InfluxDB unchanged just because the strings match, and do \
NOT assume it's unusable just because they differ. If the query uses a label with no \
corresponding entry in the given label -> tag mappings, you must still translate it (using the \
label name as-is, the same way you would with no mapping given at all), but set "needs_review" to \
true and say in "mapping_reasoning" that this tag name is a guess.
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
        for lm in m.get("label_mappings", []) or []:
            lines.append(f'    label "{lm["source_label"]}" -> tag "{lm["target_tag"]}"')
    return (
        "\n\nConfirmed schema mapping (source metric -> target measurement/field, with any "
        "label -> tag mappings indented beneath):\n" + "\n".join(lines)
    )


def _build_bucket_context(target_bucket: str | None) -> str:
    if not target_bucket:
        return ""
    return f'\n\nTarget InfluxDB bucket (use this exact name in `from(bucket: "...")`): "{target_bucket}"'


def _build_panel_type_context(panel_type: str | None) -> str:
    if not panel_type:
        return ""
    return f"\n\nTarget Grafana panel type: {panel_type}"


def _build_user_prompt(
    query: str,
    source_language: str,
    target_language: str,
    schema_mapping: list[dict] | None = None,
    target_bucket: str | None = None,
    panel_type: str | None = None,
) -> str:
    return (
        f"Source query language: {source_language}\n"
        f"Target query language: {target_language}\n"
        f"Query to translate:\n{query}"
        f"{_build_mapping_context(schema_mapping)}"
        f"{_build_bucket_context(target_bucket)}"
        f"{_build_panel_type_context(panel_type)}"
    )


async def translate_query(
    query: str,
    source_language: str,
    target_language: str,
    schema_mapping: list[dict] | None = None,
    target_bucket: str | None = None,
    panel_type: str | None = None,
) -> dict:
    """Translate a single query string via Venice's chat completions API.

    `schema_mapping`, if given, is the user-confirmed list of {source, target, ...} entries
    from POST /propose-mapping - grounding the translation in the real target schema instead
    of guessed measurement/field names.

    `target_bucket`, if given, is the real InfluxDB bucket name (the same one schema_introspection
    already queries against) - grounding `from(bucket: ...)` in a real value instead of a guessed
    placeholder.

    `panel_type`, if given, is the Grafana panel type (e.g. "stat", "gauge", "timeseries") - it
    determines whether the Flux pipeline should end with a flattening aggregate (single-value
    panels) or preserve `_time` (timeseries panels).

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
                "content": _build_user_prompt(
                    query, source_language, target_language, schema_mapping, target_bucket, panel_type
                ),
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
