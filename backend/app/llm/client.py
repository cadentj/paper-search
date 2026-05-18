"""OpenRouter LLM client for structured outputs."""

import asyncio
import json
import random

import httpx
from openai import OpenAI
from app.core.config import settings


OPENROUTER_URL = "https://openrouter.ai/api/v1/chat/completions"
OPENROUTER_BASE_URL = "https://openrouter.ai/api/v1"
TRANSIENT_STATUS_CODES = {408, 429, 500, 502, 503, 504}
LLM_REQUEST_TIMEOUT_SECONDS = 120.0


def _headers() -> dict:
    if not settings.OPENROUTER_API_KEY:
        raise ValueError("OPENROUTER_API_KEY is not set")

    return {
        "Authorization": f"Bearer {settings.OPENROUTER_API_KEY}",
        "Content-Type": "application/json",
    }


def _body(system_prompt: str, user_prompt: str, response_format: dict | None) -> dict:
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

    return body


def _parse_response(data: dict) -> dict:
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


def _is_transient_error(exc: Exception) -> bool:
    if isinstance(exc, httpx.HTTPStatusError):
        return exc.response.status_code in TRANSIENT_STATUS_CODES
    return isinstance(exc, (httpx.TimeoutException, httpx.TransportError))


def _retry_delay(attempt: int) -> float:
    base = settings.LLM_RETRY_BASE_SECONDS * (2 ** max(attempt - 1, 0))
    return base + random.uniform(0, min(base, 1.0))


def call_llm(
    system_prompt: str,
    user_prompt: str,
    response_format: dict | None = None,
) -> dict:
    """Call OpenRouter with structured output support.

    Returns dict with keys: content, model, response_id
    """
    headers = _headers()
    body = _body(system_prompt, user_prompt, response_format)
    last_exc: Exception | None = None

    with httpx.Client(timeout=LLM_REQUEST_TIMEOUT_SECONDS) as client:
        for attempt in range(settings.LLM_MAX_RETRIES + 1):
            try:
                resp = client.post(OPENROUTER_URL, headers=headers, json=body)
                resp.raise_for_status()
                return _parse_response(resp.json())
            except Exception as exc:
                last_exc = exc
                if attempt >= settings.LLM_MAX_RETRIES or not _is_transient_error(exc):
                    raise
                import time

                time.sleep(_retry_delay(attempt + 1))

    raise RuntimeError("LLM call failed") from last_exc


async def async_call_llm(
    system_prompt: str,
    user_prompt: str,
    response_format: dict | None = None,
) -> dict:
    """Async OpenRouter call with retry/backoff for concurrent worker jobs."""
    headers = _headers()
    body = _body(system_prompt, user_prompt, response_format)
    last_exc: Exception | None = None

    async with httpx.AsyncClient(timeout=LLM_REQUEST_TIMEOUT_SECONDS) as client:
        for attempt in range(settings.LLM_MAX_RETRIES + 1):
            try:
                resp = await client.post(OPENROUTER_URL, headers=headers, json=body)
                resp.raise_for_status()
                return _parse_response(resp.json())
            except Exception as exc:
                last_exc = exc
                if attempt >= settings.LLM_MAX_RETRIES or not _is_transient_error(exc):
                    raise
                await asyncio.sleep(_retry_delay(attempt + 1))

    raise RuntimeError("LLM call failed") from last_exc


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


def stream_structured_response(
    *,
    system_prompt: str,
    user_prompt: str,
    text_format,
    on_text_delta=None,
) -> dict:
    """Stream an OpenRouter Responses API structured output via the OpenAI SDK."""
    if not settings.OPENROUTER_API_KEY:
        raise ValueError("OPENROUTER_API_KEY is not set")

    client = OpenAI(
        base_url=OPENROUTER_BASE_URL,
        api_key=settings.OPENROUTER_API_KEY,
        timeout=LLM_REQUEST_TIMEOUT_SECONDS,
    )

    text_buffer = ""

    with client.responses.stream(
        model=settings.OPENROUTER_MODEL,
        input=[
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": user_prompt},
        ],
        text_format=text_format,
    ) as stream:
        for event in stream:
            if event.type == "response.output_text.delta":
                text_buffer += event.delta
                if on_text_delta:
                    on_text_delta(event.delta)
            elif event.type == "response.error":
                raise RuntimeError(str(event.error))

        final_response = stream.get_final_response()

    output_text = final_response.output[0].content[0]
    parsed = getattr(output_text, "parsed", None)
    if parsed is not None:
        content = parsed.model_dump() if hasattr(parsed, "model_dump") else parsed
    else:
        raw_text = getattr(output_text, "text", None) or text_buffer
        content = text_format.model_validate_json(raw_text).model_dump()

    return {
        "content": content,
        "model": final_response.model or settings.OPENROUTER_MODEL,
        "response_id": final_response.id,
    }
