"""Public R2-backed LessWrong post provider."""

from __future__ import annotations

from datetime import datetime
from typing import Any

from app.core.config import settings
from app.services.public_r2_index import (
    R2SourceConfig,
    ShardedPublicIndexReader,
    has_searchable_text,
    http_get_text,
    public_url_for_base,
)

_LW_READER = ShardedPublicIndexReader(
    R2SourceConfig(
        public_base_url=settings.LESSWRONG_HTML_PUBLIC_BASE_URL,
        manifest_path=settings.LESSWRONG_HTML_INDEX_PATH,
        ttl_seconds=settings.LESSWRONG_PUBLIC_INDEX_TTL_SECONDS,
        items_key="posts",
    ),
    namespace="lesswrong",
)


def available_counts() -> dict[str, int]:
    index = fetch_index()
    return {
        day: int(payload.get("count") or 0)
        for day, payload in (index.get("dates") or {}).items()
    }


def fetch_public_cached_posts(*, run_date: str) -> tuple[list[dict[str, Any]], int]:
    index = fetch_index()
    date_payload = (index.get("dates") or {}).get(run_date)
    if not date_payload:
        return [], 0

    skipped_missing_text = 0
    posts: list[dict[str, Any]] = []
    for post in posts_for_date(run_date=run_date, date_payload=date_payload):
        post_id = str(post.get("post_id") or "")
        if not post_id:
            continue
        if not has_searchable_text(post, text_fields=("text_preview", "excerpt")):
            skipped_missing_text += 1
            continue

        html_key = str(post.get("html_key") or _html_key_for_post_id(post_id))
        html_url = public_url(html_key)
        transient_text = _transient_text_from_post_shard(post)
        posts.append(
            {
                "source_type": "lesswrong",
                "source_id": post_id,
                "title": post.get("title") or "Untitled LessWrong post",
                "abstract": "",
                "transient_text": transient_text,
                "authors": [author for author in [post.get("author")] if author],
                "categories": [],
                "published_at": _parse_datetime(post.get("posted_at")),
                "html_url": html_url,
                "landing_url": post.get("page_url"),
                "source_url": post.get("page_url"),
                "source_metadata": {
                    "baseScore": post.get("base_score"),
                    "html_key": html_key,
                },
            }
        )
    return posts, skipped_missing_text


def posts_for_date(*, run_date: str, date_payload: dict[str, Any]) -> list[dict[str, Any]]:
    return _LW_READER.items_for_date(run_date=run_date, date_payload=date_payload)


def _transient_text_from_post_shard(post: dict[str, Any]) -> str:
    raw = post.get("text_preview")
    if raw is None:
        raw = post.get("excerpt")
    if raw is None:
        return ""
    return _first_words(str(raw), settings.LESSWRONG_EXCERPT_WORDS)


def fetch_public_post_html(*, html_url: str | None = None, html_key: str | None = None) -> str | None:
    url = html_url or (public_url(html_key) if html_key else None)
    if not url:
        return None
    return http_get_text(url)


def fetch_index() -> dict[str, Any]:
    if not settings.LESSWRONG_HTML_PUBLIC_BASE_URL.strip():
        return {"dates": {}}
    return _LW_READER.fetch_manifest()


def fetch_date_index(*, index_key: str) -> dict[str, Any]:
    return _LW_READER.fetch_date_shard(index_key)


def public_url(path_or_key: str) -> str:
    return public_url_for_base(settings.LESSWRONG_HTML_PUBLIC_BASE_URL, path_or_key)


def _first_words(value: str, count: int) -> str:
    words = value.split()
    if len(words) <= count:
        return " ".join(words)
    return " ".join(words[:count])


def _parse_datetime(value: str | None) -> datetime | None:
    if not value:
        return None
    try:
        return datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError:
        return None


def _html_key_for_post_id(post_id: str) -> str:
    return f"data/{post_id[:2]}/{post_id}.html"
