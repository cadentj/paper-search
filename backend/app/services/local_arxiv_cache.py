"""Local arXiv candidate provider backed by the HTML scraper cache."""

from __future__ import annotations

import json
import random
import sqlite3
from datetime import datetime
from pathlib import Path
from typing import Any

from bs4 import BeautifulSoup

from app.core.config import REPO_ROOT, settings
from app.services.paper_html_source import arxiv_html_url, resolve_local_html_path


def fetch_local_cached_papers(
    *,
    limit: int | None = None,
    categories: list[str] | None = None,
) -> list[dict[str, Any]]:
    max_results = limit or settings.ARXIV_DAILY_LIMIT
    rows = _load_success_rows()
    category_set = set(categories or _settings_categories())

    candidates = []
    for row in rows:
        row_categories = _parse_categories(row["categories"])
        if category_set and not category_set.intersection(row_categories):
            continue
        html_path = resolve_local_html_path(row["arxiv_id"], row["html_path"])
        if not html_path:
            continue
        candidates.append((row, row_categories, html_path))

    if not candidates:
        return []

    latest_day = max(
        (_date_part(row["latest_version_date"]) for row, _, _ in candidates),
        default="",
    )
    latest_pool = [
        candidate
        for candidate in candidates
        if _date_part(candidate[0]["latest_version_date"]) == latest_day
    ]
    older_pool = [
        candidate
        for candidate in candidates
        if _date_part(candidate[0]["latest_version_date"]) != latest_day
    ]
    random.shuffle(latest_pool)
    random.shuffle(older_pool)
    pool = latest_pool + older_pool

    return [
        _paper_record(row, row_categories, html_path)
        for row, row_categories, html_path in pool[:max_results]
    ]


def _load_success_rows() -> list[sqlite3.Row]:
    db_path = _state_db_path()
    if not db_path.exists():
        return []

    with sqlite3.connect(db_path) as conn:
        conn.row_factory = sqlite3.Row
        return conn.execute(
            """
            SELECT arxiv_id, title, categories, latest_version_date, source_url, html_path
            FROM arxiv_html_scrape
            WHERE status = 'success'
              AND COALESCE(html_path, '') != ''
            ORDER BY latest_version_date DESC
            """
        ).fetchall()


def _paper_record(
    row: sqlite3.Row,
    categories: list[str],
    html_path: Path,
) -> dict[str, Any]:
    html_metadata = _extract_html_metadata(html_path)
    arxiv_id = row["arxiv_id"]
    title = row["title"] or html_metadata["title"] or arxiv_id
    return {
        "arxiv_id": arxiv_id,
        "title": title,
        "abstract": html_metadata["abstract"],
        "authors": html_metadata["authors"],
        "categories": categories,
        "published_at": _parse_datetime(row["latest_version_date"]),
        "html_url": row["source_url"] or arxiv_html_url(arxiv_id),
        "landing_url": f"https://arxiv.org/abs/{arxiv_id}",
    }


def _extract_html_metadata(path: Path) -> dict[str, Any]:
    try:
        soup = BeautifulSoup(path.read_text(encoding="utf-8"), "lxml")
    except OSError:
        return {"title": "", "abstract": "", "authors": []}

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
        "abstract": abstract or "Local HTML cached paper. Abstract metadata was not available locally.",
        "authors": [author for author in authors if author],
    }


def _settings_categories() -> list[str]:
    return [
        category.strip()
        for category in settings.ARXIV_CATEGORIES.split(",")
        if category.strip()
    ]


def _parse_categories(value: str | None) -> list[str]:
    if not value:
        return []
    try:
        parsed = json.loads(value)
    except json.JSONDecodeError:
        return value.split()
    return [str(category) for category in parsed]


def _parse_datetime(value: str | None) -> datetime | None:
    if not value:
        return None
    try:
        return datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError:
        return None


def _date_part(value: str | None) -> str:
    parsed = _parse_datetime(value)
    return parsed.date().isoformat() if parsed else ""


def _state_db_path() -> Path:
    path = Path(settings.ARXIV_HTML_STATE_DB).expanduser()
    if path.is_absolute():
        return path
    return (REPO_ROOT / path).resolve()


def _normalize_text(value: str) -> str:
    return " ".join(value.split())
