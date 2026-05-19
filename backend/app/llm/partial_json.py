from __future__ import annotations

import json
from collections.abc import Callable


def partial_string_field(buffer: str, field_name: str) -> str | None:
    marker_idx = buffer.find(f'"{field_name}"')
    if marker_idx == -1:
        return None

    colon_idx = buffer.find(":", marker_idx + len(field_name) + 2)
    if colon_idx == -1:
        return None

    idx = colon_idx + 1
    while idx < len(buffer) and buffer[idx] in " \n\r\t":
        idx += 1
    if idx >= len(buffer) or buffer[idx] != '"':
        return None

    decoded, _consumed = _decode_string(buffer, idx)
    return decoded


def complete_string_field(buffer: str, field_name: str) -> str | None:
    try:
        payload = json.loads(buffer)
    except json.JSONDecodeError:
        return None
    value = payload.get(field_name)
    return value if isinstance(value, str) else None


def complete_array_items(
    buffer: str,
    field_name: str,
    normalize: Callable[[dict], dict | None],
) -> list[dict]:
    decoder = json.JSONDecoder()
    marker_idx = buffer.find(f'"{field_name}"')
    if marker_idx == -1:
        return []

    array_start = buffer.find("[", marker_idx)
    if array_start == -1:
        return []

    idx = array_start + 1
    results: list[dict] = []
    while idx < len(buffer):
        while idx < len(buffer) and buffer[idx] in " \n\r\t,":
            idx += 1
        if idx >= len(buffer) or buffer[idx] == "]":
            break
        try:
            obj, next_idx = decoder.raw_decode(buffer, idx)
        except json.JSONDecodeError:
            break
        if isinstance(obj, dict):
            normalized = normalize(obj)
            if normalized:
                results.append(normalized)
        idx = next_idx

    return results


def _decode_string(buffer: str, start: int) -> tuple[str, int]:
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
