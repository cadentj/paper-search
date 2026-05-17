from pydantic_settings import BaseSettings


class Settings(BaseSettings):
    DATABASE_URL: str = "sqlite:///./data/paper_search.db"
    REDIS_URL: str = "redis://redis:6379/0"
    OPENROUTER_API_KEY: str = ""
    OPENROUTER_MODEL: str = "deepseek/deepseek-v4-flash"
    OPENROUTER_PROVIDER: str = "novita"
    APP_ENV: str = "development"
    ENABLE_DEV_RESET: bool = True
    RUN_LIVE_LLM_TESTS: bool = False

    @property
    def is_development(self) -> bool:
        return self.APP_ENV == "development" or self.ENABLE_DEV_RESET

    model_config = {"env_file": ".env", "extra": "ignore"}


settings = Settings()
