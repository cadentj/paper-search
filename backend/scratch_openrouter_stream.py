"""Scratch test for OpenAI SDK streaming against OpenRouter.

Run from repo root:
    cd backend
    python scratch_openrouter_stream.py

This intentionally does not import app settings, so it can verify the SDK
surface independently of the app's current httpx client.
"""

from __future__ import annotations

import json
import os
from pathlib import Path
from typing import List

from openai import OpenAI
from pydantic import BaseModel


ROOT = Path(__file__).resolve().parents[1]


def load_root_env() -> None:
    env_path = ROOT / ".env"
    if not env_path.exists():
        return
    for line in env_path.read_text().splitlines():
        line = line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, value = line.split("=", 1)
        os.environ.setdefault(key.strip(), value.strip())


class EntitiesModel(BaseModel):
    attributes: List[str]
    colors: List[str]
    animals: List[str]


def print_exception(exc: Exception) -> None:
    print(f"{type(exc).__name__}: {exc}")
    response = getattr(exc, "response", None)
    if response is not None:
        print(f"status_code={getattr(response, 'status_code', None)}")
        try:
            print(response.text)
        except Exception:
            pass


def test_responses_stream(client: OpenAI, model: str) -> None:
    print("\n=== responses.stream + text_format ===")
    with client.responses.stream(
        model=model,
        input=[
            {"role": "system", "content": "Extract entities from the input text"},
            {
                "role": "user",
                "content": "The quick brown fox jumps over the lazy dog with piercing blue eyes.",
            },
        ],
        text_format=EntitiesModel,
    ) as stream:
        for event in stream:
            print(f"event={event.type}")
            if event.type == "response.output_text.delta":
                print(event.delta, end="")
            elif event.type == "response.refusal.delta":
                print(event.delta, end="")
            elif event.type == "response.error":
                print(event.error)
        final_response = stream.get_final_response()
        print("\nfinal_response:")
        print(final_response)


def test_chat_stream(client: OpenAI, model: str) -> None:
    print("\n=== chat.completions stream + response_format ===")
    schema = EntitiesModel.model_json_schema()
    stream = client.chat.completions.create(
        model=model,
        messages=[
            {"role": "system", "content": "Extract entities from the input text."},
            {
                "role": "user",
                "content": "The quick brown fox jumps over the lazy dog with piercing blue eyes.",
            },
        ],
        response_format={
            "type": "json_schema",
            "json_schema": {
                "name": "entities",
                "strict": True,
                "schema": schema,
            },
        },
        stream=True,
    )

    buffer = ""
    for chunk in stream:
        delta = chunk.choices[0].delta.content or ""
        buffer += delta
        print(delta, end="")

    print("\nparsed:")
    print(json.loads(buffer))


def main() -> None:
    load_root_env()
    api_key = os.environ.get("OPENROUTER_API_KEY")
    model = os.environ.get("OPENROUTER_MODEL", "deepseek/deepseek-v4-flash")
    if not api_key:
        raise RuntimeError("OPENROUTER_API_KEY is not set")

    client = OpenAI(
        base_url="https://openrouter.ai/api/v1",
        api_key=api_key,
    )

    for test in (test_responses_stream, test_chat_stream):
        try:
            test(client, model)
        except Exception as exc:
            print_exception(exc)


if __name__ == "__main__":
    main()
