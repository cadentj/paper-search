#!/usr/bin/env python3
"""Scrape LessWrong HTML, upload to R2, and publish the date index."""

from __future__ import annotations

import argparse
import logging
import re
import sqlite3
import sys
import time
from dataclasses import dataclass
from datetime import date, datetime, timedelta, timezone
from pathlib import Path
from typing import Any

import httpx
from bs4 import BeautifulSoup
from tqdm import tqdm

from paper_search_core.daily_dates import DAILY_SEARCH_END

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
GRAPHQL_URL = "https://www.lesswrong.com/graphql"
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
      user { displayName username }
      contents { html }
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
    settings = Settings()
    start_date, end_date = parse_date_window(args)
    steps = resolve_steps(args.step)
    cookie = load_cookie(args, settings)

    logger.info(
        "ingest-lesswrong %s..%s steps=%s",
        start_date.isoformat(),
        end_date.isoformat(),
        ",".join(steps),
    )

    if "scrape" in steps:
        run_scrape(settings, start_date, end_date, args, cookie)
    if "upload-html" in steps:
        client = r2_client(settings, max_pool_connections=args.workers * 2)
        upload_html(
            client,
            bucket=settings.R2_BUCKET,
            cache_dir=settings.lesswrong_html_cache_dir(),
            prefix=settings.LESSWRONG_HTML_PREFIX,
            workers=args.workers,
            skip_existing=not args.no_skip_existing,
            limit=args.upload_limit,
            content_type="text/html; charset=utf-8",
        )
    if "publish-index" in steps:
        publish_index(settings)


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--end-date", default=DAILY_SEARCH_END.isoformat())
    parser.add_argument("--start-date")
    parser.add_argument("--days", type=int, default=31)
    parser.add_argument("--step", action="append", choices=STEPS)
    parser.add_argument("--window-days", type=int, default=5)
    parser.add_argument("--limit-per-window", type=int, default=500)
    parser.add_argument("--sleep", type=float, default=1.0)
    parser.add_argument("--timeout", type=float, default=30.0)
    parser.add_argument("--cookie-file")
    parser.add_argument("--cookie")
    parser.add_argument(
        "--user-agent",
        default=(
            "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
            "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/148.0.0.0 Safari/537.36"
        ),
    )
    parser.add_argument("--workers", type=int, default=16)
    parser.add_argument("--no-skip-existing", action="store_true")
    parser.add_argument("--upload-limit", type=int, default=None)
    return parser.parse_args()


def parse_date_window(args: argparse.Namespace) -> tuple[date, date]:
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


def load_cookie(args: argparse.Namespace, settings: Settings) -> str:
    if args.cookie_file:
        return Path(args.cookie_file).expanduser().read_text(encoding="utf-8").strip()
    if args.cookie:
        return args.cookie.strip()
    return settings.lesswrong_cookie()


def run_scrape(
    settings: Settings,
    start_date: date,
    end_date: date,
    args: argparse.Namespace,
    cookie: str,
) -> None:
    output_dir = settings.lesswrong_cache_dir()
    output_dir.mkdir(parents=True, exist_ok=True)
    db_path = output_dir / "scrape_state.sqlite"
    days = (end_date - start_date).days + 1
    dates = [start_date + timedelta(days=offset) for offset in range(days)]

    with connect_state(db_path) as conn:
        create_state(conn)
        scrape_windows(
            args,
            conn,
            dates,
            output_dir,
            cookie,
            preview_words=settings.LESSWRONG_PREVIEW_WORDS,
        )


