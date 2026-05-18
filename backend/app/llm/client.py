"""OpenRouter LLM client for structured outputs."""

import json
import httpx
from app.core.config import settings


OPENROUTER_URL = "https://openrouter.ai/api/v1/chat/completions"


def call_llm(
    system_prompt: str,
    user_prompt: str,
    response_format: dict | None = None,
) -> dict:
    """Call OpenRouter with structured output support.

    Returns dict with keys: content, model, response_id
    """
    if not settings.OPENROUTER_API_KEY:
        raise ValueError("OPENROUTER_API_KEY is not set")

    headers = {
        "Authorization": f"Bearer {settings.OPENROUTER_API_KEY}",
        "Content-Type": "application/json",
    }

    body: dict = {
        "model": settings.OPENROUTER_MODEL,
        "provider": {"order": [settings.OPENROUTER_PROVIDER]},
        "messages": [
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": user_prompt},
        ],
    }

    if response_format:
        body["response_format"] = response_format

    with httpx.Client(timeout=120.0) as client:
        resp = client.post(OPENROUTER_URL, headers=headers, json=body)
        resp.raise_for_status()
        data = resp.json()

    choice = data["choices"][0]
    content_str = choice["message"]["content"]

    try:
        content = json.loads(content_str)
    except (json.JSONDecodeError, TypeError):
        content = {"raw": content_str}

    return {
        "content": content,
        "model": data.get("model", settings.OPENROUTER_MODEL),
        "response_id": data.get("id", ""),
    }


def build_json_schema(name: str, schema: dict) -> dict:
    """Build OpenRouter response_format for JSON schema."""
    return {
        "type": "json_schema",
        "json_schema": {
            "name": name,
            "strict": True,
            "schema": schema,
        },
    }
