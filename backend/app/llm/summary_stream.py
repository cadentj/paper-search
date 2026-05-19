"""Helpers for streaming partial daily-search summary structured output."""

from __future__ import annotations

import json


def extract_partial_summary(buffer: str) -> str | None:
    """Return the best-effort partial value of the JSON ``summary`` string field."""
    marker = '"summary"'
    marker_idx = buffer.find(marker)
    if marker_idx == -1:
        return None

    colon_idx = buffer.find(":", marker_idx + len(marker))
    if colon_idx == -1:
        return None

    idx = colon_idx + 1
    while idx < len(buffer) and buffer[idx] in " \n\r\t":
        idx += 1
    if idx >= len(buffer) or buffer[idx] != '"':
        return None

    decoded, _consumed = _decode_json_string(buffer, idx)
    return decoded


def _decode_json_string(buffer: str, start: int) -> tuple[str, int]:
    """Decode a JSON string starting at the opening quote index."""
    if start >= len(buffer) or buffer[start] != '"':
        return "", start

    pieces: list[str] = []
    idx = start + 1
    while idx < len(buffer):
        char = buffer[idx]
        if char == '"':
            return "".join(pieces), idx + 1
        if char != "\\":
            pieces.append(char)
            idx += 1
            continue

        idx += 1
        if idx >= len(buffer):
            break

        escape = buffer[idx]
        if escape == "u":
            if idx + 4 < len(buffer):
                try:
                    pieces.append(chr(int(buffer[idx + 1 : idx + 5], 16)))
                    idx += 5
                    continue
                except ValueError:
                    break
            break

        pieces.append(
            {
                '"': '"',
                "\\": "\\",
                "/": "/",
                "b": "\b",
                "f": "\f",
                "n": "\n",
                "r": "\r",
                "t": "\t",
            }.get(escape, escape)
        )
        idx += 1

    return "".join(pieces), idx


def extract_complete_summary(buffer: str) -> str | None:
    """Return the summary field when the buffer contains valid structured JSON."""
    try:
        payload = json.loads(buffer)
    except json.JSONDecodeError:
        return None
    summary = payload.get("summary")
    return summary if isinstance(summary, str) else None
