"""HTTP fetch for R2 public manifest and date shards."""

from __future__ import annotations

from typing import Any

import httpx

from paper_search_core.r2_urls import public_url_for_base


def fetch_manifest(*, public_base_url: str, manifest_path: str) -> dict[str, Any]:
    url = public_url_for_base(public_base_url, manifest_path)
    response = httpx.get(url, timeout=30.0, follow_redirects=True)
    response.raise_for_status()
    return response.json()


def fetch_date_shard(*, public_base_url: str, index_key: str) -> dict[str, Any]:
    url = public_url_for_base(public_base_url, index_key)
    response = httpx.get(url, timeout=30.0, follow_redirects=True)
    response.raise_for_status()
    return response.json()


def items_for_date(
    *,
    public_base_url: str,
    run_date: str,
    date_payload: dict[str, Any],
    items_key: str,
) -> list[dict[str, Any]]:
    index_key = str(date_payload.get("index_key") or "")
    if not index_key:
        return []

    shard = fetch_date_shard(public_base_url=public_base_url, index_key=index_key)
    if str(shard.get("date") or run_date) != run_date:
        return []
    items = shard.get(items_key) or []
    return items if isinstance(items, list) else []
