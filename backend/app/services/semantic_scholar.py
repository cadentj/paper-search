"""Semantic Scholar API client."""

import logging
import re

import httpx

logger = logging.getLogger(__name__)

S2_API_BASE = "https://api.semanticscholar.org/graph/v1"
AUTHOR_FIELDS = "name,affiliations,paperCount,hIndex"
PAPER_FIELDS = "title,abstract,year,fieldsOfStudy,authors"
MAX_PUBLICATIONS = 100


def extract_author_id(url: str) -> str | None:
    match = re.search(r"/author/[^/]+/(\d+)", url)
    return match.group(1) if match else None


def get_author(author_id: str) -> dict | None:
    url = f"{S2_API_BASE}/author/{author_id}"
    try:
        resp = httpx.get(url, params={"fields": AUTHOR_FIELDS}, timeout=15)
        resp.raise_for_status()
        return resp.json()
    except Exception:
        logger.exception("Failed to fetch S2 author %s", author_id)
        return None


def get_author_papers(author_id: str, limit: int = MAX_PUBLICATIONS) -> list[dict]:
    url = f"{S2_API_BASE}/author/{author_id}/papers"
    papers: list[dict] = []
    offset = 0
    per_page = min(limit, 100)

    while len(papers) < limit:
        try:
            resp = httpx.get(
                url,
                params={"fields": PAPER_FIELDS, "offset": offset, "limit": per_page},
                timeout=15,
            )
            resp.raise_for_status()
            data = resp.json()
        except Exception:
            logger.exception(
                "Failed to fetch S2 author papers %s offset=%d", author_id, offset
            )
            break

        batch = data.get("data", [])
        if not batch:
            break
        papers.extend(batch)
        offset += len(batch)

        if data.get("next") is None:
            break

    return papers[:limit]


def build_publications_text(papers: list[dict], max_papers: int = 50) -> str:
    lines = []
    for p in papers[:max_papers]:
        title = p.get("title", "Unknown")
        year = p.get("year", "")
        abstract = p.get("abstract") or "(no abstract)"
        authors = ", ".join(a.get("name", "") for a in (p.get("authors") or [])[:5])
        fields = ", ".join(p.get("fieldsOfStudy") or [])
        lines.append(
            f"Title: {title}\n"
            f"Year: {year}\n"
            f"Authors: {authors}\n"
            f"Fields: {fields}\n"
            f"Abstract: {abstract[:500]}\n"
        )
    return "\n---\n".join(lines)
