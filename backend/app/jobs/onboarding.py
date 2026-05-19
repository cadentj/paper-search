"""Onboarding extraction worker job."""

import json
import uuid
from datetime import datetime, timezone

from app.db.session import database
from app.models.document import SQLADocument
from app.models.filter import SQLAFilter
from app.models.job import SQLAJob
from app.models.onboarding_extraction import SQLAOnboardingExtraction
from app.services.jobs import get_or_create_job_for_subject, set_job_status
from app.llm.client import stream_structured_response
from app.llm.config import FILTER_GENERATION_PROFILE
from app.llm.prompts import (
    ONBOARDING_SYSTEM_PROMPT,
    ONBOARDING_USER_PROMPT,
    ONBOARDING_WITH_DOCUMENTS_USER_PROMPT,
)
from app.llm.schemas import OnboardingFiltersResponse, StreamedFilter


def _normalize_filter(raw: dict) -> dict | None:
    try:
        item = StreamedFilter.model_validate(raw)
    except Exception:
        return None
    return item.model_dump()


def _extract_complete_filter_objects(buffer: str) -> list[dict]:
    decoder = json.JSONDecoder()
    marker = '"proposedFilters"'
    marker_idx = buffer.find(marker)
    if marker_idx == -1:
        return []

    array_start = buffer.find("[", marker_idx)
    if array_start == -1:
        return []

    idx = array_start + 1
    results: list[dict] = []
    while idx < len(buffer):
        while idx < len(buffer) and buffer[idx] in " \n\r\t,":
            idx += 1
        if idx >= len(buffer) or buffer[idx] == "]":
            break
        try:
            obj, next_idx = decoder.raw_decode(buffer, idx)
        except json.JSONDecodeError:
            break
        if isinstance(obj, dict):
            normalized = _normalize_filter(obj)
            if normalized:
                results.append(normalized)
        idx = next_idx

    return results


def _merge_filters(existing: list[dict], incoming: list[dict]) -> list[dict]:
    by_id = {f.get("id"): f for f in existing if f.get("id")}
    merged = list(existing)

    for item in incoming:
        item_id = item.get("id") or str(uuid.uuid4())
        item["id"] = item_id
        if item_id in by_id:
            continue
        by_id[item_id] = item
        merged.append(item)

    return merged


def _resolve_onboarding_job(db, extraction_id: str, job_id: str | None) -> SQLAJob:
    if job_id:
        job = db.query(SQLAJob).filter(SQLAJob.id == job_id).first()
        if job:
            return job
    return get_or_create_job_for_subject(
        db,
        kind="onboarding_extraction",
        subject_type="onboarding_extraction",
        subject_id=extraction_id,
    )


def _draft_filter_definition(raw: dict, job_id: str) -> dict:
    return {
        "name": raw.get("name", "Unnamed Filter"),
        "description": raw.get("description", ""),
        "mode": raw.get("mode", "topic"),
        "onboarding_generation_job_id": job_id,
    }


def _create_draft_filter(db, raw: dict, job_id: str) -> SQLAFilter:
    now = datetime.now(timezone.utc)
    definition = _draft_filter_definition(raw, job_id)
    filt = SQLAFilter(
        id=str(uuid.uuid4()),
        name=definition["name"],
        definition=definition,
        status="draft",
        source="onboarding",
        created_at=now,
        updated_at=now,
    )
    db.add(filt)
    return filt


def _document_summaries(db, document_ids: list[str]) -> list[str]:
    if not document_ids:
        return []
    documents = db.query(SQLADocument).filter(SQLADocument.id.in_(document_ids)).all()
    by_id = {document.id: document for document in documents}
    summaries: list[str] = []
    for document_id in document_ids:
        document = by_id.get(document_id)
        if not document or document.status != "ready" or not document.summary:
            continue
        summaries.append(
            f"SQLADocument: {document.original_filename}\nSummary: {document.summary}"
        )
    return summaries


