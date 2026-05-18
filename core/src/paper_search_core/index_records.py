"""Map R2 shard items to paper records for index sync."""

from __future__ import annotations

import re
from dataclasses import dataclass
from datetime import datetime
from typing import Any

from paper_search_core.r2_urls import has_searchable_text, public_url_for_base

VERSION_RE = re.compile(r"v\d+$")

ARXIV_SEARCHABLE_FIELDS = ("abstract",)
LESSWRONG_SEARCHABLE_FIELDS = ("text_preview", "excerpt")


@dataclass(frozen=True)
class IndexSettings:
    arxiv_html_public_base_url: str
    lesswrong_html_public_base_url: str
    arxiv_categories: str = "cs.AI,cs.CL,cs.LG"
    lesswrong_excerpt_words: int = 250


def normalize_arxiv_id(value: str) -> str:
    arxiv_id = value.rstrip("/").rsplit("/", 1)[-1]
    return VERSION_RE.sub("", arxiv_id)


def arxiv_html_key_for_id(arxiv_id: str) -> str:
    return f"data/{arxiv_id[:4]}/{arxiv_id}.html"


def lesswrong_html_key_for_post_id(post_id: str) -> str:
    return f"data/{post_id[:2]}/{post_id}.html"


def arxiv_is_searchable(paper: dict[str, Any]) -> bool:
    return has_searchable_text(paper, text_fields=ARXIV_SEARCHABLE_FIELDS)


def lesswrong_is_searchable(post: dict[str, Any]) -> bool:
    return has_searchable_text(post, text_fields=LESSWRONG_SEARCHABLE_FIELDS)


def arxiv_search_text(paper: dict[str, Any]) -> str:
    return str(paper.get("abstract") or "").strip()


def lesswrong_search_text(post: dict[str, Any], settings: IndexSettings) -> str:
    raw = post.get("text_preview")
    if raw is None:
        raw = post.get("excerpt")
    if raw is None:
        return ""
    return _first_words(str(raw), settings.lesswrong_excerpt_words)


def arxiv_record_from_shard(
    paper: dict[str, Any], settings: IndexSettings
) -> dict[str, Any]:
    arxiv_id = str(paper.get("arxiv_id") or "")
    html_key = str(paper.get("html_key") or arxiv_html_key_for_id(arxiv_id))
    abstract = arxiv_search_text(paper)
    return {
        "source_type": "arxiv",
        "source_id": arxiv_id,
        "title": paper.get("title") or arxiv_id,
        "abstract": abstract,
        "search_text": abstract,
        "authors": list(paper.get("authors") or []),
        "categories": list(paper.get("categories") or []),
        "published_at": _parse_datetime(paper.get("latest_version_date")),
        "html_url": public_url_for_base(settings.arxiv_html_public_base_url, html_key),
        "source_url": f"https://arxiv.org/abs/{arxiv_id}",
    }


def lesswrong_record_from_shard(
    post: dict[str, Any], settings: IndexSettings
) -> dict[str, Any]:
    post_id = str(post.get("post_id") or "")
    html_key = str(post.get("html_key") or lesswrong_html_key_for_post_id(post_id))
    search_text = lesswrong_search_text(post, settings)
    return {
        "source_type": "lesswrong",
        "source_id": post_id,
        "title": post.get("title") or "Untitled LessWrong post",
        "abstract": search_text,
        "search_text": search_text,
        "authors": [author for author in [post.get("author")] if author],
        "categories": [],
        "published_at": _parse_datetime(post.get("posted_at")),
        "html_url": public_url_for_base(
            settings.lesswrong_html_public_base_url, html_key
        ),
        "source_url": post.get("page_url"),
    }


def arxiv_matches_categories(paper: dict[str, Any], category_set: set[str]) -> bool:
    if not category_set:
        return True
    return bool(category_set.intersection(set(paper.get("categories") or [])))


def arxiv_categories(settings: IndexSettings) -> list[str]:
    return [
        category.strip()
        for category in settings.arxiv_categories.split(",")
        if category.strip()
    ]


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
