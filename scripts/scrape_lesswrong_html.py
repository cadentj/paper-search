#!/usr/bin/env python3
# /// script
# requires-python = ">=3.11"
# dependencies = ["httpx>=0.27.0", "tqdm>=4.66.0"]
# ///
"""Build a local LessWrong HTML cache for the daily-search date window."""

from __future__ import annotations

import argparse
import json
import re
import sqlite3
import time
from dataclasses import dataclass
from datetime import date, datetime, timedelta, timezone
from pathlib import Path
from typing import Any, Iterable

import httpx
from tqdm import tqdm


REPO_ROOT = Path(__file__).resolve().parents[1]
DEFAULT_OUTPUT_DIR = REPO_ROOT / "data" / "lesswrong_html_cache"
GRAPHQL_URL = "https://www.lesswrong.com/graphql"
SAFE_ID_RE = re.compile(r"[^A-Za-z0-9_.-]+")

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
        html
      }
    }
  }
}
"""


@dataclass(frozen=True)
class LessWrongPost:
    post_id: str
    title: str
    slug: str
    page_url: str
    posted_at: str
    author: str
    base_score: float | int | None
    html: str


def main() -> None:
    args = parse_args()
    output_dir = Path(args.output_dir).expanduser().resolve()
    output_dir.mkdir(parents=True, exist_ok=True)
    db_path = output_dir / "scrape_state.sqlite"

    anchor_date = date.fromisoformat(args.anchor_date)
    start_date = anchor_date - timedelta(days=args.days - 1)
    dates = [start_date + timedelta(days=offset) for offset in range(args.days)]

    with connect_state(db_path) as conn:
        create_state(conn)
        scrape_dates(args, conn, dates, output_dir)


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output-dir", default=str(DEFAULT_OUTPUT_DIR))
    parser.add_argument("--anchor-date", default="2026-05-14")
    parser.add_argument("--days", type=int, default=31)
    parser.add_argument("--limit-per-day", type=int, default=500)
    parser.add_argument("--graphql-url", default=GRAPHQL_URL)
    parser.add_argument("--sleep", type=float, default=1.0)
    parser.add_argument("--timeout", type=float, default=30.0)
    parser.add_argument("--user-agent", default="paper-search-lesswrong-cache/0.1 contact: local-research")
    return parser.parse_args()


def scrape_dates(
    args: argparse.Namespace,
    conn: sqlite3.Connection,
    dates: list[date],
    output_dir: Path,
) -> None:
    headers = {"User-Agent": args.user_agent}
    with httpx.Client(timeout=args.timeout, follow_redirects=True, headers=headers) as client, tqdm(
        total=len(dates),
        desc="lesswrong days",
        unit="day",
        dynamic_ncols=True,
    ) as progress:
        for day in dates:
            if date_done(conn, day):
                progress.update(1)
                continue
            posts = fetch_posts_for_day(client, args, day)
            for post in posts:
                write_post(output_dir, post)
                record_post(conn, post)
            record_day(conn, day, len(posts))
            progress.set_postfix(day=day.isoformat(), posts=len(posts))
            progress.update(1)
            time.sleep(max(args.sleep, 0.0))


def fetch_posts_for_day(
    client: httpx.Client,
    args: argparse.Namespace,
    day: date,
) -> list[LessWrongPost]:
    response = client.post(
        args.graphql_url,
        json={
            "query": POSTS_QUERY,
            "variables": {
                "after": day.isoformat(),
                "before": (day + timedelta(days=1)).isoformat(),
                "limit": args.limit_per_day,
            },
        },
    )
    response.raise_for_status()
    payload = response.json()
    if payload.get("errors"):
        raise RuntimeError(f"LessWrong GraphQL error for {day}: {payload['errors']}")
    records = (((payload.get("data") or {}).get("posts") or {}).get("results") or [])
    return [post_from_record(record) for record in records if record.get("_id")]


def post_from_record(record: dict[str, Any]) -> LessWrongPost:
    user = record.get("user") or {}
    author = user.get("displayName") or user.get("username") or ""
    return LessWrongPost(
        post_id=str(record.get("_id") or ""),
        title=record.get("title") or "Untitled LessWrong post",
        slug=record.get("slug") or "",
        page_url=record.get("pageUrl") or "",
        posted_at=record.get("postedAt") or "",
        author=author,
        base_score=record.get("baseScore"),
        html=((record.get("contents") or {}).get("html") or ""),
    )


def write_post(output_dir: Path, post: LessWrongPost) -> Path:
    html_dir = output_dir / "html" / post.post_id[:2]
    html_dir.mkdir(parents=True, exist_ok=True)
    html_path = html_dir / f"{safe_filename(post.post_id)}.html"
    html_path.write_text(post.html, encoding="utf-8")
    return html_path


def connect_state(db_path: Path) -> sqlite3.Connection:
    db_path.parent.mkdir(parents=True, exist_ok=True)
    return sqlite3.connect(db_path)


def create_state(conn: sqlite3.Connection) -> None:
    conn.execute(
        """
        CREATE TABLE IF NOT EXISTS lesswrong_html_scrape (
            post_id TEXT PRIMARY KEY,
            title TEXT NOT NULL DEFAULT '',
            slug TEXT NOT NULL DEFAULT '',
            page_url TEXT NOT NULL DEFAULT '',
            posted_at TEXT NOT NULL DEFAULT '',
            author TEXT NOT NULL DEFAULT '',
            base_score REAL,
            html_path TEXT,
            status TEXT NOT NULL DEFAULT 'success',
            bytes INTEGER NOT NULL DEFAULT 0,
            updated_at TEXT NOT NULL
        )
        """
    )
    conn.execute(
        """
        CREATE TABLE IF NOT EXISTS lesswrong_day_scrape (
            day TEXT PRIMARY KEY,
            post_count INTEGER NOT NULL DEFAULT 0,
            updated_at TEXT NOT NULL
        )
        """
    )
    conn.commit()


def date_done(conn: sqlite3.Connection, day: date) -> bool:
    row = conn.execute(
        "SELECT day FROM lesswrong_day_scrape WHERE day = ?",
        (day.isoformat(),),
    ).fetchone()
    return bool(row)


def record_day(conn: sqlite3.Connection, day: date, post_count: int) -> None:
    conn.execute(
        """
        INSERT INTO lesswrong_day_scrape (day, post_count, updated_at)
        VALUES (?, ?, ?)
        ON CONFLICT(day) DO UPDATE SET
            post_count = excluded.post_count,
            updated_at = excluded.updated_at
        """,
        (day.isoformat(), post_count, datetime.now(timezone.utc).isoformat()),
    )
    conn.commit()


def record_post(conn: sqlite3.Connection, post: LessWrongPost) -> None:
    html_path = f"{post.post_id[:2]}/{safe_filename(post.post_id)}.html"
    conn.execute(
        """
        INSERT INTO lesswrong_html_scrape (
            post_id, title, slug, page_url, posted_at, author, base_score,
            html_path, status, bytes, updated_at
        )
        VALUES (?, ?, ?, ?, ?, ?, ?, ?, 'success', ?, ?)
        ON CONFLICT(post_id) DO UPDATE SET
            title = excluded.title,
            slug = excluded.slug,
            page_url = excluded.page_url,
            posted_at = excluded.posted_at,
            author = excluded.author,
            base_score = excluded.base_score,
            html_path = excluded.html_path,
            status = excluded.status,
            bytes = excluded.bytes,
            updated_at = excluded.updated_at
        """,
        (
            post.post_id,
            post.title,
            post.slug,
            post.page_url,
            post.posted_at,
            post.author,
            post.base_score,
            html_path,
            len(post.html.encode("utf-8")),
            datetime.now(timezone.utc).isoformat(),
        ),
    )
    conn.commit()


def safe_filename(value: str) -> str:
    return SAFE_ID_RE.sub("_", value)


if __name__ == "__main__":
    main()
