#!/usr/bin/env python3
# /// script
# requires-python = ">=3.11"
# dependencies = ["beautifulsoup4>=4.12.0", "boto3>=1.34.0", "lxml>=5.0.0"]
# ///
"""Build and upload a date-keyed LessWrong HTML scrape index to Cloudflare R2."""

from __future__ import annotations

import argparse
import json
import os
import sqlite3
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import boto3
from bs4 import BeautifulSoup
from botocore.config import Config


REPO_ROOT = Path(__file__).resolve().parents[1]
DEFAULT_STATE_DB = REPO_ROOT / "data" / "lesswrong_html_cache" / "scrape_state.sqlite"
DEFAULT_CACHE_DIR = REPO_ROOT / "data" / "lesswrong_html_cache" / "html"
DEFAULT_PREVIEW_WORDS = 250


@dataclass(frozen=True)
class ScrapedPost:
    post_id: str
    title: str
    slug: str
    page_url: str
    posted_at: str
    author: str
    base_score: float | None
    html_key: str
    text_preview: str
    bytes: int


def main() -> None:
    args = parse_args()
    manifest, date_shards = build_index(
        state_db=Path(args.state_db).expanduser().resolve(),
        cache_dir=Path(args.cache_dir).expanduser().resolve(),
        prefix=args.prefix,
        date_index_prefix=args.date_index_prefix,
        preview_words=args.preview_words,
        verify_files=not args.no_verify_files,
    )
    manifest_body = json_body(manifest, pretty=args.pretty)

    if args.output:
        output_path = Path(args.output).expanduser().resolve()
        output_path.parent.mkdir(parents=True, exist_ok=True)
        output_path.write_text(manifest_body, encoding="utf-8")
        print(f"Wrote {output_path}")

    if args.output_dir:
        write_index_files(Path(args.output_dir).expanduser().resolve(), manifest, date_shards, pretty=args.pretty)

    print_summary(manifest)
    if args.dry_run:
        return

    client = r2_client(args)
    client.put_object(
        Bucket=args.bucket,
        Key=args.index_key,
        Body=manifest_body.encode("utf-8"),
        ContentType="application/json",
        CacheControl="no-cache",
    )
    print(f"Uploaded s3://{args.bucket}/{args.index_key}")
    for day, shard in date_shards.items():
        key = manifest["dates"][day]["index_key"]
        client.put_object(
            Bucket=args.bucket,
            Key=key,
            Body=json_body(shard, pretty=args.pretty).encode("utf-8"),
            ContentType="application/json",
            CacheControl="no-cache",
        )
    print(f"Uploaded {len(date_shards)} date shards")


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--account-id", default=os.environ.get("R2_ACCOUNT_ID"))
    parser.add_argument("--access-key-id", default=os.environ.get("R2_ACCESS_KEY_ID"))
    parser.add_argument("--secret-access-key", default=os.environ.get("R2_SECRET_ACCESS_KEY"))
    parser.add_argument("--bucket", default=os.environ.get("R2_BUCKET"))
    parser.add_argument("--state-db", default=str(DEFAULT_STATE_DB))
    parser.add_argument("--cache-dir", default=str(DEFAULT_CACHE_DIR))
    parser.add_argument("--prefix", default="lesswrong-html/posts/")
    parser.add_argument("--index-key", default="lesswrong-html/index/posts-by-date.json")
    parser.add_argument("--date-index-prefix", default="lesswrong-html/index/dates/")
    parser.add_argument("--preview-words", type=int, default=DEFAULT_PREVIEW_WORDS)
    parser.add_argument("--output", help="Optional local path to write the generated JSON.")
    parser.add_argument("--output-dir", help="Optional local directory to write the manifest and date shards.")
    parser.add_argument("--dry-run", action="store_true")
    parser.add_argument("--pretty", action="store_true")
    parser.add_argument("--no-verify-files", action="store_true")
    return parser.parse_args()


def build_index(
    *,
    state_db: Path,
    cache_dir: Path,
    prefix: str,
    date_index_prefix: str,
    preview_words: int,
    verify_files: bool,
) -> tuple[dict[str, Any], dict[str, dict[str, Any]]]:
    if not state_db.exists():
        raise SystemExit(f"State DB not found: {state_db}")
    if verify_files and not cache_dir.exists():
        raise SystemExit(f"Cache dir not found: {cache_dir}")

    dates: dict[str, dict[str, Any]] = {}
    skipped_missing = 0
    for row in load_success_rows(state_db):
        post = post_from_row(
            row,
            cache_dir=cache_dir,
            prefix=prefix,
            preview_words=preview_words,
            verify_files=verify_files,
        )
        if not post:
            skipped_missing += 1
            continue
        day = date_part(post.posted_at)
        if not day:
            continue
        bucket = dates.setdefault(day, {"count": 0, "posts": []})
        bucket["posts"].append(
            {
                "post_id": post.post_id,
                "title": post.title,
                "slug": post.slug,
                "page_url": post.page_url,
                "posted_at": post.posted_at,
                "author": post.author,
                "base_score": post.base_score,
                "html_key": post.html_key,
                "text_preview": post.text_preview,
                "bytes": post.bytes,
            }
        )

    generated_at = datetime.now(timezone.utc).isoformat()
    normalized_date_prefix = normalize_prefix(date_index_prefix)
    manifest_dates: dict[str, dict[str, Any]] = {}
    date_shards: dict[str, dict[str, Any]] = {}
    for day in sorted(dates.keys(), reverse=True):
        posts = sorted(dates[day]["posts"], key=lambda item: item["posted_at"], reverse=True)
        index_key = f"{normalized_date_prefix}{day}.json"
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


