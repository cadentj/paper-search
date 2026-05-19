from __future__ import annotations

from app.llm.partial_json import complete_string_field, partial_string_field


def extract_partial_summary(buffer: str) -> str | None:
    return partial_string_field(buffer, "summary")


def extract_complete_summary(buffer: str) -> str | None:
    return complete_string_field(buffer, "summary")
