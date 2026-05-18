#!/usr/bin/env python3
# /// script
# requires-python = ">=3.11"
# dependencies = ["beautifulsoup4>=4.12.0", "httpx>=0.27.0", "lxml>=5.0.0", "tqdm>=4.66.0"]
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
from typing import Any

import httpx
from bs4 import BeautifulSoup
from tqdm import tqdm


REPO_ROOT = Path(__file__).resolve().parents[1]
DEFAULT_OUTPUT_DIR = REPO_ROOT / "data" / "lesswrong_html_cache"
GRAPHQL_URL = "https://www.lesswrong.com/graphql"
DEFAULT_PREVIEW_WORDS = 250
SAFE_ID_RE = re.compile(r"[^A-Za-z0-9_.-]+")

POSTS_QUERY = """
query LessWrongPosts($after: String!, $before: String!, $limit: Int!) {
  posts(selector: { new: { after: $after, before: $before } }, limit: $limit) {
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
        scrape_windows(args, conn, dates, output_dir)


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output-dir", default=str(DEFAULT_OUTPUT_DIR))
    parser.add_argument("--anchor-date", default="2026-05-14")
    parser.add_argument("--days", type=int, default=31)
    parser.add_argument("--window-days", type=int, default=5)
    parser.add_argument("--limit-per-window", type=int, default=500)
    parser.add_argument("--preview-words", type=int, default=DEFAULT_PREVIEW_WORDS)
    parser.add_argument("--graphql-url", default=GRAPHQL_URL)
    parser.add_argument("--sleep", type=float, default=1.0)
    parser.add_argument("--timeout", type=float, default=30.0)
    parser.add_argument("--cookie-file", help="File containing a browser Cookie header value.")
    parser.add_argument("--cookie", help="Raw browser Cookie header value. Prefer --cookie-file.")
    parser.add_argument(
        "--user-agent",
        default="Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/148.0.0.0 Safari/537.36",
    )
    return parser.parse_args()


def scrape_windows(
    args: argparse.Namespace,
    conn: sqlite3.Connection,
    dates: list[date],
    output_dir: Path,
) -> None:
    windows = date_windows(dates, args.window_days)
    headers = {
        "User-Agent": args.user_agent,
        "Referer": "https://www.lesswrong.com/graphiql",
        "Origin": "https://www.lesswrong.com",
    }
    cookie = load_cookie(args)
    if cookie:
        headers["Cookie"] = cookie
    with httpx.Client(timeout=args.timeout, follow_redirects=True, headers=headers) as client, tqdm(
        total=len(windows),
        desc="lesswrong windows",
        unit="window",
        dynamic_ncols=True,
    ) as progress:
        for start_day, end_day in windows:
            if window_done(conn, start_day, end_day):
                progress.update(1)
                continue
            posts = fetch_posts_for_window(client, args, start_day, end_day)
            for post in posts:
                write_post(output_dir, post)
                record_post(conn, post, preview_words=args.preview_words)
            record_window(conn, start_day, end_day, len(posts))
            progress.set_postfix(
                window=f"{start_day.isoformat()}..{end_day.isoformat()}",
                posts=len(posts),
            )
            progress.update(1)
            time.sleep(max(args.sleep, 0.0))


def fetch_posts_for_window(
    client: httpx.Client,
    args: argparse.Namespace,
    start_day: date,
    end_day: date,
) -> list[LessWrongPost]:
    response = client.post(
        args.graphql_url,
        json={
            "query": POSTS_QUERY,
            "variables": {
                "after": start_iso(start_day),
                "before": start_iso(end_day + timedelta(days=1)),
                "limit": args.limit_per_window,
            },
        },
    )
    if response.status_code == 429 and "Vercel Security Checkpoint" in response.text:
        raise RuntimeError(
            "LessWrong returned a Vercel challenge. Put the browser Cookie "
            "request header in a local file and pass --cookie-file."
        )
    response.raise_for_status()
    payload = response.json()
    if payload.get("errors"):
        raise RuntimeError(
            f"LessWrong GraphQL error for {start_day}..{end_day}: {payload['errors']}"
        )
    records = (((payload.get("data") or {}).get("posts") or {}).get("results") or [])
    if len(records) >= args.limit_per_window:
        raise RuntimeError(
            f"LessWrong returned {len(records)} posts for {start_day}..{end_day}, "
            "which reached --limit-per-window. Rerun with a smaller --window-days."
        )
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
            text_preview TEXT NOT NULL DEFAULT '',
            status TEXT NOT NULL DEFAULT 'success',
            bytes INTEGER NOT NULL DEFAULT 0,
            updated_at TEXT NOT NULL
        )
        """
    )
    conn.execute(
        """
        CREATE TABLE IF NOT EXISTS lesswrong_window_scrape (
            start_day TEXT NOT NULL,
            end_day TEXT NOT NULL,
            post_count INTEGER NOT NULL DEFAULT 0,
            updated_at TEXT NOT NULL,
            PRIMARY KEY (start_day, end_day)
        )
        """
    )
    add_column_if_missing(
        conn,
        table="lesswrong_html_scrape",
        column="text_preview",
        definition="TEXT NOT NULL DEFAULT ''",
    )
    conn.commit()


