from __future__ import annotations

import base64
import json
from datetime import datetime


def encode_cursor(value: datetime, item_id: str) -> str:
    payload = {"at": value.isoformat(), "id": item_id}
    raw = json.dumps(payload, separators=(",", ":")).encode("utf-8")
    return base64.urlsafe_b64encode(raw).decode("ascii")


def decode_cursor(cursor: str | None) -> tuple[datetime, str] | None:
    if not cursor:
        return None
    try:
        raw = base64.urlsafe_b64decode(cursor.encode("ascii"))
        payload = json.loads(raw.decode("utf-8"))
        value = datetime.fromisoformat(payload["at"])
        if value.tzinfo is not None:
            value = value.replace(tzinfo=None)
        return value, str(payload["id"])
    except Exception as exc:
        raise ValueError("Invalid cursor") from exc


def apply_cursor(items: list, cursor: str | None) -> list:
    decoded = decode_cursor(cursor)
    if not decoded:
        return items
    value, item_id = decoded
    return [
        item
        for item in items
        if item.created_at > value or (item.created_at == value and item.id > item_id)
    ]
