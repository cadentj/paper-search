#!/usr/bin/env python3
"""Scrape arXiv HTML, upload to R2, and publish the date index."""

from __future__ import annotations

import argparse
import json
import logging
import re
import sqlite3
import sys
import time
import xml.etree.ElementTree as ET
from dataclasses import dataclass
from datetime import date, datetime, timezone
from pathlib import Path
from typing import Any, Iterable

import httpx
from bs4 import BeautifulSoup
from tqdm import tqdm

from paper_search_core.daily_dates import DAILY_SEARCH_END
from paper_search_core.index_records import normalize_arxiv_id

_SCRIPTS_DIR = Path(__file__).resolve().parent
if str(_SCRIPTS_DIR) not in sys.path:
    sys.path.insert(0, str(_SCRIPTS_DIR))

from r2 import (  # noqa: E402
    Settings,
    date_index_key,
    normalize_prefix,
    r2_client,
    upload_html,
    upload_sharded_index,
)

logging.basicConfig(level=logging.INFO, format="%(levelname)s %(message)s")
logger = logging.getLogger(__name__)

STEPS = ("scrape", "upload-html", "publish-index")
ARXIV_API_URL = "https://export.arxiv.org/api/query"
ATOM_NS = "{http://www.w3.org/2005/Atom}"
ARXIV_NS = "{http://arxiv.org/schemas/atom}"
VERSION_RE = re.compile(r"v\d+$")
SAFE_ID_RE = re.compile(r"[^A-Za-z0-9_.-]+")
SCHEMA_VERSION = 3


@dataclass(frozen=True)
class Candidate:
    arxiv_id: str
    version: str
    title: str
    categories: list[str]
    latest_version_date: str

    @property
    def html_url(self) -> str:
        return f"https://arxiv.org/html/{self.arxiv_id}"


def main() -> None:
    args = parse_args()
    settings = Settings()
    start_date, end_date = parse_date_window(args)
    steps = resolve_steps(args.step)

    logger.info(
        "ingest-arxiv %s..%s steps=%s",
        start_date.isoformat(),
        end_date.isoformat(),
        ",".join(steps),
    )

    if "scrape" in steps:
        run_scrape(settings, start_date, end_date, args)
    if "upload-html" in steps:
        client = r2_client(settings, max_pool_connections=args.workers * 2)
        upload_html(
            client,
            bucket=settings.R2_BUCKET,
            cache_dir=settings.arxiv_html_cache_dir(),
            prefix=settings.ARXIV_HTML_PREFIX,
            workers=args.workers,
            skip_existing=not args.no_skip_existing,
            limit=args.upload_limit,
        )
    if "publish-index" in steps:
        publish_index(settings)


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--end-date", default=DAILY_SEARCH_END.isoformat())
    parser.add_argument("--start-date")
    parser.add_argument("--days", type=int, default=31)
    parser.add_argument("--step", action="append", choices=STEPS)
    parser.add_argument("--steady-rps", type=float, default=2.0)
    parser.add_argument("--timeout", type=float, default=30.0)
    parser.add_argument("--user-agent", default="paper-search/0.1 contact: local-research")
    parser.add_argument("--limit", type=int, default=None)
    parser.add_argument("--workers", type=int, default=16)
    parser.add_argument("--no-skip-existing", action="store_true")
    parser.add_argument("--upload-limit", type=int, default=None)
    return parser.parse_args()


def parse_date_window(args: argparse.Namespace) -> tuple[date, date]:
    from datetime import timedelta

    end_date = date.fromisoformat(args.end_date)
    if args.start_date:
        start_date = date.fromisoformat(args.start_date)
        if start_date > end_date:
            raise SystemExit("--start-date must be on or before --end-date")
        return start_date, end_date
    if args.days < 1:
        raise SystemExit("--days must be at least 1")
    return end_date - timedelta(days=args.days - 1), end_date


