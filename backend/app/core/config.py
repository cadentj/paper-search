from pathlib import Path

from pydantic_settings import BaseSettings


BACKEND_DIR = Path(__file__).resolve().parents[2]
REPO_ROOT = BACKEND_DIR.parent


class Settings(BaseSettings):
    DATABASE_URL: str = "sqlite:///./data/paper_search.db"
    REDIS_URL: str = "redis://localhost:6379/0"
    OPENROUTER_API_KEY: str = ""
    OPENROUTER_MODEL: str = "deepseek/deepseek-v4-flash"
    OPENROUTER_PROVIDER: str = "novita"
    LLM_MAX_CONCURRENCY: int = 4
    LLM_MAX_RETRIES: int = 3
    LLM_RETRY_BASE_SECONDS: float = 1.5
    ARXIV_DAILY_LIMIT: int = 50
    ARXIV_CATEGORIES: str = "cs.AI,cs.CL,cs.LG,stat.ML"
    APP_ENV: str = "development"
    ENABLE_DEV_RESET: bool = True
    RUN_LIVE_LLM_TESTS: bool = False

    @property
    def is_development(self) -> bool:
        return self.APP_ENV == "development" or self.ENABLE_DEV_RESET

    model_config = {
        "env_file": (REPO_ROOT / ".env", BACKEND_DIR / ".env"),
        "extra": "ignore",
    }


settings = Settings()
