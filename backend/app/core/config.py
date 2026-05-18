from pathlib import Path

from pydantic import ValidationInfo, field_validator
from pydantic_settings import BaseSettings


BACKEND_DIR = Path(__file__).resolve().parents[2]
REPO_ROOT = BACKEND_DIR.parent
LLM_MAX_CONCURRENCY = 50
LLM_MAX_RETRIES = 3
LLM_RETRY_BASE_SECONDS = 1.5


class Settings(BaseSettings):
    DATABASE_URL: str = "sqlite:///./data/paper_search.db"
    REDIS_URL: str = "redis://localhost:6379/0"
    OPENROUTER_API_KEY: str = ""
    ARXIV_CATEGORIES: str = "cs.AI,cs.CL,cs.LG"
    ARXIV_HTML_PUBLIC_BASE_URL: str
    ARXIV_HTML_INDEX_PATH: str = "data/index/papers-by-date.json"
    ARXIV_PUBLIC_DAILY_LIMIT: int = 0
    LESSWRONG_EXCERPT_WORDS: int = 250
    LESSWRONG_HTML_PUBLIC_BASE_URL: str
    LESSWRONG_HTML_INDEX_PATH: str = "data/index/posts-by-date.json"
    DOCUMENT_STORAGE_DIR: str = "data/documents"
    DOCUMENT_MAX_SIZE_BYTES: int = 1_000_000
    DOCUMENT_MAX_PAGES: int = 10
    DOCUMENT_MIN_TEXT_CHARS: int = 200
    DOCUMENT_SUMMARY_MAX_CHARS: int = 20_000
    ONBOARDING_INPUT_MAX_CHARS: int = 2_000
    APP_ENV: str = "development"
    ENABLE_DEV_RESET: bool = True

    @property
    def is_development(self) -> bool:
        return self.APP_ENV == "development" or self.ENABLE_DEV_RESET

    @field_validator("ARXIV_HTML_PUBLIC_BASE_URL", "LESSWRONG_HTML_PUBLIC_BASE_URL")
    @classmethod
    def require_public_base_url(cls, value: str, info: ValidationInfo) -> str:
        value = value.strip()
        if not value:
            raise ValueError(f"{info.field_name} must be set")
        return value

    model_config = {
        "env_file": (REPO_ROOT / ".env", BACKEND_DIR / ".env"),
        "extra": "ignore",
    }


settings = Settings()