def scrape_windows(
    args: argparse.Namespace,
    conn: sqlite3.Connection,
    dates: list[date],
    output_dir: Path,
    cookie: str,
    *,
    preview_words: int,
) -> None:
    windows = date_windows(dates, args.window_days)
    headers = {
        "User-Agent": args.user_agent,
        "Referer": "https://www.lesswrong.com/graphiql",
        "Origin": "https://www.lesswrong.com",
    }
    if cookie:
        headers["Cookie"] = cookie

    with (
        httpx.Client(
            timeout=args.timeout, follow_redirects=True, headers=headers
        ) as client,
        tqdm(
            total=len(windows),
            desc="lesswrong windows",
            unit="window",
            dynamic_ncols=True,
        ) as progress,
    ):
        for start_day, end_day in windows:
            if window_done(conn, start_day, end_day):
                progress.update(1)
                continue
            posts = fetch_posts_for_window(client, args, start_day, end_day)
            for post in posts:
                write_post(output_dir, post)
                record_post(conn, post, preview_words=preview_words)
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
        GRAPHQL_URL,
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
            "LessWrong returned a Vercel challenge. Set LESSWRONG_COOKIE_FILE or --cookie-file."
        )
    response.raise_for_status()
    payload = response.json()
    if payload.get("errors"):
        raise RuntimeError(f"LessWrong GraphQL error: {payload['errors']}")
    records = ((payload.get("data") or {}).get("posts") or {}).get("results") or []
    if len(records) >= args.limit_per_window:
        raise RuntimeError(
            f"Window {start_day}..{end_day} hit --limit-per-window={args.limit_per_window}"
        )
    return [post_from_record(r) for r in records if r.get("_id")]


def post_from_record(record: dict[str, Any]) -> LessWrongPost:
    user = record.get("user") or {}
    return LessWrongPost(
        post_id=str(record.get("_id") or ""),
        title=record.get("title") or "Untitled LessWrong post",
        slug=record.get("slug") or "",
        page_url=record.get("pageUrl") or "",
        posted_at=record.get("postedAt") or "",
        author=user.get("displayName") or user.get("username") or "",
        base_score=record.get("baseScore"),
        html=((record.get("contents") or {}).get("html") or ""),
    )


def write_post(output_dir: Path, post: LessWrongPost) -> None:
    html_dir = output_dir / "html" / post.post_id[:2]
    html_dir.mkdir(parents=True, exist_ok=True)
    (html_dir / f"{SAFE_ID_RE.sub('_', post.post_id)}.html").write_text(
        post.html, encoding="utf-8"
    )


def publish_index(settings: Settings) -> None:
    state_db = settings.lesswrong_cache_dir() / "scrape_state.sqlite"
    cache_dir = settings.lesswrong_html_cache_dir()
    manifest, date_shards = build_index(
        state_db=state_db,
        cache_dir=cache_dir,
        prefix=settings.LESSWRONG_HTML_PREFIX,
        date_index_prefix=settings.LESSWRONG_DATE_INDEX_PREFIX,
        preview_words=settings.LESSWRONG_PREVIEW_WORDS,
    )
    print_summary(manifest)
    client = r2_client(settings)
    upload_sharded_index(
        client,
        bucket=settings.R2_BUCKET,
        index_key=settings.LESSWRONG_HTML_INDEX_PATH,
        manifest=manifest,
        date_shards=date_shards,
    )


def build_index(
    *,
    state_db: Path,
    cache_dir: Path,
    prefix: str,
    date_index_prefix: str,
    preview_words: int,
) -> tuple[dict[str, Any], dict[str, dict[str, Any]]]:
    if not state_db.exists():
        raise SystemExit(f"State DB not found: {state_db}")
    if not cache_dir.exists():
        raise SystemExit(f"Cache dir not found: {cache_dir}")

    dates: dict[str, dict[str, Any]] = {}
    skipped_missing = 0

    with sqlite3.connect(state_db) as conn:
        conn.row_factory = sqlite3.Row
        has_preview = "text_preview" in {
            row[1] for row in conn.execute("PRAGMA table_info(lesswrong_html_scrape)")
        }
        preview_col = "text_preview" if has_preview else "'' AS text_preview"
        rows = conn.execute(
            f"""
            SELECT post_id, title, slug, page_url, posted_at, author,
                   base_score, html_path, {preview_col}, bytes
            FROM lesswrong_html_scrape
            WHERE status = 'success'
            ORDER BY posted_at DESC, post_id ASC
            """
        ).fetchall()

    for row in rows:
        post = _post_from_row(
            row, cache_dir=cache_dir, prefix=prefix, preview_words=preview_words
        )
        if not post:
            skipped_missing += 1
            continue
        day = _date_part(post["posted_at"])
        if not day:
            continue
        bucket = dates.setdefault(day, {"count": 0, "posts": []})
        bucket["posts"].append(post)

    generated_at = datetime.now(timezone.utc).isoformat()
    normalized_date_prefix = normalize_prefix(date_index_prefix)
    manifest_dates: dict[str, dict[str, Any]] = {}
    date_shards: dict[str, dict[str, Any]] = {}

    for day in sorted(dates.keys(), reverse=True):
        posts = sorted(
            dates[day]["posts"], key=lambda item: item["posted_at"], reverse=True
        )
        index_key = date_index_key(date=day, date_index_prefix=normalized_date_prefix)
        manifest_dates[day] = {"count": len(posts), "index_key": index_key}
        date_shards[day] = {
            "schema_version": 2,
            "source": "lesswrong",
            "date": day,
            "generated_at": generated_at,
            "count": len(posts),
            "posts": posts,
        }

    manifest = {
        "schema_version": 2,
        "source": "lesswrong",
        "generated_at": generated_at,
        "html_prefix": normalize_prefix(prefix),
        "date_index_prefix": normalized_date_prefix,
        "skipped_missing_files": skipped_missing,
        "total_posts": sum(day["count"] for day in manifest_dates.values()),
        "dates": manifest_dates,
    }
    return manifest, date_shards


