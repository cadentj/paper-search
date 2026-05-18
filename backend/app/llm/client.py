"""OpenRouter LLM client for structured outputs."""

import asyncio
import random
import time
from typing import TypeVar

from openai import (
    APIConnectionError,
    APIStatusError,
    APITimeoutError,
    AsyncOpenAI,
    OpenAI,
)
from pydantic import BaseModel
from app.core.config import LLM_MAX_RETRIES, LLM_RETRY_BASE_SECONDS, settings
from app.llm.config import JUDGE_PROFILE, LLMModelConfig, get_llm_config


OPENROUTER_BASE_URL = "https://openrouter.ai/api/v1"
TRANSIENT_STATUS_CODES = {408, 429, 500, 502, 503, 504}
LLM_REQUEST_TIMEOUT_SECONDS = 120.0
ResponseModelT = TypeVar("ResponseModelT", bound=BaseModel)


def _require_api_key() -> str:
    if not settings.OPENROUTER_API_KEY:
        raise ValueError("OPENROUTER_API_KEY is not set")
    return settings.OPENROUTER_API_KEY


def _client() -> OpenAI:
    return OpenAI(
        base_url=OPENROUTER_BASE_URL,
        api_key=_require_api_key(),
        timeout=LLM_REQUEST_TIMEOUT_SECONDS,
    )


def _async_client() -> AsyncOpenAI:
    return AsyncOpenAI(
        base_url=OPENROUTER_BASE_URL,
        api_key=_require_api_key(),
        timeout=LLM_REQUEST_TIMEOUT_SECONDS,
    )


def _response_input(system_prompt: str, user_prompt: str) -> list[dict]:
    return [
        {"role": "system", "content": system_prompt},
        {"role": "user", "content": user_prompt},
    ]


def _provider_body(model_config: LLMModelConfig) -> dict:
    return {"provider": {"order": [model_config.provider]}}


def _parse_structured_response(
    response,
    response_model: type[ResponseModelT],
    model_config: LLMModelConfig,
) -> dict:
    for output in getattr(response, "output", []):
        for content_item in getattr(output, "content", []):
            parsed = getattr(content_item, "parsed", None)
            if parsed is None:
                continue
            content = parsed.model_dump() if hasattr(parsed, "model_dump") else parsed
            return {
                "content": content,
                "model": getattr(response, "model", None) or model_config.model,
                "response_id": getattr(response, "id", ""),
            }

    raise RuntimeError(
        f"Structured LLM response did not include parsed {response_model.__name__}"
    )


def _parse_call(
    client: OpenAI,
    system_prompt: str,
    user_prompt: str,
    model_config: LLMModelConfig,
    response_model: type[ResponseModelT],
):
    return client.responses.parse(
        model=model_config.model,
        input=_response_input(system_prompt, user_prompt),
        extra_body=_provider_body(model_config),
        text_format=response_model,
    )


async def _async_parse_call(
    client: AsyncOpenAI,
    system_prompt: str,
    user_prompt: str,
    model_config: LLMModelConfig,
    response_model: type[ResponseModelT],
):
    return await client.responses.parse(
        model=model_config.model,
        input=_response_input(system_prompt, user_prompt),
        extra_body=_provider_body(model_config),
        text_format=response_model,
    )


def _is_transient_error(exc: Exception) -> bool:
    if isinstance(exc, APIStatusError):
        return exc.status_code in TRANSIENT_STATUS_CODES
    return isinstance(exc, (APIConnectionError, APITimeoutError))


def _retry_delay(attempt: int) -> float:
    base = LLM_RETRY_BASE_SECONDS * (2 ** max(attempt - 1, 0))
    return base + random.uniform(0, min(base, 1.0))


def call_llm(
    system_prompt: str,
    user_prompt: str,
    *,
    response_model: type[ResponseModelT],
    profile: str = JUDGE_PROFILE,
) -> dict:
    """Call OpenRouter with structured output support.

    Returns dict with keys: content, model, response_id
    """
    model_config = get_llm_config(profile)
    last_exc: Exception | None = None

    with _client() as client:
        for attempt in range(LLM_MAX_RETRIES + 1):
            try:
                response = _parse_call(
                    client,
                    system_prompt,
                    user_prompt,
                    model_config,
                    response_model,
                )
                return _parse_structured_response(response, response_model, model_config)
            except Exception as exc:
                last_exc = exc
                if attempt >= LLM_MAX_RETRIES or not _is_transient_error(exc):
                    raise
                time.sleep(_retry_delay(attempt + 1))

    raise RuntimeError("LLM call failed") from last_exc


async def async_call_llm(
    system_prompt: str,
    user_prompt: str,
    *,
    response_model: type[ResponseModelT],
    profile: str = JUDGE_PROFILE,
) -> dict:
    """Async OpenRouter call with retry/backoff for concurrent worker jobs."""
    model_config = get_llm_config(profile)
    last_exc: Exception | None = None

    async with _async_client() as client:
        for attempt in range(LLM_MAX_RETRIES + 1):
            try:
                response = await _async_parse_call(
                    client,
                    system_prompt,
                    user_prompt,
                    model_config,
                    response_model,
                )
                return _parse_structured_response(response, response_model, model_config)
            except Exception as exc:
                last_exc = exc
                if attempt >= LLM_MAX_RETRIES or not _is_transient_error(exc):
                    raise
                await asyncio.sleep(_retry_delay(attempt + 1))

    raise RuntimeError("LLM call failed") from last_exc


def stream_structured_response(
    *,
    system_prompt: str,
    user_prompt: str,
    response_model: type[ResponseModelT],
    on_text_delta=None,
    profile: str = JUDGE_PROFILE,
) -> dict:
    """Stream an OpenRouter Responses API structured output via the OpenAI SDK."""
    model_config = get_llm_config(profile)
    with _client() as client, client.responses.stream(
        model=model_config.model,
        input=_response_input(system_prompt, user_prompt),
        extra_body=_provider_body(model_config),
        text_format=response_model,
    ) as stream:
        for event in stream:
            if event.type == "response.output_text.delta":
                if on_text_delta:
                    on_text_delta(event.delta)
            elif event.type == "response.error":
                raise RuntimeError(str(event.error))

        final_response = stream.get_final_response()

    return _parse_structured_response(final_response, response_model, model_config)
