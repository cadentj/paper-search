from __future__ import annotations

from typing import Any
from urllib.parse import quote, urljoin


def public_url_for_base(base_url: str, path_or_key: str) -> str:
    base = base_url.rstrip("/") + "/"
    path = path_or_key.lstrip("/")
    return urljoin(base, quote(path, safe="/:.-_"))


def has_searchable_text(
    item: dict[str, Any], *, text_fields: tuple[str, ...]
) -> bool:
    return any(str(item.get(field) or "").strip() for field in text_fields)
