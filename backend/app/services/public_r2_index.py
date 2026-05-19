"""Shared HTTP helpers for R2 public object URLs (HTML viewers)."""

from __future__ import annotations

import threading
import httpx


_http_client: httpx.Client | None = None
_http_client_lock = threading.Lock()


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


def has_searchable_text(record: dict, *, text_fields: tuple[str, ...]) -> bool:
    for field in text_fields:
        value = record.get(field)
        if isinstance(value, str) and value.strip():
            return True
    return False


def http_get_text(url: str) -> str | None:
    """GET a URL and return response body as text; None on failure."""
    try:
        response = _shared_client().get(url)
        response.raise_for_status()
        return response.text
    except httpx.HTTPError:
        return None
