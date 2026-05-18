"""arXiv source — public R2 index access and provider."""

from __future__ import annotations

import logging
import re
from dataclasses import dataclass
from datetime import date, datetime
from typing import Any

from app.core.config import settings
from app.models.paper import Paper
from app.services.html_parser import prepare_arxiv_html_for_viewer
from app.services.public_r2_index import (
    ShardedPublicIndexReader,
    has_searchable_text,
    http_get_text,
    public_url_for_base,
)
from app.services.source_types import SourceFetchResult, candidate_from_record

logger = logging.getLogger(__name__)

VERSION_RE = re.compile(r"v\d+$")

_ARXIV_READER = ShardedPublicIndexReader(
    public_base_url=settings.ARXIV_HTML_PUBLIC_BASE_URL,
    manifest_path=settings.ARXIV_HTML_INDEX_PATH,
    ttl_seconds=settings.ARXIV_PUBLIC_INDEX_TTL_SECONDS,
    items_key="papers",
    namespace="arxiv",
)


@dataclass(frozen=True)
class PaperHtmlDocument:
    arxiv_id: str
    source_url: str
    html: str


def fetch_public_cached_papers(
    *,
    run_date: str,
    categories: list[str] | None = None,
    limit: int | None = None,
) -> tuple[list[dict[str, Any]], int]:
    index = fetch_index()
    date_payload = index.get("dates", {}).get(run_date)
    if not date_payload:
        return [], 0

    category_set = set(categories or _settings_categories())
    raw_papers = papers_for_date(run_date=run_date, date_payload=date_payload)
    skipped_missing_text = 0
    papers: list[dict[str, Any]] = []
    for paper in raw_papers:
        if not has_searchable_text(paper, text_fields=("abstract",)):
            skipped_missing_text += 1
            continue
        if not _matches_categories(paper, category_set):
            continue
        papers.append(paper)

    max_results = limit if limit is not None else settings.ARXIV_PUBLIC_DAILY_LIMIT
    if max_results and max_results > 0:
        papers = papers[:max_results]

    records = [_paper_record(p) for p in papers]
    return records, skipped_missing_text


def papers_for_date(*, run_date: str, date_payload: dict[str, Any]) -> list[dict[str, Any]]:
    return _ARXIV_READER.items_for_date(run_date=run_date, date_payload=date_payload)


def fetch_public_paper_html(
    *,
    arxiv_id: str | None = None,
    html_url: str | None = None,
) -> dict[str, str] | None:
    url = html_url
    if not url and arxiv_id:
        html_key = _html_key_for_arxiv_id(arxiv_id)
        url = public_url(html_key)
    if not url:
        return None

    text = http_get_text(url)
    if text is None:
        return None
    return {"html": text, "source_url": url}


def fetch_index() -> dict[str, Any]:
    return _ARXIV_READER.fetch_manifest()


def public_url(path_or_key: str) -> str:
    return public_url_for_base(settings.ARXIV_HTML_PUBLIC_BASE_URL, path_or_key)


def arxiv_html_url(arxiv_id: str) -> str:
    return f"https://arxiv.org/html/{normalize_arxiv_id(arxiv_id)}"


def read_paper_html(
    arxiv_id: str | None,
    *,
    html_url: str | None = None,
) -> PaperHtmlDocument | None:
    remote_html = fetch_public_paper_html(arxiv_id=arxiv_id, html_url=html_url)
    if not remote_html:
        return None

    return PaperHtmlDocument(
        arxiv_id=normalize_arxiv_id(arxiv_id or ""),
        source_url=remote_html["source_url"],
        html=remote_html["html"],
    )


def normalize_arxiv_id(value: str) -> str:
    arxiv_id = value.rstrip("/").rsplit("/", 1)[-1]
    return VERSION_RE.sub("", arxiv_id)


class ArxivProvider:
    source_type = "arxiv"

    def count_for_date(self, run_date: date) -> int:
        try:
            index = fetch_index()
        except Exception:
            logger.exception("failed to fetch arXiv index count for %s", run_date)
            return 0
        payload = (index.get("dates") or {}).get(run_date.isoformat())
        return int((payload or {}).get("count") or 0)

    def candidates_for_date(self, run_date: date) -> SourceFetchResult:
        try:
            records, skipped = fetch_public_cached_papers(run_date=run_date.isoformat())
        except Exception as exc:
            logger.exception("failed to fetch cached arXiv papers for %s", run_date)
            return SourceFetchResult(items=[], errors=[f"arXiv fetch failed: {exc}"])
        skipped_map = {"arxiv": skipped} if skipped else {}
        return SourceFetchResult(
            items=[candidate_from_record(record) for record in records],
            skipped_missing_text=skipped_map,
        )

    def html_for_paper(self, paper: Paper) -> dict[str, str | None]:
        paper_html = read_paper_html(paper.arxiv_id, html_url=paper.html_url)
        if paper_html:
            return {
                "html": prepare_arxiv_html_for_viewer(
                    paper_html.html,
                    paper_html.source_url,
                ),
                "source_url": paper_html.source_url,
            }
        return {
            "html": None,
            "source_url": arxiv_html_url(paper.arxiv_id) if paper.arxiv_id else None,
        }


def _paper_record(paper: dict[str, Any]) -> dict[str, Any]:
    arxiv_id = str(paper.get("arxiv_id") or "")
    html_key = str(paper.get("html_key") or _html_key_for_arxiv_id(arxiv_id))
    html_url = public_url(html_key)
    abstract = str(paper.get("abstract") or "").strip()
    return {
        "source_type": "arxiv",
        "source_id": arxiv_id,
        "arxiv_id": arxiv_id,
        "title": paper.get("title") or arxiv_id,
        "abstract": abstract,
        "authors": list(paper.get("authors") or []),
        "categories": list(paper.get("categories") or []),
        "published_at": _parse_datetime(paper.get("latest_version_date")),
        "html_url": html_url,
        "landing_url": f"https://arxiv.org/abs/{arxiv_id}",
        "source_url": f"https://arxiv.org/abs/{arxiv_id}",
        "source_metadata": {},
    }


def _matches_categories(paper: dict[str, Any], category_set: set[str]) -> bool:
    if not category_set:
        return True
    return bool(category_set.intersection(set(paper.get("categories") or [])))


def _settings_categories() -> list[str]:
    return [
        category.strip()
        for category in settings.ARXIV_CATEGORIES.split(",")
        if category.strip()
    ]


def _html_key_for_arxiv_id(arxiv_id: str) -> str:
    return f"data/{arxiv_id[:4]}/{arxiv_id}.html"


def _parse_datetime(value: str | None) -> datetime | None:
    if not value:
        return None
    try:
        return datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError:
        return None
