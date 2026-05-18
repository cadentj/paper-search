"""Public R2-backed LessWrong post provider."""

from __future__ import annotations

import threading
import time
from datetime import datetime
from typing import Any
from urllib.parse import quote, urljoin

import httpx
from bs4 import BeautifulSoup

from app.core.config import settings


_index_cache: dict[str, Any] | None = None
_index_cached_at = 0.0
_date_index_cache: dict[str, dict[str, Any]] = {}
_date_index_cached_at: dict[str, float] = {}
_index_lock = threading.Lock()


def available_counts() -> dict[str, int]:
    index = fetch_index()
    return {
        day: int(payload.get("count") or 0)
        for day, payload in (index.get("dates") or {}).items()
    }


def fetch_public_cached_posts(*, run_date: str) -> list[dict[str, Any]]:
    index = fetch_index()
    date_payload = (index.get("dates") or {}).get(run_date)
    if not date_payload:
        return []

    posts = []
    for post in posts_for_date(run_date=run_date, date_payload=date_payload):
        post_id = str(post.get("post_id") or "")
        if not post_id:
            continue
        html_key = str(post.get("html_key") or _html_key_for_post_id(post_id))
        html_url = public_url(html_key)
        transient_text = text_preview_for_post(post=post, html_url=html_url)
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
    return posts


def posts_for_date(*, run_date: str, date_payload: dict[str, Any]) -> list[dict[str, Any]]:
    inline_posts = date_payload.get("posts")
    if isinstance(inline_posts, list):
        return inline_posts

    index_key = str(date_payload.get("index_key") or "")
    if not index_key:
        return []

    date_index = fetch_date_index(index_key=index_key)
    if str(date_index.get("date") or run_date) != run_date:
        return []
    posts = date_index.get("posts") or []
    return posts if isinstance(posts, list) else []


def text_preview_for_post(*, post: dict[str, Any], html_url: str) -> str:
    text_preview = post.get("text_preview")
    if text_preview is None:
        text_preview = post.get("excerpt")
    if text_preview is not None:
        return _first_words(str(text_preview), settings.LESSWRONG_EXCERPT_WORDS)

    plaintext = _extract_plaintext(fetch_public_post_html(html_url=html_url) or "")
    return _first_words(plaintext, settings.LESSWRONG_EXCERPT_WORDS)


def fetch_public_post_html(*, html_url: str | None = None, html_key: str | None = None) -> str | None:
    url = html_url or (public_url(html_key) if html_key else None)
    if not url:
        return None
    try:
        with httpx.Client(timeout=30.0, follow_redirects=True) as client:
            response = client.get(url)
            response.raise_for_status()
    except httpx.HTTPError:
        return None
    return response.text


def fetch_index() -> dict[str, Any]:
    global _index_cache, _index_cached_at

    if not settings.LESSWRONG_HTML_PUBLIC_BASE_URL:
        return {"dates": {}}

    now = time.monotonic()
    with _index_lock:
        if (
            _index_cache is not None
            and now - _index_cached_at < settings.LESSWRONG_PUBLIC_INDEX_TTL_SECONDS
        ):
            return _index_cache

    with httpx.Client(timeout=30.0, follow_redirects=True) as client:
        response = client.get(public_url(settings.LESSWRONG_HTML_INDEX_PATH))
        response.raise_for_status()
        payload = response.json()

    with _index_lock:
        _index_cache = payload
        _index_cached_at = now
    return payload


def fetch_date_index(*, index_key: str) -> dict[str, Any]:
    now = time.monotonic()
    with _index_lock:
        cached = _date_index_cache.get(index_key)
        cached_at = _date_index_cached_at.get(index_key, 0.0)
        if cached is not None and now - cached_at < settings.LESSWRONG_PUBLIC_INDEX_TTL_SECONDS:
            return cached

    with httpx.Client(timeout=30.0, follow_redirects=True) as client:
        response = client.get(public_url(index_key))
        response.raise_for_status()
        payload = response.json()

    with _index_lock:
        _date_index_cache[index_key] = payload
        _date_index_cached_at[index_key] = now
    return payload


def public_url(path_or_key: str) -> str:
    base = settings.LESSWRONG_HTML_PUBLIC_BASE_URL.rstrip("/") + "/"
    path = path_or_key.lstrip("/")
    return urljoin(base, quote(path, safe="/:.-_"))


def _extract_plaintext(html: str) -> str:
    if not html:
        return ""
    soup = BeautifulSoup(html, "lxml")
    for element in soup(["script", "style", "noscript"]):
        element.decompose()
    selectors = [
        ".PostsPage-postContent",
        ".post-body",
        ".post-content",
        "article",
        "main",
    ]
    body = next((soup.select_one(selector) for selector in selectors if soup.select_one(selector)), None)
    return " ".join((body or soup).get_text(" ", strip=True).split())


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
