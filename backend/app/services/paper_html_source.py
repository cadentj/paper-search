"""Resolve locally scraped arXiv HTML files."""

from __future__ import annotations

import re
import sqlite3
from dataclasses import dataclass
from pathlib import Path

from app.core.config import REPO_ROOT, settings


VERSION_RE = re.compile(r"v\d+$")
SAFE_ARXIV_ID_RE = re.compile(r"^[A-Za-z0-9_.-]+$")


@dataclass(frozen=True)
class LocalHtmlDocument:
    arxiv_id: str
    source_url: str
    path: Path
    html: str


def arxiv_html_url(arxiv_id: str) -> str:
    return f"https://arxiv.org/html/{normalize_arxiv_id(arxiv_id)}"


def read_local_paper_html(arxiv_id: str | None) -> LocalHtmlDocument | None:
    if not arxiv_id:
        return None

    normalized_id = normalize_arxiv_id(arxiv_id)
    path = resolve_local_html_path(normalized_id)
    if not path or not path.exists() or not path.is_file():
        return None

    return LocalHtmlDocument(
        arxiv_id=normalized_id,
        source_url=arxiv_html_url(normalized_id),
        path=path,
        html=path.read_text(encoding="utf-8"),
    )


def local_html_path(arxiv_id: str) -> Path | None:
    normalized_id = normalize_arxiv_id(arxiv_id)
    if not SAFE_ARXIV_ID_RE.fullmatch(normalized_id):
        return None
    if not _is_new_style_arxiv_id(normalized_id):
        return None

    cache_dir = _cache_dir()
    return cache_dir / normalized_id[:4] / f"{normalized_id}.html"


def resolve_local_html_path(
    arxiv_id: str,
    recorded_path: str | None = None,
) -> Path | None:
    normalized_id = normalize_arxiv_id(arxiv_id)
    candidates: list[Path | None] = []
    if recorded_path:
        candidates.extend(_path_variants(Path(recorded_path).expanduser()))

    state_path = _state_html_path(normalized_id)
    if state_path:
        candidates.extend(_path_variants(state_path))

    candidates.append(local_html_path(normalized_id))
    candidates.append(_cache_root() / "data" / normalized_id[:4] / f"{normalized_id}.html")

    for candidate in candidates:
        if candidate and candidate.exists() and candidate.is_file():
            return candidate
    return None


def normalize_arxiv_id(value: str) -> str:
    arxiv_id = value.rstrip("/").rsplit("/", 1)[-1]
    return VERSION_RE.sub("", arxiv_id)


def _cache_dir() -> Path:
    path = Path(settings.ARXIV_HTML_CACHE_DIR).expanduser()
    if path.is_absolute():
        return path
    return (REPO_ROOT / path).resolve()


def _cache_root() -> Path:
    cache_dir = _cache_dir()
    if cache_dir.name in {"html", "data"}:
        return cache_dir.parent
    return cache_dir


def _state_db_path() -> Path:
    path = Path(settings.ARXIV_HTML_STATE_DB).expanduser()
    if path.is_absolute():
        return path
    return (REPO_ROOT / path).resolve()


def _state_html_path(arxiv_id: str) -> Path | None:
    db_path = _state_db_path()
    if not db_path.exists():
        return None

    try:
        with sqlite3.connect(db_path) as conn:
            row = conn.execute(
                """
                SELECT html_path
                FROM arxiv_html_scrape
                WHERE arxiv_id = ? AND status = 'success'
                """,
                (arxiv_id,),
            ).fetchone()
    except sqlite3.Error:
        return None

    if not row or not row[0]:
        return None
    return Path(row[0]).expanduser()


def _path_variants(path: Path) -> list[Path]:
    variants = [path if path.is_absolute() else (REPO_ROOT / path).resolve()]
    text = str(variants[0])
    for old, new in (("/html/", "/data/"), ("/data/", "/html/")):
        if old in text:
            variants.append(Path(text.replace(old, new, 1)))
    return variants


def _is_new_style_arxiv_id(arxiv_id: str) -> bool:
    return len(arxiv_id) >= 6 and arxiv_id[:4].isdigit() and "." in arxiv_id