def generate_onboarding_draft_filters(
    input_text: str,
    document_ids: list[str],
    job_id: str,
) -> None:
    """Worker job: generate draft filters from text and ready document summaries."""
    with database.session() as db:
        try:
            job = db.query(SQLAJob).filter(SQLAJob.id == job_id).first()
            if not job:
                return

            set_job_status(job, status="running")
            db.commit()

            summaries = _document_summaries(db, document_ids)
            user_prompt = ONBOARDING_WITH_DOCUMENTS_USER_PROMPT.format(
                input_text=input_text or "(No additional text provided.)",
                document_summaries="\n\n".join(summaries)
                if summaries
                else "(No ready document summaries selected.)",
            )
            text_buffer = ""
            last_count = 0
            created_llm_ids: set[str] = set()

            def create_new_filters(parsed_filters: list[dict]) -> None:
                nonlocal last_count
                new_items = []
                for raw in parsed_filters:
                    llm_id = raw.get("id") or str(uuid.uuid4())
                    raw["id"] = llm_id
                    if llm_id in created_llm_ids:
                        continue
                    created_llm_ids.add(llm_id)
                    new_items.append(raw)
                if not new_items:
                    return

                for raw in new_items:
                    _create_draft_filter(db, raw, job_id)
                db.commit()
                last_count = len(parsed_filters)

            def handle_delta(delta: str) -> None:
                nonlocal text_buffer
                text_buffer += delta
                parsed_filters = _extract_complete_filter_objects(text_buffer)
                if len(parsed_filters) <= last_count:
                    return
                create_new_filters(parsed_filters)

            result = stream_structured_response(
                system_prompt=ONBOARDING_SYSTEM_PROMPT,
                user_prompt=user_prompt,
                response_model=OnboardingFiltersResponse,
                on_text_delta=handle_delta,
                profile=FILTER_GENERATION_PROFILE,
            )

            proposed = result["content"].get("proposedFilters", [])
            create_new_filters([_normalize_filter(f) or f for f in proposed])

            set_job_status(job, status="completed")
            db.commit()
        except Exception as e:
            db.rollback()
            job = db.query(SQLAJob).filter(SQLAJob.id == job_id).first()
            if job:
                set_job_status(job, status="failed", error=str(e))
                db.commit()
            raise


def extract_onboarding_filters(extraction_id: str, job_id: str | None = None) -> None:
    """Worker job: extract proposed filters from onboarding text."""
    with database.session() as db:
        try:
            extraction = (
                db.query(SQLAOnboardingExtraction)
                .filter(SQLAOnboardingExtraction.id == extraction_id)
                .first()
            )
            if not extraction:
                return

            job = _resolve_onboarding_job(db, extraction_id, job_id)
            now = datetime.now(timezone.utc)
            extraction.status = "running"
            extraction.updated_at = now
            set_job_status(job, status="running")
            db.commit()

            user_prompt = ONBOARDING_USER_PROMPT.format(
                input_text=extraction.input_text
            )
            text_buffer = ""
            last_count = 0

            def handle_delta(delta: str) -> None:
                nonlocal text_buffer, last_count
                text_buffer += delta
                parsed_filters = _extract_complete_filter_objects(text_buffer)
                if len(parsed_filters) <= last_count:
                    return

                current = list(extraction.proposed_filters or [])
                extraction.proposed_filters = _merge_filters(current, parsed_filters)
                extraction.updated_at = datetime.now(timezone.utc)
                last_count = len(parsed_filters)
                db.commit()

            result = stream_structured_response(
                system_prompt=ONBOARDING_SYSTEM_PROMPT,
                user_prompt=user_prompt,
                response_model=OnboardingFiltersResponse,
                on_text_delta=handle_delta,
                profile=FILTER_GENERATION_PROFILE,
            )

            content = result["content"]
            proposed = content.get("proposedFilters", [])

            for f in proposed:
                if "id" not in f:
                    f["id"] = str(uuid.uuid4())

            extraction.proposed_filters = _merge_filters(
                list(extraction.proposed_filters or []),
                [_normalize_filter(f) or f for f in proposed],
            )
            extraction.llm_model = result["model"]
            extraction.llm_response_id = result["response_id"]
            extraction.status = "completed"
            extraction.completed_at = datetime.now(timezone.utc)
            extraction.updated_at = datetime.now(timezone.utc)
            job.completed_at = extraction.completed_at
            set_job_status(job, status="completed")
            db.commit()

        except Exception as e:
            db.rollback()
            extraction = (
                db.query(SQLAOnboardingExtraction)
                .filter(SQLAOnboardingExtraction.id == extraction_id)
                .first()
            )
            if extraction:
                now = datetime.now(timezone.utc)
                extraction.status = "failed"
                extraction.error = str(e)
                extraction.updated_at = now
                job = _resolve_onboarding_job(db, extraction_id, job_id)
                set_job_status(job, status="failed", error=extraction.error)
                db.commit()
            raise