def resolve_steps(selected: list[str] | None) -> tuple[str, ...]:
    if not selected:
        return STEPS
    ordered = [step for step in STEPS if step in selected]
    if not ordered:
        raise SystemExit(f"No valid steps. Choose from: {', '.join(STEPS)}")
    return tuple(ordered)


def run_scrape(
    settings: Settings,
    start_date: date,
    end_date: date,
    args: argparse.Namespace,
) -> None:
    output_dir = settings.arxiv_cache_dir()
    output_dir.mkdir(parents=True, exist_ok=True)
    db_path = output_dir / "scrape_state.sqlite"
    categories = settings.arxiv_category_set()

    candidates = load_candidates(categories, start_date, end_date, limit=args.limit)
    print(
        f"Loaded {len(candidates)} candidates for "
        f"{start_date.isoformat()}..{end_date.isoformat()}",
        flush=True,
    )

    with connect_state(db_path) as conn:
        create_state(conn)
        upsert_candidates(conn, candidates)

    headers = {"User-Agent": args.user_agent}
    stats = {"attempted": 0, "success": 0, "missing": 0, "error": 0, "bytes": 0}
    skipped_done = 0

    with tqdm(total=len(candidates), desc="scraping", unit="paper", dynamic_ncols=True) as progress, connect_state(
        db_path
    ) as conn, httpx.Client(timeout=args.timeout, follow_redirects=True, headers=headers) as client:
        create_state(conn)
        for candidate in candidates:
            if already_done(conn, candidate.arxiv_id):
                skipped_done += 1
                progress.update(1)
                continue
            time.sleep(max(0.0, 1.0 / args.steady_rps))
            stats["attempted"] += 1
            result = fetch_one(client, candidate, output_dir)
            stats[result["status"]] += 1
            stats["bytes"] += result.get("bytes", 0)
            record_result(conn, candidate, result)
            progress.update(1)

    print(
        f"done attempted={stats['attempted']} ok={stats['success']} "
        f"missing={stats['missing']} error={stats['error']} skipped={skipped_done}",
        flush=True,
    )


def load_candidates(
    categories: set[str],
    start_date: date,
    end_date: date,
    *,
    limit: int | None,
) -> list[Candidate]:
    query = (
        "(" + " OR ".join(f"cat:{c}" for c in sorted(categories)) + ")"
        f" AND submittedDate:[{start_date:%Y%m%d}0000 TO {end_date:%Y%m%d}2359]"
    )
    candidates: list[Candidate] = []
    start = 0
    page_size = 100
    while True:
        params = {
            "search_query": query,
            "start": start,
            "max_results": page_size,
            "sortBy": "submittedDate",
            "sortOrder": "descending",
        }
        with httpx.Client(timeout=60.0, follow_redirects=True) as client:
            response = client.get(ARXIV_API_URL, params=params)
            response.raise_for_status()
        page = parse_arxiv_feed(response.text)
        if not page:
            break
        candidates.extend(page)
        if len(page) < page_size:
            break
        start += page_size
        time.sleep(3.0)

    deduped = list({c.arxiv_id: c for c in candidates}.values())
    deduped.sort(key=lambda item: (item.latest_version_date, item.arxiv_id))
    return deduped[:limit] if limit is not None else deduped


def parse_arxiv_feed(xml_text: str) -> list[Candidate]:
    root = ET.fromstring(xml_text)
    candidates: list[Candidate] = []
    for entry in root.findall(f"{ATOM_NS}entry"):
        id_el = entry.find(f"{ATOM_NS}id")
        title_el = entry.find(f"{ATOM_NS}title")
        updated_el = entry.find(f"{ATOM_NS}updated")
        if id_el is None or not id_el.text:
            continue
        categories = [
            el.attrib["term"]
            for el in entry.findall(f"{ATOM_NS}category")
            if el.attrib.get("term")
        ]
        primary_el = entry.find(f"{ARXIV_NS}primary_category")
        primary = primary_el.attrib.get("term") if primary_el is not None else None
        if primary and primary not in categories:
            categories.insert(0, primary)
        candidates.append(
            Candidate(
                arxiv_id=normalize_arxiv_id(id_el.text),
                version=_version_from_id(id_el.text),
                title=" ".join((title_el.text or "").split()) if title_el is not None else "",
                categories=categories,
                latest_version_date=updated_el.text if updated_el is not None else "",
            )
        )
    return candidates


