from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.api.health import router as health_router
from app.api.onboarding import router as onboarding_router
from app.api.filters import router as filters_router
from app.api.search import router as search_router
from app.api.papers import router as papers_router
from app.api.dev import router as dev_router
from app.models import Base
from app.db.session import engine


Base.metadata.create_all(bind=engine)

app = FastAPI(title="Paper Search API", version="0.1.0")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(health_router)
app.include_router(onboarding_router)
app.include_router(filters_router)
app.include_router(search_router)
app.include_router(papers_router)
app.include_router(dev_router)
