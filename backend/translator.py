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
  "reasoning": string,
  "needs_review": boolean
}

Rules:
- "reasoning" should be a brief explanation of the translation and any assumptions you made \
(e.g. how variables like $node or $__rate_interval were carried over, how a function was mapped).
- Set "needs_review" to true whenever the source query uses label filters, regex matching, \
boolean/comparison operators, or functions that do not have a clean 1:1 equivalent in the \
target language. Set it to false only when the translation is a direct, unambiguous mapping.
- If you set "needs_review" to true, "confidence" should generally be "medium" or "low".
"""


class TranslationError(RuntimeError):
    pass


def _build_user_prompt(query: str, source_language: str, target_language: str) -> str:
    return (
        f"Source query language: {source_language}\n"
        f"Target query language: {target_language}\n"
        f"Query to translate:\n{query}"
    )


async def translate_query(query: str, source_language: str, target_language: str) -> dict:
    """Translate a single query string via Venice's chat completions API.

    Returns a dict with keys: translated_query, confidence, reasoning, needs_review.
    Raises TranslationError if the API call fails or the model's response isn't
    valid JSON matching the expected shape.
    """
    if not VENICE_API_KEY:
        raise TranslationError("VENICE_API_KEY is not set")

    payload = {
        "model": TRANSLATION_MODEL,
        "messages": [
            {"role": "system", "content": SYSTEM_PROMPT},
            {"role": "user", "content": _build_user_prompt(query, source_language, target_language)},
        ],
        "response_format": {"type": "json_object"},
        "temperature": 0.2,
        # zai-org-glm-4.7 is a reasoning model: with thinking enabled it puts its
        # entire answer in `reasoning_content` and leaves `content` empty, which
        # breaks response_format=json_object parsing. We don't need a visible
        # chain-of-thought here since the JSON schema already has its own
        # "reasoning" field, so disable thinking to get a reliable `content`.
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

    missing = {"translated_query", "confidence", "reasoning", "needs_review"} - result.keys()
    if missing:
        raise TranslationError(f"Model response missing fields {missing}: {result}")

    return result
