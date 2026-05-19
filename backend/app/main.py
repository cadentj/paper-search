import logging

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from sqlalchemy import func

from app.api.onboarding import router as onboarding_router
from app.api.filters import router as filters_router
from app.api.data_sources import router as data_sources_router
from app.api.documents import router as documents_router
from app.api.jobs import router as jobs_router
from app.api.search import router as search_router
from app.api.papers import router as papers_router
from app.api.feedback import router as feedback_router
from app.api.settings import router as settings_router
from app.api.jobs import DailySearchSummaryJob
from app.api.search import DailySearchSummary
from app.models import Base
from app.db.session import database, engine
from app.models.paper import SQLAPaper
from paper_search_core.daily_dates import DEFAULT_DAILY_SEARCH_DATE

logger = logging.getLogger(__name__)

DailySearchSummaryJob.model_rebuild(
    _types_namespace={"DailySearchSummary": DailySearchSummary}
)

Base.metadata.create_all(bind=engine)

with database.session() as db:
    if (
        db.query(SQLAPaper)
        .filter(func.date(SQLAPaper.published_at) == DEFAULT_DAILY_SEARCH_DATE)
        .count()
        == 0
    ):
        logger.warning(
            "No synced daily index for %s — run: uv run --directory scripts python sync.py",
            DEFAULT_DAILY_SEARCH_DATE,
        )

app = FastAPI(title="Paper Search API", version="0.1.0")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

@app.get("/health")
def health_check():
    return {"status": "ok"}

app.include_router(onboarding_router)
app.include_router(filters_router)
app.include_router(data_sources_router)
app.include_router(documents_router)
app.include_router(jobs_router)
app.include_router(search_router)
app.include_router(papers_router)
app.include_router(feedback_router)
app.include_router(settings_router)
