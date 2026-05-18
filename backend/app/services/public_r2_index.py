"""Shared HTTP helpers for R2 public object URLs (HTML viewers)."""

from __future__ import annotations

import threading
from typing import Any
import httpx

from paper_search_core.r2_urls import has_searchable_text, public_url_for_base


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


def http_get_text(url: str) -> str | None:
    """GET a URL and return response body as text; None on failure."""
    try:
        response = _shared_client().get(url)
        response.raise_for_status()
        return response.text
    except httpx.HTTPError:
        return None