def add_column_if_missing(
    conn: sqlite3.Connection,
    *,
    table: str,
    column: str,
    definition: str,
) -> None:
    columns = {row[1] for row in conn.execute(f"PRAGMA table_info({table})")}
    if column not in columns:
        conn.execute(f"ALTER TABLE {table} ADD COLUMN {column} {definition}")


def window_done(conn: sqlite3.Connection, start_day: date, end_day: date) -> bool:
    row = conn.execute(
        "SELECT start_day FROM lesswrong_window_scrape WHERE start_day = ? AND end_day = ?",
        (start_day.isoformat(), end_day.isoformat()),
    ).fetchone()
    return bool(row)


def record_window(conn: sqlite3.Connection, start_day: date, end_day: date, post_count: int) -> None:
    conn.execute(
        """
        INSERT INTO lesswrong_window_scrape (start_day, end_day, post_count, updated_at)
        VALUES (?, ?, ?, ?)
        ON CONFLICT(start_day, end_day) DO UPDATE SET
            post_count = excluded.post_count,
            updated_at = excluded.updated_at
        """,
        (
            start_day.isoformat(),
            end_day.isoformat(),
            post_count,
            datetime.now(timezone.utc).isoformat(),
        ),
    )
    conn.commit()


def record_post(conn: sqlite3.Connection, post: LessWrongPost, *, preview_words: int) -> None:
    html_path = f"{post.post_id[:2]}/{safe_filename(post.post_id)}.html"
    text_preview = first_words(extract_plaintext(post.html), preview_words)
    conn.execute(
        """
        INSERT INTO lesswrong_html_scrape (
            post_id, title, slug, page_url, posted_at, author, base_score,
            html_path, text_preview, status, bytes, updated_at
        )
        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, 'success', ?, ?)
        ON CONFLICT(post_id) DO UPDATE SET
            title = excluded.title,
            slug = excluded.slug,
            page_url = excluded.page_url,
            posted_at = excluded.posted_at,
            author = excluded.author,
            base_score = excluded.base_score,
            html_path = excluded.html_path,
            text_preview = excluded.text_preview,
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
            text_preview,
            len(post.html.encode("utf-8")),
            datetime.now(timezone.utc).isoformat(),
        ),
    )
    conn.commit()


def safe_filename(value: str) -> str:
    return SAFE_ID_RE.sub("_", value)


def extract_plaintext(html: str) -> str:
    if not html:
        return ""
    soup = BeautifulSoup(html, "lxml")
    for element in soup(["script", "style", "noscript"]):
        element.decompose()
    return " ".join(soup.get_text(" ", strip=True).split())


def first_words(value: str, count: int) -> str:
    words = value.split()
    if len(words) <= count:
        return " ".join(words)
    return " ".join(words[:count])


def load_cookie(args: argparse.Namespace) -> str:
    if args.cookie_file:
        return Path(args.cookie_file).expanduser().read_text(encoding="utf-8").strip()
    return (args.cookie or "").strip()


def date_windows(dates: list[date], window_days: int) -> list[tuple[date, date]]:
    size = max(window_days, 1)
    windows = []
    for index in range(0, len(dates), size):
        chunk = dates[index : index + size]
        if chunk:
            windows.append((chunk[0], chunk[-1]))
    return windows


def start_iso(day: date) -> str:
    return f"{day.isoformat()}T00:00:00Z"


if __name__ == "__main__":
    main()
