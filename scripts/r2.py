"""Shared settings, public R2 fetch, and R2 upload helpers."""

from __future__ import annotations

import json
import mimetypes
from concurrent.futures import ThreadPoolExecutor, as_completed
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import boto3
import httpx
from botocore.config import Config
from botocore.exceptions import ClientError
from pydantic import field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict
from tqdm import tqdm

from paper_search_core.index_records import IndexSettings
from paper_search_core.r2_urls import public_url_for_base

REPO_ROOT = Path(__file__).resolve().parents[1]
BACKEND_DIR = REPO_ROOT / "backend"
_ENV_FILES = (REPO_ROOT / ".env", BACKEND_DIR / ".env")


class Settings(BaseSettings):
    DATABASE_URL: str = "sqlite:///./data/paper_search.db"
    ARXIV_CATEGORIES: str = "cs.AI,cs.CL,cs.LG"
    ARXIV_HTML_PUBLIC_BASE_URL: str = ""
    ARXIV_HTML_INDEX_PATH: str = "data/index/papers-by-date.json"
    ARXIV_PUBLIC_DAILY_LIMIT: int = 0
    LESSWRONG_EXCERPT_WORDS: int = 250
    LESSWRONG_HTML_PUBLIC_BASE_URL: str = ""
    LESSWRONG_HTML_INDEX_PATH: str = "data/index/posts-by-date.json"
    R2_ACCOUNT_ID: str = ""
    R2_ACCESS_KEY_ID: str = ""
    R2_SECRET_ACCESS_KEY: str = ""
    R2_BUCKET: str = ""
    ARXIV_HTML_PREFIX: str = "data/"
    LESSWRONG_HTML_PREFIX: str = "data/"
    ARXIV_DATE_INDEX_PREFIX: str = "data/index/dates/"
    LESSWRONG_DATE_INDEX_PREFIX: str = "data/index/dates/"
    ARXIV_CACHE_DIR: str = ""
    LESSWRONG_CACHE_DIR: str = ""
    LESSWRONG_COOKIE_FILE: str = ""
    LESSWRONG_PREVIEW_WORDS: int = 250

    model_config = SettingsConfigDict(env_file=_ENV_FILES, extra="ignore")

    @field_validator("ARXIV_HTML_PUBLIC_BASE_URL", "LESSWRONG_HTML_PUBLIC_BASE_URL")
    @classmethod
    def _strip_public_urls(cls, value: str) -> str:
        return value.strip()

    def index_settings(self) -> IndexSettings:
        return IndexSettings(
            arxiv_html_public_base_url=self.ARXIV_HTML_PUBLIC_BASE_URL,
            lesswrong_html_public_base_url=self.LESSWRONG_HTML_PUBLIC_BASE_URL,
            arxiv_categories=self.ARXIV_CATEGORIES,
            lesswrong_excerpt_words=self.LESSWRONG_EXCERPT_WORDS,
        )

    def require_sync_urls(self) -> None:
        if (
            not self.ARXIV_HTML_PUBLIC_BASE_URL
            or not self.LESSWRONG_HTML_PUBLIC_BASE_URL
        ):
            raise SystemExit(
                "ARXIV_HTML_PUBLIC_BASE_URL and LESSWRONG_HTML_PUBLIC_BASE_URL are required for sync"
            )

    def arxiv_cache_dir(self) -> Path:
        if self.ARXIV_CACHE_DIR.strip():
            return Path(self.ARXIV_CACHE_DIR).expanduser().resolve()
        return REPO_ROOT / "data" / "arxiv_html_cache"

    def lesswrong_cache_dir(self) -> Path:
        if self.LESSWRONG_CACHE_DIR.strip():
            return Path(self.LESSWRONG_CACHE_DIR).expanduser().resolve()
        return REPO_ROOT / "data" / "lesswrong_html_cache"

    def arxiv_html_cache_dir(self) -> Path:
        return self.arxiv_cache_dir() / "html"

    def lesswrong_html_cache_dir(self) -> Path:
        return self.lesswrong_cache_dir() / "html"

    def arxiv_category_set(self) -> set[str]:
        return {c.strip() for c in self.ARXIV_CATEGORIES.split(",") if c.strip()}

    def lesswrong_cookie(self) -> str:
        if not self.LESSWRONG_COOKIE_FILE.strip():
            return ""
        return (
            Path(self.LESSWRONG_COOKIE_FILE)
            .expanduser()
            .read_text(encoding="utf-8")
            .strip()
        )


def resolve_sqlite_path(database_url: str) -> Path:
    prefix = "sqlite:///"
    if not database_url.startswith(prefix):
        raise ValueError(
            f"Only SQLite URLs are supported for sync, got: {database_url}"
        )
    raw = database_url.removeprefix(prefix)
    path = Path(raw)
    if not path.is_absolute():
        path = BACKEND_DIR / path
    return path


def fetch_manifest(public_base_url: str, manifest_path: str) -> dict[str, Any]:
    url = public_url_for_base(public_base_url, manifest_path)
    response = httpx.get(url, timeout=30.0, follow_redirects=True)
    response.raise_for_status()
    return response.json()


def fetch_date_shard(public_base_url: str, index_key: str) -> dict[str, Any]:
    url = public_url_for_base(public_base_url, index_key)
    response = httpx.get(url, timeout=30.0, follow_redirects=True)
    response.raise_for_status()
    return response.json()


def items_for_date(
    public_base_url: str,
    run_date: str,
    date_payload: dict[str, Any],
    items_key: str,
) -> list[dict[str, Any]]:
    index_key = str(date_payload.get("index_key") or "")
    if not index_key:
        return []
    shard = fetch_date_shard(public_base_url=public_base_url, index_key=index_key)
    if str(shard.get("date") or run_date) != run_date:
        return []
    items = shard.get(items_key) or []
    return items if isinstance(items, list) else []


