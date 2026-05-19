"""Feedback reflection worker job — revise a filter based on match feedback."""

import json
import logging
from datetime import datetime, timezone

from app.db.session import SessionLocal
from app.models.filter import Filter
from app.models.job import Job
from app.models.paper import Paper
from app.models.paper_match import PaperMatch
from app.models.paper_match_feedback import PaperMatchFeedback
from app.services.jobs import set_job_status
from app.llm.client import call_llm
from app.llm.config import FILTER_GENERATION_PROFILE
from app.llm.prompts import FEEDBACK_REFLECTION_SYSTEM_PROMPT, FEEDBACK_REFLECTION_USER_PROMPT
from app.llm.schemas import FeedbackReflectionResponse

logger = logging.getLogger(__name__)


def reflect_on_feedback(feedback_id: str, job_id: str) -> None:
    db = SessionLocal()
    try:
        job = db.query(Job).filter(Job.id == job_id).first()
        if not job:
            return
        set_job_status(job, status="running")
        db.commit()

        feedback = db.query(PaperMatchFeedback).filter(PaperMatchFeedback.id == feedback_id).first()
        if not feedback:
            set_job_status(job, status="failed", error="Feedback not found")
            db.commit()
            return

        match = db.query(PaperMatch).filter(PaperMatch.id == feedback.paper_match_id).first()
        if not match:
            set_job_status(job, status="failed", error="Match not found")
            db.commit()
            return

        parent_filter = db.query(Filter).filter(Filter.id == feedback.filter_id).first()
        paper = db.query(Paper).filter(Paper.id == feedback.paper_id).first()

        if not parent_filter or not paper:
            set_job_status(job, status="failed", error="Filter or paper not found")
            db.commit()
            return

        parent_def = parent_filter.definition or {}
        match_result = match.result if isinstance(match.result, str) else json.dumps(match.result or {})

        user_prompt = FEEDBACK_REFLECTION_USER_PROMPT.format(
            parent_filter_name=parent_def.get("name", parent_filter.name),
            parent_filter_description=parent_def.get("description", ""),
            parent_filter_mode=parent_def.get("mode", "topic"),
            paper_title=paper.title or "Unknown",
            paper_abstract=paper.abstract or "(no abstract)",
            match_result=match_result,
            feedback_value="thumbs up (more like this)" if feedback.value == "up" else "thumbs down (less like this)",
        )

        result = call_llm(
            system_prompt=FEEDBACK_REFLECTION_SYSTEM_PROMPT,
            user_prompt=user_prompt,
            response_model=FeedbackReflectionResponse,
            profile=FILTER_GENERATION_PROFILE,
        )

        revised_description = result["content"].get("revised_description", "")
        if revised_description:
            new_def = dict(parent_def)
            new_def["description"] = revised_description
            parent_filter.definition = new_def
            parent_filter.updated_at = datetime.now(timezone.utc)

        set_job_status(job, status="completed")
        db.commit()

    except Exception as e:
        db.rollback()
        job = db.query(Job).filter(Job.id == job_id).first()
        if job:
            set_job_status(job, status="failed", error=str(e))
            db.commit()
        logger.exception("feedback_reflection feedback=%s failed", feedback_id)
    finally:
        db.close()
