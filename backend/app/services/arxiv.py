"""arXiv API paper provider for daily searches."""

from __future__ import annotations

import re
import xml.etree.ElementTree as ET
from datetime import datetime
from typing import Any

import httpx

from app.core.config import settings

ARXIV_API_URL = "https://export.arxiv.org/api/query"
ATOM_NS = "{http://www.w3.org/2005/Atom}"
ARXIV_NS = "{http://arxiv.org/schemas/atom}"
VERSION_RE = re.compile(r"v\d+$")


def normalize_arxiv_id(value: str) -> str:
    """Return a bare arXiv ID without URL prefix or version suffix."""
    arxiv_id = value.rstrip("/").rsplit("/", 1)[-1]
    return VERSION_RE.sub("", arxiv_id)


def build_category_query(categories: list[str]) -> str:
    return " OR ".join(f"cat:{category}" for category in categories)


def parse_arxiv_datetime(value: str | None) -> datetime | None:
    if not value:
        return None
    return datetime.fromisoformat(value.replace("Z", "+00:00"))


def parse_arxiv_feed(xml_text: str) -> list[dict[str, Any]]:
    root = ET.fromstring(xml_text)
    papers: list[dict[str, Any]] = []

    for entry in root.findall(f"{ATOM_NS}entry"):
        id_el = entry.find(f"{ATOM_NS}id")
        title_el = entry.find(f"{ATOM_NS}title")
        summary_el = entry.find(f"{ATOM_NS}summary")
        published_el = entry.find(f"{ATOM_NS}published")

        if id_el is None or not id_el.text:
            continue

        arxiv_id = normalize_arxiv_id(id_el.text)
        authors = [
            name_el.text.strip()
            for author_el in entry.findall(f"{ATOM_NS}author")
            for name_el in [author_el.find(f"{ATOM_NS}name")]
            if name_el is not None and name_el.text
        ]
        categories = [
            category_el.attrib["term"]
            for category_el in entry.findall(f"{ATOM_NS}category")
            if category_el.attrib.get("term")
        ]

        primary_category_el = entry.find(f"{ARXIV_NS}primary_category")
        primary_category = (
            primary_category_el.attrib.get("term")
            if primary_category_el is not None
            else None
        )
        if primary_category and primary_category not in categories:
            categories.insert(0, primary_category)

        papers.append(
            {
                "arxiv_id": arxiv_id,
                "title": " ".join((title_el.text or "").split()) if title_el is not None else "",
                "abstract": " ".join((summary_el.text or "").split()) if summary_el is not None else "",
                "authors": authors,
                "categories": categories,
                "published_at": parse_arxiv_datetime(
                    published_el.text if published_el is not None else None
                ),
                "html_url": f"https://arxiv.org/html/{arxiv_id}",
                "landing_url": f"https://arxiv.org/abs/{arxiv_id}",
            }
        )

    return papers


def fetch_daily_papers(
    *,
    limit: int | None = None,
    categories: list[str] | None = None,
) -> list[dict[str, Any]]:
    category_list = categories or [
        category.strip()
        for category in settings.ARXIV_CATEGORIES.split(",")
        if category.strip()
    ]
    max_results = limit or settings.ARXIV_DAILY_LIMIT

    params = {
        "search_query": build_category_query(category_list),
        "start": 0,
        "max_results": max_results,
        "sortBy": "submittedDate",
        "sortOrder": "descending",
    }

    with httpx.Client(timeout=30.0, follow_redirects=True) as client:
        response = client.get(ARXIV_API_URL, params=params)
        response.raise_for_status()

    return parse_arxiv_feed(response.text)
