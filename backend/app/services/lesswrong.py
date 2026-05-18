from __future__ import annotations

from collections import Counter
from datetime import date, datetime
from typing import Any

import httpx

from app.core.config import settings


POSTS_QUERY = """
query LessWrongPosts($after: String!, $before: String!, $limit: Int!) {
  posts(input: { terms: { view: "new", after: $after, before: $before, limit: $limit } }) {
    results {
      _id
      title
      slug
      pageUrl
      postedAt
      baseScore
      user {
        displayName
        username
      }
      contents {
        plaintextMainText
      }
    }
  }
}
"""

POST_COUNTS_QUERY = """
query LessWrongPostCounts($after: String!, $before: String!, $limit: Int!) {
  posts(input: { terms: { view: "new", after: $after, before: $before, limit: $limit } }) {
    results {
      _id
      postedAt
    }
  }
}
"""

POST_HTML_QUERY = """
query LessWrongPostHtml($postId: String!) {
  post(input: { selector: { _id: $postId } }) {
    result {
      _id
      pageUrl
      contents {
        html
      }
    }
  }
}
"""


def fetch_lesswrong_posts_for_date(run_date: date) -> list[dict[str, Any]]:
    payload = _graphql(
        POSTS_QUERY,
        {
            "after": run_date.isoformat(),
            "before": _next_day(run_date).isoformat(),
            "limit": settings.LESSWRONG_DAILY_LIMIT,
        },
    )
    posts = ((payload.get("data") or {}).get("posts") or {}).get("results") or []
    return [_normalize_post(post) for post in posts if post.get("_id")]


def count_lesswrong_posts_by_date(start_date: date, end_date: date) -> dict[str, int]:
    payload = _graphql(
        POST_COUNTS_QUERY,
        {
            "after": start_date.isoformat(),
            "before": _next_day(end_date).isoformat(),
            "limit": settings.LESSWRONG_COUNT_LIMIT,
        },
    )
    posts = ((payload.get("data") or {}).get("posts") or {}).get("results") or []
    counts: Counter[str] = Counter()
    for post in posts:
        posted_at = _parse_datetime(post.get("postedAt"))
        if posted_at:
            counts[posted_at.date().isoformat()] += 1
    return dict(counts)


def fetch_lesswrong_post_html(post_id: str) -> dict[str, str] | None:
    payload = _graphql(POST_HTML_QUERY, {"postId": post_id})
    post = ((payload.get("data") or {}).get("post") or {}).get("result") or {}
    html = ((post.get("contents") or {}).get("html") or "").strip()
    if not html:
        return None
    return {
        "html": html,
        "source_url": post.get("pageUrl") or f"https://www.lesswrong.com/posts/{post_id}",
    }


def _normalize_post(post: dict[str, Any]) -> dict[str, Any]:
    post_id = str(post.get("_id") or "")
    user = post.get("user") or {}
    plaintext = ((post.get("contents") or {}).get("plaintextMainText") or "").strip()
    excerpt = _first_words(plaintext, settings.LESSWRONG_EXCERPT_WORDS)
    page_url = post.get("pageUrl") or f"https://www.lesswrong.com/posts/{post_id}/{post.get('slug') or ''}".rstrip("/")

    return {
        "source_type": "lesswrong",
        "source_id": post_id,
        "title": post.get("title") or "Untitled LessWrong post",
        "abstract": "",
        "transient_text": excerpt,
        "authors": [
            value
            for value in [user.get("displayName") or user.get("username")]
            if value
        ],
        "categories": [],
        "published_at": _parse_datetime(post.get("postedAt")),
        "html_url": None,
        "landing_url": page_url,
        "source_url": page_url,
        "source_metadata": {
            "slug": post.get("slug"),
            "baseScore": post.get("baseScore"),
        },
    }


def _graphql(query: str, variables: dict[str, Any]) -> dict[str, Any]:
    headers = {
        "User-Agent": settings.LESSWRONG_USER_AGENT,
        "Content-Type": "application/json",
    }
    with httpx.Client(timeout=30.0, follow_redirects=True, headers=headers) as client:
        response = client.post(
            settings.LESSWRONG_GRAPHQL_URL,
            json={"query": query, "variables": variables},
        )
        response.raise_for_status()
        payload = response.json()
    if payload.get("errors"):
        raise RuntimeError(f"LessWrong GraphQL error: {payload['errors']}")
    return payload


def _parse_datetime(value: str | None) -> datetime | None:
    if not value:
        return None
    try:
        return datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError:
        return None


def _first_words(value: str, count: int) -> str:
    words = value.split()
    if len(words) <= count:
        return " ".join(words)
    return " ".join(words[:count])


def _next_day(value: date) -> date:
    from datetime import timedelta

    return value + timedelta(days=1)