def fetch_one(client: httpx.Client, candidate: Candidate, output_dir: Path) -> dict[str, Any]:
    try:
        response = client.get(candidate.html_url)
    except httpx.HTTPError as exc:
        return {"status": "error", "error": str(exc)}

    if response.status_code == 404:
        return {"status": "missing", "status_code": response.status_code}
    if response.status_code != 200:
        return {"status": "error", "status_code": response.status_code}

    html_dir = output_dir / "html" / candidate.arxiv_id[:4]
    html_dir.mkdir(parents=True, exist_ok=True)
    html_path = html_dir / f"{SAFE_ID_RE.sub('_', candidate.arxiv_id)}.html"
    html_path.write_text(response.text, encoding=response.encoding or "utf-8")
    return {
        "status": "success",
        "status_code": response.status_code,
        "bytes": len(response.content),
        "html_path": str(html_path),
        "source_url": str(response.url),
    }


def publish_index(settings: Settings) -> None:
    state_db = settings.arxiv_cache_dir() / "scrape_state.sqlite"
    cache_dir = settings.arxiv_html_cache_dir()
    manifest, date_shards = build_index(
        state_db=state_db,
        cache_dir=cache_dir,
        prefix=settings.ARXIV_HTML_PREFIX,
        date_index_prefix=settings.ARXIV_DATE_INDEX_PREFIX,
    )
    print_summary(manifest)
    client = r2_client(settings)
    upload_sharded_index(
        client,
        bucket=settings.R2_BUCKET,
        index_key=settings.ARXIV_HTML_INDEX_PATH,
        manifest=manifest,
        date_shards=date_shards,
    )


def build_index(
    *,
    state_db: Path,
    cache_dir: Path,
    prefix: str,
    date_index_prefix: str,
) -> tuple[dict[str, Any], dict[str, dict[str, Any]]]:
    if not state_db.exists():
        raise SystemExit(f"State DB not found: {state_db}")
    if not cache_dir.exists():
        raise SystemExit(f"Cache dir not found: {cache_dir}")

    daily_papers: dict[str, list[dict[str, Any]]] = {}
    skipped_missing = 0

    with sqlite3.connect(state_db) as conn:
        conn.row_factory = sqlite3.Row
        rows = conn.execute(
            """
            SELECT arxiv_id, version, title, categories, latest_version_date,
                   source_url, html_path, bytes
            FROM arxiv_html_scrape
            WHERE status = 'success'
            ORDER BY latest_version_date DESC, arxiv_id ASC
            """
        ).fetchall()

    for row in rows:
        paper = _paper_from_row(row, cache_dir=cache_dir, prefix=prefix)
        if not paper:
            skipped_missing += 1
            continue
        day = _date_part(paper["latest_version_date"])
        if not day:
            continue
        metadata = _metadata_from_html(_resolve_html_path(row, cache_dir))
        daily_papers.setdefault(day, []).append(
            {
                "arxiv_id": paper["arxiv_id"],
                "version": paper["version"],
                "title": metadata["title"] or paper["title"],
                "abstract": metadata["abstract"],
                "authors": metadata["authors"],
                "categories": paper["categories"],
                "latest_version_date": paper["latest_version_date"],
                "source_url": paper["source_url"],
                "html_key": paper["html_key"],
                "bytes": paper["bytes"],
            }
        )

    return _build_sharded_index(
        daily_papers,
        html_prefix=prefix,
        date_index_prefix=date_index_prefix,
        skipped_missing_files=skipped_missing,
    )