def _post_from_row(
    row: sqlite3.Row,
    *,
    cache_dir: Path,
    prefix: str,
    preview_words: int,
) -> dict[str, Any] | None:
    post_id = str(row["post_id"])
    if not row["html_path"]:
        return None
    html_path = cache_dir / row["html_path"]
    if not html_path.is_file():
        return None
    text_preview = row["text_preview"] or _preview_from_file(html_path, preview_words)
    html_key = (
        f"{normalize_prefix(prefix)}{html_path.relative_to(cache_dir).as_posix()}"
    )
    return {
        "post_id": post_id,
        "title": row["title"] or "Untitled LessWrong post",
        "slug": row["slug"] or "",
        "page_url": row["page_url"] or f"https://www.lesswrong.com/posts/{post_id}",
        "posted_at": row["posted_at"] or "",
        "author": row["author"] or "",
        "base_score": row["base_score"],
        "html_key": html_key,
        "text_preview": text_preview,
        "bytes": int(row["bytes"] or 0),
    }


def _preview_from_file(html_path: Path, preview_words: int) -> str:
    try:
        html = html_path.read_text(encoding="utf-8")
    except OSError:
        return ""
    return _first_words(_extract_plaintext(html), preview_words)


def _extract_plaintext(html: str) -> str:
    if not html:
        return ""
    soup = BeautifulSoup(html, "lxml")
    for element in soup(["script", "style", "noscript"]):
        element.decompose()
    return " ".join(soup.get_text(" ", strip=True).split())


def _first_words(value: str, count: int) -> str:
    words = value.split()
    return " ".join(words[:count]) if len(words) > count else " ".join(words)


def _date_part(value: str) -> str:
    if not value:
        return ""
    try:
        return datetime.fromisoformat(value.replace("Z", "+00:00")).date().isoformat()
    except ValueError:
        return value[:10]


def print_summary(index: dict[str, Any]) -> None:
    dates = index["dates"]
    newest = next(iter(dates), None)
    print(
        f"Indexed {index['total_posts']} posts across {len(dates)} dates; "
        f"newest={newest or 'none'}; skipped_missing={index['skipped_missing_files']}"
    )


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
    columns = {
        row[1] for row in conn.execute("PRAGMA table_info(lesswrong_html_scrape)")
    }
    if "text_preview" not in columns:
        conn.execute(
            "ALTER TABLE lesswrong_html_scrape ADD COLUMN text_preview TEXT NOT NULL DEFAULT ''"
        )
    conn.commit()


def window_done(conn: sqlite3.Connection, start_day: date, end_day: date) -> bool:
    row = conn.execute(
        "SELECT start_day FROM lesswrong_window_scrape WHERE start_day = ? AND end_day = ?",
        (start_day.isoformat(), end_day.isoformat()),
    ).fetchone()
    return bool(row)


def record_window(
    conn: sqlite3.Connection, start_day: date, end_day: date, post_count: int
) -> None:
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


def record_post(
    conn: sqlite3.Connection, post: LessWrongPost, *, preview_words: int
) -> None:
    html_path = f"{post.post_id[:2]}/{SAFE_ID_RE.sub('_', post.post_id)}.html"
    text_preview = _first_words(_extract_plaintext(post.html), preview_words)
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
