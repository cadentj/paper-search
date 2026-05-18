"""Public R2-backed arXiv candidate provider."""

from __future__ import annotations

import threading
import time
from concurrent.futures import ThreadPoolExecutor, as_completed
from dataclasses import dataclass
from datetime import datetime
from typing import Any
from urllib.parse import quote, urljoin

import httpx
from bs4 import BeautifulSoup

from app.core.config import settings


@dataclass(frozen=True)
class AvailableDate:
    date: str
    count: int


_index_cache: dict[str, Any] | None = None
_index_cached_at = 0.0
_index_lock = threading.Lock()


def available_dates() -> dict[str, Any]:
    index = fetch_index()
    dates = [
        AvailableDate(date=day, count=int(payload.get("count") or 0))
        for day, payload in index.get("dates", {}).items()
    ]
    dates.sort(key=lambda item: item.date, reverse=True)
    return {
        "default_date": dates[0].date if dates else None,
        "dates": [{"date": item.date, "count": item.count} for item in dates],
    }


def fetch_public_cached_papers(
    *,
    run_date: str,
    categories: list[str] | None = None,
    limit: int | None = None,
) -> list[dict[str, Any]]:
    index = fetch_index()
    date_payload = index.get("dates", {}).get(run_date)
    if not date_payload:
        return []

    category_set = set(categories or _settings_categories())
    papers = [
        paper for paper in date_payload.get("papers", [])
        if _matches_categories(paper, category_set)
    ]
    max_results = limit if limit is not None else settings.ARXIV_PUBLIC_DAILY_LIMIT
    if max_results and max_results > 0:
        papers = papers[:max_results]

    return _hydrate_paper_records(papers)


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

    try:
        with httpx.Client(timeout=30.0, follow_redirects=True) as client:
            response = client.get(url)
            response.raise_for_status()
    except httpx.HTTPError:
        return None

    return {"html": response.text, "source_url": str(response.url)}


def fetch_index() -> dict[str, Any]:
    global _index_cache, _index_cached_at

    now = time.monotonic()
    with _index_lock:
        if (
            _index_cache is not None
            and now - _index_cached_at < settings.ARXIV_PUBLIC_INDEX_TTL_SECONDS
        ):
            return _index_cache

    index_url = public_url(settings.ARXIV_HTML_INDEX_PATH)
    with httpx.Client(timeout=30.0, follow_redirects=True) as client:
        response = client.get(index_url)
        response.raise_for_status()
        payload = response.json()

    with _index_lock:
        _index_cache = payload
        _index_cached_at = now
    return payload


def public_url(path_or_key: str) -> str:
    base = settings.ARXIV_HTML_PUBLIC_BASE_URL.rstrip("/") + "/"
    path = path_or_key.lstrip("/")
    return urljoin(base, quote(path, safe="/:.-_"))


def _hydrate_paper_records(index_papers: list[dict[str, Any]]) -> list[dict[str, Any]]:
    records: list[dict[str, Any] | None] = [None] * len(index_papers)
    with ThreadPoolExecutor(max_workers=16) as executor:
        futures = {
            executor.submit(_paper_record, paper): index
            for index, paper in enumerate(index_papers)
        }
        for future in as_completed(futures):
            records[futures[future]] = future.result()
    return [record for record in records if record]


def _paper_record(paper: dict[str, Any]) -> dict[str, Any]:
    arxiv_id = str(paper.get("arxiv_id") or "")
    html_key = str(paper.get("html_key") or _html_key_for_arxiv_id(arxiv_id))
    html_url = public_url(html_key)
    metadata = {
        "title": paper.get("title") or arxiv_id,
        "abstract": paper.get("abstract") or "",
        "authors": paper.get("authors") or [],
    }

    if not metadata["abstract"] or not metadata["authors"]:
        fetched = fetch_public_paper_html(arxiv_id=arxiv_id, html_url=html_url)
        if fetched:
            extracted = _extract_html_metadata(fetched["html"])
            metadata = {
                "title": metadata["title"] or extracted["title"] or arxiv_id,
                "abstract": metadata["abstract"] or extracted["abstract"],
                "authors": metadata["authors"] or extracted["authors"],
            }

    return {
        "arxiv_id": arxiv_id,
        "title": metadata["title"] or arxiv_id,
        "abstract": metadata["abstract"] or "No abstract was available in the R2 index or HTML.",
        "authors": metadata["authors"],
        "categories": list(paper.get("categories") or []),
        "published_at": _parse_datetime(paper.get("latest_version_date")),
        "html_url": html_url,
        "landing_url": f"https://arxiv.org/abs/{arxiv_id}",
    }


def _extract_html_metadata(html: str) -> dict[str, Any]:
    soup = BeautifulSoup(html, "lxml")
    title_el = soup.select_one(".ltx_title_document") or soup.find("title")
    authors = [
        _normalize_text(author.get_text(" ", strip=True))
        for author in soup.select(".ltx_authors .ltx_personname")
    ]
    abstract_el = soup.select_one(".ltx_abstract")
    if abstract_el:
        for heading in abstract_el.select(".ltx_title_abstract"):
            heading.decompose()
        abstract = _normalize_text(abstract_el.get_text(" ", strip=True))
    else:
        abstract = ""

    return {
        "title": _normalize_text(title_el.get_text(" ", strip=True)) if title_el else "",
        "abstract": abstract,
        "authors": [author for author in authors if author],
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


def _normalize_text(value: str) -> str:
    return " ".join(value.split())
