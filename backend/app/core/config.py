from pathlib import Path

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
    ARXIV_DAILY_LIMIT: int = 50
    ARXIV_CATEGORIES: str = "cs.AI,cs.CL,cs.LG,stat.ML"
    ARXIV_HTML_CACHE_DIR: str = str(REPO_ROOT / "data" / "arxiv_html_cache" / "html")
    ARXIV_HTML_STATE_DB: str = str(REPO_ROOT / "data" / "arxiv_html_cache" / "scrape_state.sqlite")
    APP_ENV: str = "development"
    ENABLE_DEV_RESET: bool = True

    @property
    def is_development(self) -> bool:
        return self.APP_ENV == "development" or self.ENABLE_DEV_RESET

    model_config = {
        "env_file": (REPO_ROOT / ".env", BACKEND_DIR / ".env"),
        "extra": "ignore",
    }


settings = Settings()