def _build_sharded_index(
    daily_papers: dict[str, list[dict[str, Any]]],
    *,
    html_prefix: str,
    date_index_prefix: str,
    skipped_missing_files: int,
) -> tuple[dict[str, Any], dict[str, dict[str, Any]]]:
    generated_at = datetime.now(timezone.utc).isoformat()
    normalized_date_prefix = normalize_prefix(date_index_prefix)
    manifest_dates: dict[str, dict[str, Any]] = {}
    date_shards: dict[str, dict[str, Any]] = {}

    for day in sorted(daily_papers.keys(), reverse=True):
        papers = sorted(daily_papers[day], key=lambda item: str(item.get("arxiv_id") or ""))
        index_key = date_index_key(date=day, date_index_prefix=normalized_date_prefix)
        manifest_dates[day] = {"count": len(papers), "index_key": index_key}
        date_shards[day] = {
            "schema_version": SCHEMA_VERSION,
            "source": "arxiv",
            "date": day,
            "generated_at": generated_at,
            "count": len(papers),
            "papers": papers,
        }

    manifest = {
        "schema_version": SCHEMA_VERSION,
        "source": "arxiv",
        "generated_at": generated_at,
        "html_prefix": normalize_prefix(html_prefix),
        "date_index_prefix": normalized_date_prefix,
        "skipped_missing_files": skipped_missing_files,
        "total_papers": sum(day["count"] for day in manifest_dates.values()),
        "dates": manifest_dates,
    }
    return manifest, date_shards


def _paper_from_row(row: sqlite3.Row, *, cache_dir: Path, prefix: str) -> dict[str, Any] | None:
    arxiv_id = str(row["arxiv_id"])
    html_path = _resolve_html_path(row, cache_dir)
    if not html_path:
        return None
    try:
        categories = json.loads(row["categories"] or "[]")
    except json.JSONDecodeError:
        categories = [c for c in (row["categories"] or "").split() if c]
    relative = html_path.resolve().relative_to(cache_dir.resolve()).as_posix()
    prefix_norm = prefix.strip("/")
    html_key = f"{prefix_norm}/{relative}" if prefix_norm else relative
    return {
        "arxiv_id": arxiv_id,
        "version": row["version"] or "",
        "title": row["title"] or arxiv_id,
        "categories": [str(c) for c in categories],
        "latest_version_date": row["latest_version_date"] or "",
        "source_url": row["source_url"] or f"https://arxiv.org/html/{arxiv_id}",
        "html_key": html_key,
        "bytes": int(row["bytes"] or 0),
    }


def _resolve_html_path(row: sqlite3.Row, cache_dir: Path) -> Path | None:
    arxiv_id = str(row["arxiv_id"])
    candidates: list[Path] = []
    if row["html_path"]:
        recorded = Path(row["html_path"]).expanduser()
        if not recorded.is_absolute():
            candidates.append(cache_dir / recorded)
    candidates.append(cache_dir / arxiv_id[:4] / f"{SAFE_ID_RE.sub('_', arxiv_id)}.html")
    for candidate in candidates:
        resolved = candidate.resolve()
        if resolved.is_file():
            return resolved
    return None


def _metadata_from_html(html_path: Path | None) -> dict[str, Any]:
    if html_path is None or not html_path.is_file():
        return {"title": "", "abstract": "", "authors": []}
    try:
        html = html_path.read_text(encoding="utf-8", errors="replace")
    except OSError:
        return {"title": "", "abstract": "", "authors": []}
    soup = BeautifulSoup(html, "lxml")
    title_el = soup.select_one(".ltx_title_document") or soup.find("title")
    authors = [
        " ".join(a.get_text(" ", strip=True).split())
        for a in soup.select(".ltx_authors .ltx_personname")
    ]
    abstract_el = soup.select_one(".ltx_abstract")
    if abstract_el:
        for heading in abstract_el.select(".ltx_title_abstract"):
            heading.decompose()
        abstract = " ".join(abstract_el.get_text(" ", strip=True).split())
    else:
        abstract = ""
    return {
        "title": " ".join(title_el.get_text(" ", strip=True).split()) if title_el else "",
        "abstract": abstract,
        "authors": [a for a in authors if a],
    }


