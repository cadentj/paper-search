"""Shared R2 JSON manifest and date-shard upload helpers (arXiv, LessWrong)."""

from __future__ import annotations

import json
from typing import Any


def normalize_prefix(prefix: str) -> str:
    stripped = prefix.strip("/")
    return f"{stripped}/" if stripped else ""


def date_index_key(*, date: str, date_index_prefix: str) -> str:
    return f"{normalize_prefix(date_index_prefix)}{date}.json"


def json_body(payload: dict[str, Any], *, pretty: bool = False) -> str:
    if pretty:
        return json.dumps(payload, indent=2, sort_keys=False) + "\n"
    return json.dumps(payload, separators=(",", ":"), sort_keys=False) + "\n"


def upload_sharded_index(
    client,
    *,
    bucket: str,
    index_key: str,
    manifest: dict[str, Any],
    date_shards: dict[str, dict[str, Any]],
    pretty: bool = False,
) -> None:
    client.put_object(
        Bucket=bucket,
        Key=index_key,
        Body=json_body(manifest, pretty=pretty).encode("utf-8"),
        ContentType="application/json",
        CacheControl="no-cache",
    )
    print(f"Uploaded s3://{bucket}/{index_key}")

    for day, shard in date_shards.items():
        key = manifest["dates"][day]["index_key"]
        client.put_object(
            Bucket=bucket,
            Key=key,
            Body=json_body(shard, pretty=pretty).encode("utf-8"),
            ContentType="application/json",
            CacheControl="public, max-age=31536000, immutable",
        )
    print(f"Uploaded {len(date_shards)} date shards")
