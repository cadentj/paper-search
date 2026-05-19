"""OpenRouter LLM client for structured outputs."""

from typing import TypeVar

import backoff
from openai import (
    APIConnectionError,
    APIStatusError,
    APITimeoutError,
    AsyncOpenAI,
    OpenAI,
)
from pydantic import BaseModel

from app.config import LLM_MAX_RETRIES, LLM_RETRY_BASE_SECONDS, settings
from app.llm.config import JUDGE_PROFILE, LLMModelConfig, get_llm_config

OPENROUTER_BASE_URL = "https://openrouter.ai/api/v1"
TRANSIENT_STATUS_CODES = {408, 429, 500, 502, 503, 504}
LLM_REQUEST_TIMEOUT_SECONDS = 120.0
ResponseModelT = TypeVar("ResponseModelT", bound=BaseModel)


def _is_transient_error(exc: Exception) -> bool:
    if isinstance(exc, APIStatusError):
        return exc.status_code in TRANSIENT_STATUS_CODES
    return isinstance(exc, (APIConnectionError, APITimeoutError))


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


@backoff.on_exception(
    backoff.expo,
    Exception,
    max_tries=LLM_MAX_RETRIES + 1,
    base=LLM_RETRY_BASE_SECONDS,
    factor=2,
    jitter=backoff.random_jitter,
    giveup=lambda exc: not _is_transient_error(exc),
)
async def _async_call_llm_with_client(
    client: AsyncOpenAI,
    system_prompt: str,
    user_prompt: str,
    model_config: LLMModelConfig,
    response_model: type[ResponseModelT],
) -> dict:
    response = await _async_parse_call(
        client, system_prompt, user_prompt, model_config, response_model
    )
    return _parse_structured_response(response, response_model, model_config)


async def async_call_llm(
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
    async with _async_client() as client:
        return await _async_call_llm_with_client(
            client, system_prompt, user_prompt, model_config, response_model
        )


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
    with (
        _client() as client,
        client.responses.stream(
            model=model_config.model,
            input=_response_input(system_prompt, user_prompt),
            extra_body=_provider_body(model_config),
            text_format=response_model,
        ) as stream,
    ):
        for event in stream:
            if event.type == "response.output_text.delta":
                if on_text_delta:
                    on_text_delta(event.delta)
            elif event.type == "response.error":
                raise RuntimeError(str(event.error))

        final_response = stream.get_final_response()

    return _parse_structured_response(final_response, response_model, model_config)
