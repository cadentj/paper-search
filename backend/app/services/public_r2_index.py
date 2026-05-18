"""Shared HTTP helpers for R2 public object URLs (HTML viewers)."""

from __future__ import annotations

import threading
from typing import Any
from urllib.parse import quote, urljoin

import httpx


_http_client: httpx.Client | None = None
_http_client_lock = threading.Lock()


def public_url_for_base(base_url: str, path_or_key: str) -> str:
    base = base_url.rstrip("/") + "/"
    path = path_or_key.lstrip("/")
    return urljoin(base, quote(path, safe="/:.-_"))


def has_searchable_text(
    item: dict[str, Any], *, text_fields: tuple[str, ...]
) -> bool:
    return any(str(item.get(f) or "").strip() for f in text_fields)


def _shared_client() -> httpx.Client:
    global _http_client
    with _http_client_lock:
        if _http_client is None:
            _http_client = httpx.Client(
                timeout=30.0,
                follow_redirects=True,
                limits=httpx.Limits(
                    max_connections=32, max_keepalive_connections=16
                ),
            )
        return _http_client


def http_get_text(url: str) -> str | None:
    """GET a URL and return response body as text; None on failure."""
    try:
        response = _shared_client().get(url)
        response.raise_for_status()
        return response.text
    except httpx.HTTPError:
        return None
