import logging

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.api.onboarding import router as onboarding_router
from app.api.filters import router as filters_router
from app.api.data_sources import router as data_sources_router
from app.api.documents import router as documents_router
from app.api.jobs import router as jobs_router
from app.api.search import router as search_router
from app.api.papers import router as papers_router
from app.api.dev import router as dev_router
from app.models import Base
from app.db.session import SessionLocal, engine
from app.models.source_daily import SourceDailyRollup
from app.services.daily_dates import DEFAULT_DAILY_SEARCH_DATE


logger = logging.getLogger(__name__)

Base.metadata.create_all(bind=engine)

_db = SessionLocal()
try:
    if (
        _db.query(SourceDailyRollup)
        .filter(SourceDailyRollup.run_date == DEFAULT_DAILY_SEARCH_DATE)
        .count()
        == 0
    ):
        logger.warning(
            "No synced daily index for %s — run: cd backend && uv run python ../scripts/sync_public_index.py",
            DEFAULT_DAILY_SEARCH_DATE,
        )
finally:
    _db.close()

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
app.include_router(dev_router)