def _date_part(value: str) -> str:
    if not value:
        return ""
    try:
        return datetime.fromisoformat(value.replace("Z", "+00:00")).date().isoformat()
    except ValueError:
        return value[:10]


def print_summary(manifest: dict[str, Any]) -> None:
    dates = manifest["dates"]
    newest = next(iter(dates), None)
    print(
        f"Indexed {manifest['total_papers']} papers across {len(dates)} dates; "
        f"newest={newest or 'none'}; skipped_missing={manifest['skipped_missing_files']}"
    )


def connect_state(db_path: Path) -> sqlite3.Connection:
    db_path.parent.mkdir(parents=True, exist_ok=True)
    return sqlite3.connect(db_path)


def create_state(conn: sqlite3.Connection) -> None:
    conn.execute(
        """
        CREATE TABLE IF NOT EXISTS arxiv_html_scrape (
            arxiv_id TEXT PRIMARY KEY,
            version TEXT,
            title TEXT NOT NULL DEFAULT '',
            categories TEXT NOT NULL DEFAULT '[]',
            latest_version_date TEXT,
            source_url TEXT,
            html_path TEXT,
            status TEXT NOT NULL DEFAULT 'pending',
            status_code INTEGER,
            bytes INTEGER NOT NULL DEFAULT 0,
            error TEXT,
            updated_at TEXT NOT NULL
        )
        """
    )
    conn.commit()


def upsert_candidates(conn: sqlite3.Connection, candidates: Iterable[Candidate]) -> None:
    now = datetime.now(timezone.utc).isoformat()
    for candidate in candidates:
        conn.execute(
            """
            INSERT INTO arxiv_html_scrape (
                arxiv_id, version, title, categories, latest_version_date, updated_at
            )
            VALUES (?, ?, ?, ?, ?, ?)
            ON CONFLICT(arxiv_id) DO UPDATE SET
                version = excluded.version,
                title = excluded.title,
                categories = excluded.categories,
                latest_version_date = excluded.latest_version_date
            """,
            (
                candidate.arxiv_id,
                candidate.version,
                candidate.title,
                json.dumps(candidate.categories),
                candidate.latest_version_date,
                now,
            ),
        )
    conn.commit()


def already_done(conn: sqlite3.Connection, arxiv_id: str) -> bool:
    row = conn.execute(
        "SELECT status FROM arxiv_html_scrape WHERE arxiv_id = ?",
        (arxiv_id,),
    ).fetchone()
    return bool(row and row[0] == "success")


def record_result(conn: sqlite3.Connection, candidate: Candidate, result: dict[str, Any]) -> None:
    conn.execute(
        """
        UPDATE arxiv_html_scrape SET
            source_url = ?, html_path = ?, status = ?, status_code = ?,
            bytes = ?, error = ?, updated_at = ?
        WHERE arxiv_id = ?
        """,
        (
            result.get("source_url") or candidate.html_url,
            result.get("html_path"),
            result["status"],
            result.get("status_code"),
            result.get("bytes", 0),
            result.get("error"),
            datetime.now(timezone.utc).isoformat(),
            candidate.arxiv_id,
        ),
    )
    conn.commit()


def _version_from_id(value: str) -> str:
    arxiv_id = value.rstrip("/").rsplit("/", 1)[-1]
    match = VERSION_RE.search(arxiv_id)
    return match.group(0) if match else ""


if __name__ == "__main__":
    main()
