"""LessWrong source — public R2 index access and provider."""

from __future__ import annotations

import logging
from datetime import date, datetime
from typing import Any

from app.core.config import settings
from app.models.paper import Paper
from app.services.public_r2_index import (
    ShardedPublicIndexReader,
    has_searchable_text,
    http_get_text,
    public_url_for_base,
)
from app.services.source_types import SourceFetchResult, candidate_from_record

logger = logging.getLogger(__name__)

_LW_READER = ShardedPublicIndexReader(
    public_base_url=settings.LESSWRONG_HTML_PUBLIC_BASE_URL,
    manifest_path=settings.LESSWRONG_HTML_INDEX_PATH,
    ttl_seconds=settings.LESSWRONG_PUBLIC_INDEX_TTL_SECONDS,
    items_key="posts",
    namespace="lesswrong",
)


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


def fetch_public_post_html(*, html_url: str | None = None, html_key: str | None = None) -> str | None:
    url = html_url or (public_url(html_key) if html_key else None)
    if not url:
        return None
    return http_get_text(url)


def fetch_index() -> dict[str, Any]:
    if not settings.LESSWRONG_HTML_PUBLIC_BASE_URL.strip():
        return {"dates": {}}
    return _LW_READER.fetch_manifest()


def public_url(path_or_key: str) -> str:
    return public_url_for_base(settings.LESSWRONG_HTML_PUBLIC_BASE_URL, path_or_key)


class LessWrongProvider:
    source_type = "lesswrong"

    def count_for_date(self, run_date: date) -> int:
        try:
            index = fetch_index()
        except Exception:
            logger.exception("failed to fetch LessWrong index count for %s", run_date)
            return 0
        payload = (index.get("dates") or {}).get(run_date.isoformat())
        return int((payload or {}).get("count") or 0)

    def candidates_for_date(self, run_date: date) -> SourceFetchResult:
        try:
            records, skipped = fetch_public_cached_posts(run_date=run_date.isoformat())
        except Exception as exc:
            logger.exception("failed to fetch cached LessWrong posts for %s", run_date)
            return SourceFetchResult(items=[], errors=[f"LessWrong fetch failed: {exc}"])
        skipped_map = {"lesswrong": skipped} if skipped else {}
        return SourceFetchResult(
            items=[candidate_from_record(record) for record in records],
            skipped_missing_text=skipped_map,
        )

    def html_for_paper(self, paper: Paper) -> dict[str, str | None]:
        try:
            html = fetch_public_post_html(
                html_url=paper.html_url,
                html_key=(paper.source_metadata or {}).get("html_key"),
            )
        except Exception:
            logger.exception("failed to fetch LessWrong HTML for paper=%s", paper.id)
            html = None
        return {
            "html": html,
            "source_url": paper.source_url or paper.landing_url,
        }


def _transient_text_from_post_shard(post: dict[str, Any]) -> str:
    raw = post.get("text_preview")
    if raw is None:
        raw = post.get("excerpt")
    if raw is None:
        return ""
    return _first_words(str(raw), settings.LESSWRONG_EXCERPT_WORDS)


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
