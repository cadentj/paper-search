"""Shared HTTP + JSON manifest/date-shard readers for R2 public index layouts (arXiv, LessWrong)."""

from __future__ import annotations

import threading
import time
from dataclasses import dataclass
from typing import Any
from urllib.parse import quote, urljoin

import httpx


@dataclass(frozen=True)
class R2SourceConfig:
    public_base_url: str
    manifest_path: str
    ttl_seconds: int
    items_key: str


_http_client: httpx.Client | None = None
_http_client_lock = threading.Lock()
_cache_lock = threading.Lock()

_manifest_cache: dict[str, tuple[float, dict[str, Any]]] = {}
_date_shard_cache: dict[str, tuple[float, dict[str, Any]]] = {}


def public_url_for_base(base_url: str, path_or_key: str) -> str:
    base = base_url.rstrip("/") + "/"
    path = path_or_key.lstrip("/")
    return urljoin(base, quote(path, safe="/:.-_"))


def has_searchable_text(item: dict[str, Any], *, text_fields: tuple[str, ...]) -> bool:
    return any(str(item.get(f) or "").strip() for f in text_fields)


def _shared_client() -> httpx.Client:
    global _http_client
    with _http_client_lock:
        if _http_client is None:
            _http_client = httpx.Client(
                timeout=30.0,
                follow_redirects=True,
                limits=httpx.Limits(max_connections=32, max_keepalive_connections=16),
            )
        return _http_client


class ShardedPublicIndexReader:
    """Fetches manifest + date shards for one R2 public bucket (namespace disambiguates cache keys)."""

    def __init__(self, config: R2SourceConfig, *, namespace: str) -> None:
        self._config = config
        self._ns = namespace

    def fetch_manifest(self) -> dict[str, Any]:
        if not self._config.public_base_url.strip():
            return {"dates": {}}

        cache_key = f"{self._ns}:manifest"
        now = time.monotonic()
        with _cache_lock:
            hit = _manifest_cache.get(cache_key)
            if hit is not None and now - hit[0] < self._config.ttl_seconds:
                return hit[1]

        url = public_url_for_base(self._config.public_base_url, self._config.manifest_path)
        response = _shared_client().get(url)
        response.raise_for_status()
        payload = response.json()

        with _cache_lock:
            _manifest_cache[cache_key] = (now, payload)
        return payload

    def fetch_date_shard(self, index_key: str) -> dict[str, Any]:
        now = time.monotonic()
        cache_key = f"{self._ns}:{index_key}"
        with _cache_lock:
            hit = _date_shard_cache.get(cache_key)
            if hit is not None and now - hit[0] < self._config.ttl_seconds:
                return hit[1]

        url = public_url_for_base(self._config.public_base_url, index_key)
        response = _shared_client().get(url)
        response.raise_for_status()
        payload = response.json()

        with _cache_lock:
            _date_shard_cache[cache_key] = (now, payload)
        return payload

    def items_for_date(self, *, run_date: str, date_payload: dict[str, Any]) -> list[dict[str, Any]]:
        key = self._config.items_key
        inline = date_payload.get(key)
        if isinstance(inline, list):
            return inline

        index_key = str(date_payload.get("index_key") or "")
        if not index_key:
            return []

        shard = self.fetch_date_shard(index_key)
        if str(shard.get("date") or run_date) != run_date:
            return []
        items = shard.get(key) or []
        return items if isinstance(items, list) else []


def http_get_text(url: str) -> str | None:
    """GET a URL and return response body as text; None on failure. Shared by HTML viewers."""
    try:
        response = _shared_client().get(url)
        response.raise_for_status()
        return response.text
    except httpx.HTTPError:
        return None
