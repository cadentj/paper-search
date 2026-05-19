"""Feedback reflection worker — process all pending feedback and propose filter changes."""

import asyncio
import json
import logging
import uuid
from datetime import datetime, timezone

from sqlalchemy.orm import Session

from app.models.filter import SQLAFilter
from app.services import filters as filter_service
from app.models.job import SQLAJob
from paper_search_core.models.paper import SQLAPaper
from app.models.paper_match import SQLAPaperMatch
from app.models.paper_match_feedback import SQLAPaperMatchFeedback
from app.models.paper_note import SQLAPaperNote
from app.services.jobs import set_job_status
from app.llm.client import async_call_llm
from app.llm.config import FILTER_GENERATION_PROFILE
from app.llm.prompts import (
    FEEDBACK_REFLECTION_SYSTEM_PROMPT,
    FEEDBACK_REFLECTION_USER_PROMPT,
)
from app.llm.schemas import (
    CreateFeedbackAction,
    DeleteFeedbackAction,
    FeedbackReflectionResponse,
    ReviseFeedbackAction,
)

logger = logging.getLogger(__name__)


def _build_reflection_prompt(
    db: Session,
    votes: list[SQLAPaperMatchFeedback],
    notes: list[SQLAPaperNote],
) -> str:
    active_filters = filter_service.list_filters(db, status="active")
    filter_summaries = []
    for f in active_filters:
        d = f.definition or {}
        filter_summaries.append(
            f"- [{f.id}] {f.name}: {d.get('description', '')} (mode: {d.get('mode', 'topic')})"
        )

    vote_descriptions = []
    for v in votes:
        paper = db.query(SQLAPaper).filter(SQLAPaper.id == v.paper_id).first()
        paper_title = paper.title if paper else "Unknown"
        paper_text = paper.search_text if paper else ""

        if v.paper_match_id and v.filter_id:
            match = (
                db.query(SQLAPaperMatch)
                .filter(SQLAPaperMatch.id == v.paper_match_id)
                .first()
            )
            match_filter = (
                db.query(SQLAFilter).filter(SQLAFilter.id == v.filter_id).first()
            )
            filter_name = match_filter.name if match_filter else "Unknown"
            match_result = ""
            if match and match.result:
                match_result = (
                    match.result
                    if isinstance(match.result, str)
                    else json.dumps(match.result)
                )
            vote_descriptions.append(
                f'- {v.value.upper()} on matched paper "{paper_title}" '
                f"(filter: {filter_name}, result: {match_result})"
            )
        else:
            vote_descriptions.append(
                f'- UP on unmatched paper "{paper_title}" '
                f"(paper text: {paper_text[:200]}...)"
            )

    note_descriptions = []
    for n in notes:
        paper = db.query(SQLAPaper).filter(SQLAPaper.id == n.paper_id).first()
        paper_title = paper.title if paper else "Unknown"
        paper_text = paper.search_text if paper else ""
        note_descriptions.append(
            f'- Note on "{paper_title}" (paper text: {paper_text[:200]}...): {n.text}'
        )

    return FEEDBACK_REFLECTION_USER_PROMPT.format(
        existing_filters="\n".join(filter_summaries) if filter_summaries else "(none)",
        vote_feedback="\n".join(vote_descriptions) if vote_descriptions else "(none)",
        note_feedback="\n".join(note_descriptions) if note_descriptions else "(none)",
    )


_PENDING_STATUS = {
    "create": "pending_create",
    "revise": "pending_revision",
    "delete": "pending_deletion",
}


def _create_draft_filter(
    db: Session,
    action: CreateFeedbackAction | ReviseFeedbackAction | DeleteFeedbackAction,
    now: datetime,
) -> None:
    target_filter_id: str | None = None

    match action:
        case DeleteFeedbackAction(target_filter_id=target_id):
            target = db.query(SQLAFilter).filter(SQLAFilter.id == target_id).first()
            if not target:
                return
            name = target.name
            definition = dict(target.definition or {})
            target_filter_id = target_id
        case CreateFeedbackAction(name=name, description=description, mode=mode):
            definition = {"name": name, "description": description, "mode": mode}
        case ReviseFeedbackAction(
            name=name,
            description=description,
            mode=mode,
            target_filter_id=target_id,
        ):
            definition = {"name": name, "description": description, "mode": mode}
            target_filter_id = target_id

    filter = SQLAFilter(
        id=str(uuid.uuid4()),
        name=name,
        definition=definition,
        status=_PENDING_STATUS[action.action],
        source="feedback",
        proposed_action=action.action,
        target_filter_id=target_filter_id,
        created_at=now,
        updated_at=now,
    )
    db.add(filter)


def run(db: Session, job: SQLAJob) -> None:
    try:
        set_job_status(job, status="running")
        db.commit()

        votes = (
            db.query(SQLAPaperMatchFeedback)
            .filter(SQLAPaperMatchFeedback.processed.is_(False))
            .all()
        )

        notes = (
            db.query(SQLAPaperNote)
            .filter(SQLAPaperNote.processed.is_(False), SQLAPaperNote.text != "")
            .all()
        )

        if not votes and not notes:
            set_job_status(job, status="completed")
            db.commit()
            return

        user_prompt = _build_reflection_prompt(db, votes, notes)

        result = asyncio.run(
            async_call_llm(
                system_prompt=FEEDBACK_REFLECTION_SYSTEM_PROMPT,
                user_prompt=user_prompt,
                response_model=FeedbackReflectionResponse,
                profile=FILTER_GENERATION_PROFILE,
            )
        )

        reflection = FeedbackReflectionResponse.model_validate(result["content"])
        now = datetime.now(timezone.utc)

        for action in reflection.actions:
            _create_draft_filter(db, action, now)

        for v in votes:
            v.processed = True
        for n in notes:
            n.processed = True

        set_job_status(job, status="completed")
        db.commit()

    except Exception as e:
        db.rollback()
        set_job_status(job, status="failed", error=str(e))
        db.commit()
        logger.exception("feedback processing failed job=%s", job.id)
