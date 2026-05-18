from pathlib import Path

from pydantic import field_validator
from pydantic_settings import BaseSettings

from paper_search_core.index_records import IndexSettings

REPO_ROOT = Path(__file__).resolve().parents[3]
BACKEND_DIR = REPO_ROOT / "backend"


class SyncSettings(BaseSettings):
    DATABASE_URL: str = "sqlite:///./data/paper_search.db"
    ARXIV_CATEGORIES: str = "cs.AI,cs.CL,cs.LG"
    ARXIV_HTML_PUBLIC_BASE_URL: str
    ARXIV_HTML_INDEX_PATH: str = "data/index/papers-by-date.json"
    ARXIV_PUBLIC_DAILY_LIMIT: int = 0
    LESSWRONG_EXCERPT_WORDS: int = 250
    LESSWRONG_HTML_PUBLIC_BASE_URL: str
    LESSWRONG_HTML_INDEX_PATH: str = "data/index/posts-by-date.json"

    model_config = {
        "env_file": (REPO_ROOT / ".env", BACKEND_DIR / ".env"),
        "extra": "ignore",
    }

    @field_validator("ARXIV_HTML_PUBLIC_BASE_URL", "LESSWRONG_HTML_PUBLIC_BASE_URL")
    @classmethod
    def _require_public_base_urls(cls, value: str) -> str:
        if not value.strip():
            raise ValueError("public base URL is required")
        return value.strip()

    def index_settings(self) -> IndexSettings:
        return IndexSettings(
            arxiv_html_public_base_url=self.ARXIV_HTML_PUBLIC_BASE_URL,
            lesswrong_html_public_base_url=self.LESSWRONG_HTML_PUBLIC_BASE_URL,
            arxiv_categories=self.ARXIV_CATEGORIES,
            lesswrong_excerpt_words=self.LESSWRONG_EXCERPT_WORDS,
        )


def resolve_sqlite_path(database_url: str) -> Path:
    prefix = "sqlite:///"
    if not database_url.startswith(prefix):
        raise ValueError(f"Only SQLite URLs are supported for sync, got: {database_url}")
    raw = database_url.removeprefix(prefix)
    path = Path(raw)
    if not path.is_absolute():
        path = BACKEND_DIR / path
    return path
