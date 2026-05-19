"""Feedback reflection worker — process all pending feedback and propose filter changes."""

import json
import logging
import uuid
from datetime import datetime, timezone

from app.db.session import database
from app.models.filter import SQLAFilter
from app.services import filters as filter_service
from app.models.job import SQLAJob
from paper_search_core.models.paper import SQLAPaper
from app.models.paper_match import SQLAPaperMatch
from app.models.paper_match_feedback import SQLAPaperMatchFeedback
from app.models.paper_note import SQLAPaperNote
from app.services.jobs import set_job_status
from app.llm.client import call_llm
from app.llm.config import FILTER_GENERATION_PROFILE
from app.llm.prompts import (
    FEEDBACK_REFLECTION_SYSTEM_PROMPT,
    FEEDBACK_REFLECTION_USER_PROMPT,
)
from app.llm.schemas import FeedbackReflectionResponse

logger = logging.getLogger(__name__)


def process_all_feedback(job_id: str) -> None:
    with database.session() as db:
        try:
            job = db.query(SQLAJob).filter(SQLAJob.id == job_id).first()
            if not job:
                return
            set_job_status(job, status="running")
            db.commit()

            # Gather pending votes
            votes = (
                db.query(SQLAPaperMatchFeedback)
                .filter(SQLAPaperMatchFeedback.processed == False)
                .all()
            )

            # Gather pending notes
            notes = (
                db.query(SQLAPaperNote)
                .filter(SQLAPaperNote.processed == False, SQLAPaperNote.text != "")
                .all()
            )

            if not votes and not notes:
                set_job_status(job, status="completed")
                db.commit()
                return

            # Build context for the LLM
            active_filters = filter_service.list_active_filters(db)
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
                paper_abstract = paper.abstract if paper else ""

                if v.paper_match_id and v.filter_id:
                    match = (
                        db.query(SQLAPaperMatch)
                        .filter(SQLAPaperMatch.id == v.paper_match_id)
                        .first()
                    )
                    match_filter = (
                        db.query(SQLAFilter)
                        .filter(SQLAFilter.id == v.filter_id)
                        .first()
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
                        f"(abstract: {paper_abstract[:200]}...)"
                    )

            note_descriptions = []
            for n in notes:
                paper = db.query(SQLAPaper).filter(SQLAPaper.id == n.paper_id).first()
                paper_title = paper.title if paper else "Unknown"
                paper_abstract = paper.abstract if paper else ""
                note_descriptions.append(
                    f'- Note on "{paper_title}" (abstract: {paper_abstract[:200]}...): {n.text}'
                )

            user_prompt = FEEDBACK_REFLECTION_USER_PROMPT.format(
                existing_filters="\n".join(filter_summaries)
                if filter_summaries
                else "(none)",
                vote_feedback="\n".join(vote_descriptions)
                if vote_descriptions
                else "(none)",
                note_feedback="\n".join(note_descriptions)
                if note_descriptions
                else "(none)",
            )

            result = call_llm(
                system_prompt=FEEDBACK_REFLECTION_SYSTEM_PROMPT,
                user_prompt=user_prompt,
                response_model=FeedbackReflectionResponse,
                profile=FILTER_GENERATION_PROFILE,
            )

            actions = result["content"].get("actions", [])
            now = datetime.now(timezone.utc)

            for action in actions:
                action_type = action.get("action")
                if action_type == "create":
                    filt = SQLAFilter(
                        id=str(uuid.uuid4()),
                        name=action.get("name", "New Filter"),
                        definition={
                            "name": action.get("name", "New Filter"),
                            "description": action.get("description", ""),
                            "mode": action.get("mode", "topic"),
                        },
                        status="pending_create",
                        source="feedback",
                        proposed_action="create",
                        created_at=now,
                        updated_at=now,
                    )
                    db.add(filt)

                elif action_type == "revise":
                    target_id = action.get("target_filter_id")
                    if not target_id:
                        continue
                    filt = SQLAFilter(
                        id=str(uuid.uuid4()),
                        name=action.get("name", "Revised Filter"),
                        definition={
                            "name": action.get("name", "Revised Filter"),
                            "description": action.get("description", ""),
                            "mode": action.get("mode", "topic"),
                        },
                        status="pending_revision",
                        source="feedback",
                        proposed_action="revise",
                        target_filter_id=target_id,
                        created_at=now,
                        updated_at=now,
                    )
                    db.add(filt)

                elif action_type == "delete":
                    target_id = action.get("target_filter_id")
                    if not target_id:
                        continue
                    target = (
                        db.query(SQLAFilter).filter(SQLAFilter.id == target_id).first()
                    )
                    if not target:
                        continue
                    filt = SQLAFilter(
                        id=str(uuid.uuid4()),
                        name=target.name,
                        definition=dict(target.definition or {}),
                        status="pending_deletion",
                        source="feedback",
                        proposed_action="delete",
                        target_filter_id=target_id,
                        created_at=now,
                        updated_at=now,
                    )
                    db.add(filt)

            # Mark all feedback as processed
            for v in votes:
                v.processed = True
            for n in notes:
                n.processed = True

            set_job_status(job, status="completed")
            db.commit()

        except Exception as e:
            db.rollback()
            job = db.query(SQLAJob).filter(SQLAJob.id == job_id).first()
            if job:
                set_job_status(job, status="failed", error=str(e))
                db.commit()
            logger.exception("feedback processing failed job=%s", job_id)
