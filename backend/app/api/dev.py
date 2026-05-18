from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from app.core.config import settings
from app.db.session import get_db
from app.models.onboarding_extraction import OnboardingExtraction
from app.models.idea_map import IdeaMap
from app.models.paper_match import PaperMatch
from app.models.search_run import SearchRun
from app.models.search_run_paper import SearchRunPaper
from app.models.filter import Filter

router = APIRouter(prefix="/dev", tags=["dev"])


@router.post("/reset-onboarding")
def reset_onboarding(db: Session = Depends(get_db)):
    if not settings.is_development:
        raise HTTPException(status_code=403, detail="Dev reset is only available in development mode")

    counts = {}

    counts["onboarding_extractions"] = db.query(OnboardingExtraction).delete()
    counts["idea_maps"] = db.query(IdeaMap).delete()
    counts["paper_matches"] = db.query(PaperMatch).delete()
    counts["search_run_papers"] = db.query(SearchRunPaper).delete()
    counts["search_runs"] = db.query(SearchRun).delete()
    counts["filters"] = db.query(Filter).delete()

    db.commit()

    return {"status": "reset", "deleted": counts}