def load_success_rows(state_db: Path) -> list[sqlite3.Row]:
    with sqlite3.connect(state_db) as conn:
        conn.row_factory = sqlite3.Row
        text_preview_expr = "text_preview" if has_column(conn, "lesswrong_html_scrape", "text_preview") else "'' AS text_preview"
        return conn.execute(
            f"""
            SELECT post_id, title, slug, page_url, posted_at, author,
                   base_score, html_path, {text_preview_expr}, bytes
            FROM lesswrong_html_scrape
            WHERE status = 'success'
            ORDER BY posted_at DESC, post_id ASC
            """
        ).fetchall()


def post_from_row(
    row: sqlite3.Row,
    *,
    cache_dir: Path,
    prefix: str,
    preview_words: int,
    verify_files: bool,
) -> ScrapedPost | None:
    post_id = str(row["post_id"])
    html_path = resolve_html_path(row["html_path"], cache_dir=cache_dir, verify_files=verify_files)
    if not html_path:
        return None
    return ScrapedPost(
        post_id=post_id,
        title=row["title"] or "Untitled LessWrong post",
        slug=row["slug"] or "",
        page_url=row["page_url"] or f"https://www.lesswrong.com/posts/{post_id}",
        posted_at=row["posted_at"] or "",
        author=row["author"] or "",
        base_score=row["base_score"],
        html_key=f"{normalize_prefix(prefix)}{html_path.relative_to(cache_dir).as_posix()}",
        text_preview=row["text_preview"] or preview_from_html_path(html_path, preview_words=preview_words),
        bytes=int(row["bytes"] or 0),
    )


def resolve_html_path(recorded_path: str | None, *, cache_dir: Path, verify_files: bool) -> Path | None:
    if not recorded_path:
        return None
    path = cache_dir / recorded_path
    if not verify_files or path.is_file():
        return path
    return None


def date_part(value: str) -> str:
    if not value:
        return ""
    try:
        return datetime.fromisoformat(value.replace("Z", "+00:00")).date().isoformat()
    except ValueError:
        return value[:10]


def normalize_prefix(prefix: str) -> str:
    stripped = prefix.strip("/")
    return f"{stripped}/" if stripped else ""


def has_column(conn: sqlite3.Connection, table: str, column: str) -> bool:
    return column in {row[1] for row in conn.execute(f"PRAGMA table_info({table})")}


def preview_from_html_path(html_path: Path, *, preview_words: int) -> str:
    try:
        html = html_path.read_text(encoding="utf-8")
    except OSError:
        return ""
    return first_words(extract_plaintext(html), preview_words)


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


def json_body(payload: dict[str, Any], *, pretty: bool) -> str:
    return json.dumps(payload, indent=2 if pretty else None, separators=None if pretty else (",", ":")) + "\n"


def write_index_files(
    output_dir: Path,
    manifest: dict[str, Any],
    date_shards: dict[str, dict[str, Any]],
    *,
    pretty: bool,
) -> None:
    output_dir.mkdir(parents=True, exist_ok=True)
    (output_dir / "posts-by-date.json").write_text(json_body(manifest, pretty=pretty), encoding="utf-8")
    dates_dir = output_dir / "dates"
    dates_dir.mkdir(parents=True, exist_ok=True)
    for day, shard in date_shards.items():
        (dates_dir / f"{day}.json").write_text(json_body(shard, pretty=pretty), encoding="utf-8")
    print(f"Wrote manifest and {len(date_shards)} date shards to {output_dir}")


def r2_client(args: argparse.Namespace):
    required = {
        "R2_ACCOUNT_ID": args.account_id,
        "R2_ACCESS_KEY_ID": args.access_key_id,
        "R2_SECRET_ACCESS_KEY": args.secret_access_key,
        "R2_BUCKET": args.bucket,
    }
    missing = [name for name, value in required.items() if not value]
    if missing:
        raise SystemExit(f"Missing required R2 settings: {', '.join(missing)}")
    return boto3.client(
        "s3",
        endpoint_url=f"https://{args.account_id}.r2.cloudflarestorage.com",
        aws_access_key_id=args.access_key_id,
        aws_secret_access_key=args.secret_access_key,
        config=Config(signature_version="s3v4"),
        region_name="auto",
    )


def print_summary(index: dict[str, Any]) -> None:
    dates = index["dates"]
    newest = next(iter(dates), None)
    print(
        f"Indexed {index['total_posts']} LessWrong posts across {len(dates)} dates; "
        f"newest={newest or 'none'}; skipped_missing={index['skipped_missing_files']}"
    )


if __name__ == "__main__":
    main()