def r2_client(settings: Settings, max_pool_connections: int = 32):
    missing = [
        name
        for name, value in {
            "R2_ACCOUNT_ID": settings.R2_ACCOUNT_ID,
            "R2_ACCESS_KEY_ID": settings.R2_ACCESS_KEY_ID,
            "R2_SECRET_ACCESS_KEY": settings.R2_SECRET_ACCESS_KEY,
            "R2_BUCKET": settings.R2_BUCKET,
        }.items()
        if not value
    ]
    if missing:
        raise SystemExit(f"Missing required R2 settings: {', '.join(missing)}")

    return boto3.client(
        "s3",
        endpoint_url=f"https://{settings.R2_ACCOUNT_ID}.r2.cloudflarestorage.com",
        aws_access_key_id=settings.R2_ACCESS_KEY_ID,
        aws_secret_access_key=settings.R2_SECRET_ACCESS_KEY,
        config=Config(
            signature_version="s3v4",
            max_pool_connections=max(max_pool_connections, 1),
        ),
        region_name="auto",
    )


def normalize_prefix(prefix: str) -> str:
    stripped = prefix.strip("/")
    return f"{stripped}/" if stripped else ""


def date_index_key(date: str, date_index_prefix: str) -> str:
    return f"{normalize_prefix(date_index_prefix)}{date}.json"


def json_body(payload: dict[str, Any], pretty: bool = False) -> str:
    if pretty:
        return json.dumps(payload, indent=2, sort_keys=False) + "\n"
    return json.dumps(payload, separators=(",", ":"), sort_keys=False) + "\n"


def upload_sharded_index(
    client,
    bucket: str,
    index_key: str,
    manifest: dict[str, Any],
    date_shards: dict[str, dict[str, Any]],
    pretty: bool = False,
) -> None:
    client.put_object(
        Bucket=bucket,
        Key=index_key,
        Body=json_body(manifest, pretty=pretty).encode("utf-8"),
        ContentType="application/json",
        CacheControl="no-cache",
    )
    print(f"Uploaded s3://{bucket}/{index_key}")

    for day, shard in date_shards.items():
        key = manifest["dates"][day]["index_key"]
        client.put_object(
            Bucket=bucket,
            Key=key,
            Body=json_body(shard, pretty=pretty).encode("utf-8"),
            ContentType="application/json",
            CacheControl="public, max-age=31536000, immutable",
        )
    print(f"Uploaded {len(date_shards)} date shards")


@dataclass(frozen=True)
class UploadTask:
    path: Path
    key: str


@dataclass(frozen=True)
class UploadResult:
    status: str
    key: str
    error: str = ""


def upload_html(
    client,
    bucket: str,
    cache_dir: Path,
    prefix: str,
    workers: int = 16,
    skip_existing: bool = True,
    limit: int | None = None,
    content_type: str | None = None,
) -> None:
    if not cache_dir.exists():
        raise SystemExit(f"Cache dir not found: {cache_dir}")

    files = sorted(cache_dir.rglob("*.html"))
    if limit is not None:
        files = files[:limit]

    tasks = [
        UploadTask(
            path=path,
            key=f"{prefix.rstrip('/')}/{path.relative_to(cache_dir).as_posix()}",
        )
        for path in files
    ]

    stats = {"uploaded": 0, "skipped": 0, "error": 0}
    with (
        ThreadPoolExecutor(max_workers=max(workers, 1)) as executor,
        tqdm(
            total=len(tasks),
            desc="uploading",
            unit="file",
            dynamic_ncols=True,
        ) as progress,
    ):
        futures = [
            executor.submit(
                _upload_one,
                client,
                bucket=bucket,
                task=task,
                skip_existing=skip_existing,
                content_type=content_type,
            )
            for task in tasks
        ]
        _set_upload_progress(progress, stats)
        for future in as_completed(futures):
            result = future.result()
            stats[result.status] += 1
            if result.status == "error":
                tqdm.write(f"{result.key} error {result.error}")
            progress.update(1)
            _set_upload_progress(progress, stats)

    print(
        f"Uploaded {stats['uploaded']} files, skipped {stats['skipped']}, "
        f"errors {stats['error']}"
    )


def _upload_one(
    client,
    bucket: str,
    task: UploadTask,
    skip_existing: bool,
    content_type: str | None,
) -> UploadResult:
    try:
        if skip_existing and _object_exists(client, bucket, task.key):
            return UploadResult(status="skipped", key=task.key)
        resolved_type = (
            content_type or mimetypes.guess_type(task.path.name)[0] or "text/html"
        )
        client.upload_file(
            str(task.path),
            bucket,
            task.key,
            ExtraArgs={
                "ContentType": resolved_type,
                "CacheControl": "public, max-age=31536000, immutable",
            },
        )
    except Exception as exc:
        return UploadResult(status="error", key=task.key, error=str(exc))
    return UploadResult(status="uploaded", key=task.key)


def _object_exists(client, bucket: str, key: str) -> bool:
    try:
        client.head_object(Bucket=bucket, Key=key)
    except ClientError as exc:
        status_code = exc.response.get("ResponseMetadata", {}).get("HTTPStatusCode")
        error_code = exc.response.get("Error", {}).get("Code")
        if status_code in {403, 404} or error_code in {
            "403",
            "404",
            "NoSuchKey",
            "NotFound",
            "Forbidden",
            "AccessDenied",
        }:
            return False
        raise
    return True


def _set_upload_progress(progress: tqdm, stats: dict[str, int]) -> None:
    progress.set_postfix(
        uploaded=stats["uploaded"],
        skipped=stats["skipped"],
        error=stats["error"],
    )
