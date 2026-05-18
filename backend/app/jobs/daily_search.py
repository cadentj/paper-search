"""Daily search worker job."""

import asyncio
import logging
import uuid
from dataclasses import dataclass
from datetime import datetime, timezone

from app.core.config import LLM_MAX_CONCURRENCY
from app.db.session import SessionLocal
from app.models.filter import Filter
from app.models.paper import Paper
from app.models.paper_match import PaperMatch
from app.models.search_run import SearchRun
from app.models.search_run_paper import SearchRunPaper
from app.models.job import Job
from app.services.jobs import build_progress, get_or_create_job_for_subject
from app.services.source_providers import CandidateItem, candidates_for_sources
from app.services.source_settings import enabled_source_types
from app.llm.client import async_call_llm, call_llm
from app.llm.config import JUDGE_PROFILE, SUMMARY_PROFILE
from app.llm.prompts import (
    FILTER_SEARCH_SYSTEM_PROMPT,
    FILTER_SEARCH_USER_PROMPT,
    SUMMARY_SYSTEM_PROMPT,
    SUMMARY_USER_PROMPT,
)
from app.llm.schemas import (
    FilterSearchResponse,
    SearchSummaryResponse,
)
from tqdm import tqdm

logger = logging.getLogger(__name__)
PAIR_TIMEOUT_SECONDS = 30.0
PAIRING_PHASE_TIMEOUT_SECONDS = 180.0


@dataclass
class FilterPayload:
    id: str
    name: str
    definition: dict


@dataclass
class PaperPayload:
    id: str
    title: str
    source_type: str
    source_id: str
    item_id: str
    text: str
    authors: list[str]


@dataclass
class PairEvaluation:
    filter_id: str
    filter_name: str
    paper_id: str
    paper_title: str
    source_type: str
    source_id: str
    item_id: str
    result: dict | None = None
    model: str | None = None
    response_id: str | None = None
    error: str | None = None


def _build_papers_text(papers: list[Paper | PaperPayload]) -> str:
    lines = []
    for p in papers:
        source_type = getattr(p, "source_type", "arxiv") or "arxiv"
        source_id = getattr(p, "source_id", None) or getattr(p, "arxiv_id", "") or ""
        item_id = getattr(p, "item_id", f"{source_type}:{source_id}")
        text = getattr(p, "text", None) or getattr(p, "abstract", "")
        lines.append(
            f"Item ID: {item_id}\n"
            f"Source Type: {source_type}\n"
            f"Source ID: {source_id}\n"
            f"Title: {p.title}\n"
            f"Authors: {', '.join(p.authors) if p.authors else 'Unknown'}\n"
            f"Excerpt: {text}\n"
        )
    return "\n---\n".join(lines)


def _build_paper_text(paper: Paper | PaperPayload) -> str:
    return _build_papers_text([paper])


def _build_matches_text(matches: list[dict]) -> str:
    lines = []
    for m in matches:
        lines.append(
            f"Item: {m.get('paper_title', 'Unknown')} ({m.get('item_id', '')})\n"
            f"Source: {m.get('source_type', '')} {m.get('source_id', '')}\n"
            f"Filter: {m.get('filter_name', 'Unknown')}\n"
            f"Stance: {m.get('stance', '')}\n"
            f"Score: {m.get('relevance_score', 0)}\n"
            f"Rationale: {m.get('rationale', '')}\n"
            f"Match ID: {m.get('match_id', '')}\n"
        )
    return "\n---\n".join(lines)


def _append_progress_log(job: Job, stage: str, message: str) -> None:
    progress = job.progress or {}
    job.progress = build_progress(
        stage=progress.get("stage", stage),
        current=progress.get("current", 0),
        total=progress.get("total", 1),
        message=progress.get("message", message),
        log=progress.get("log", []),
        append_log=True,
    )


def _set_progress(
    db,
    run: SearchRun,
    job: Job,
    *,
    stage: str,
    current: int,
    total: int,
    message: str,
    status: str | None = None,
) -> None:
    logger.info("daily_search run=%s stage=%s %s", run.id, stage, message)
    now = datetime.now(timezone.utc)
    if status:
        run.status = status
        job.status = status
        if status == "running" and not job.started_at:
            job.started_at = now
        if status in {"completed", "failed", "skipped"}:
            job.completed_at = now
    job.updated_at = now
    job.progress = build_progress(
        stage=stage,
        current=current,
        total=total,
        message=message,
        log=(job.progress or {}).get("log", []),
    )
    db.commit()


def _resolve_daily_search_job(db, search_run_id: str, job_id: str | None) -> Job:
    if job_id:
        job = db.query(Job).filter(Job.id == job_id).first()
        if job:
            return job
    return get_or_create_job_for_subject(
        db,
        kind="daily_search",
        subject_type="search_run",
        subject_id=search_run_id,
    )


def _set_pair_progress(
    progress: tqdm,
    *,
    completed: int,
    matched: int,
    irrelevant: int,
    failed: int,
) -> None:
    progress.set_postfix(
        done=completed,
        matched=matched,
        irrelevant=irrelevant,
        failed=failed,
    )


def _upsert_candidate_papers(db, run: SearchRun, job: Job | None = None) -> list[Paper]:
    now = datetime.now(timezone.utc)
    active_sources = enabled_source_types(db)
    fetch_result = candidates_for_sources(active_sources, run.run_date)
    if job:
        for error in fetch_result.errors:
            _append_progress_log(job, "fetching_items", error)
    if active_sources and fetch_result.errors and not fetch_result.items:
        raise RuntimeError("; ".join(fetch_result.errors))
    daily_items = fetch_result.items
    candidate_paper_ids = set()
    papers: list[Paper] = []
    counts: dict[str, int] = {}

    db.query(SearchRunPaper).filter(SearchRunPaper.search_run_id == run.id).delete()

    for item in daily_items:
        source_type = item.source_type
        source_id = item.source_id
        existing = db.query(Paper).filter(
            Paper.source_type == source_type,
            Paper.source_id == source_id,
        ).first()
        if not existing and source_type == "arxiv":
            existing = db.query(Paper).filter(Paper.arxiv_id == item.arxiv_id).first()
        if existing:
            existing.source_type = source_type
            existing.source_id = source_id
            existing.title = item.title
            existing.abstract = _stored_abstract(item)
            existing.authors = item.authors
            existing.categories = item.categories
            existing.published_at = item.published_at
            existing.html_url = item.html_url
            existing.landing_url = item.landing_url
            existing.source_url = item.source_url or item.landing_url
            existing.source_metadata = item.metadata
            existing.updated_at = now
            paper = existing
        else:
            paper = Paper(
                id=str(uuid.uuid4()),
                arxiv_id=item.arxiv_id if source_type == "arxiv" else None,
                source_type=source_type,
                source_id=source_id,
                title=item.title,
                abstract=_stored_abstract(item),
                authors=item.authors,
                categories=item.categories,
                published_at=item.published_at,
                html_url=item.html_url,
                landing_url=item.landing_url,
                source_url=item.source_url or item.landing_url,
                source_metadata=item.metadata,
                created_at=now,
                updated_at=now,
            )
            db.add(paper)

        setattr(paper, "_transient_text", item.display_text or paper.abstract)

        if paper.id in candidate_paper_ids:
            continue
        candidate_paper_ids.add(paper.id)
        counts[source_type] = counts.get(source_type, 0) + 1
        papers.append(paper)
        db.add(
            SearchRunPaper(
                search_run_id=run.id,
                paper_id=paper.id,
                created_at=now,
            )
        )

    run.candidate_count = len(candidate_paper_ids)
    run.candidate_counts = counts
    db.commit()
    return papers


def _build_filter_payloads(filters: list[Filter]) -> list[FilterPayload]:
    return [
        FilterPayload(
            id=filt.id,
            name=filt.name,
            definition=dict(filt.definition or {}),
        )
        for filt in filters
    ]


def _stored_abstract(item: CandidateItem) -> str:
    if item.source_type == "lesswrong":
        return "LessWrong post content is fetched on demand."
    return item.display_text or ""


def _build_paper_payloads(papers: list[Paper]) -> list[PaperPayload]:
    return [
        PaperPayload(
            id=paper.id,
            title=paper.title,
            source_type=paper.source_type or "arxiv",
            source_id=paper.source_id or paper.arxiv_id or "",
            item_id=_item_id(paper.source_type or "arxiv", paper.source_id or paper.arxiv_id or ""),
            text=getattr(paper, "_transient_text", None) or paper.abstract,
            authors=list(paper.authors or []),
        )
        for paper in papers
    ]


def _filter_behavior(mode: str) -> str:
    if mode == "claim":
        return "Look for evidence that supports, refutes, or complicates the described claim."
    if mode == "question":
        return "Look for items that answer or partially answer the described question."
    return "Look for items relevant to the described topic."


def _item_id(source_type: str, source_id: str) -> str:
    return f"{source_type}:{source_id}"


async def _evaluate_filter_paper(
    *,
    semaphore: asyncio.Semaphore,
    filt: FilterPayload,
    paper: PaperPayload,
) -> PairEvaluation:
    definition = filt.definition or {}

    user_prompt = FILTER_SEARCH_USER_PROMPT.format(
        filter_name=definition.get("name", filt.name),
        filter_description=definition.get("description", ""),
        filter_behavior=_filter_behavior(definition.get("mode", "topic")),
        papers_text=_build_paper_text(paper),
    )
    async with semaphore:
        try:
            llm_result = await async_call_llm(
                system_prompt=FILTER_SEARCH_SYSTEM_PROMPT,
                user_prompt=user_prompt,
                response_model=FilterSearchResponse,
                profile=JUDGE_PROFILE,
            )
        except Exception as exc:
            return PairEvaluation(
                filter_id=filt.id,
                filter_name=filt.name,
                paper_id=paper.id,
                paper_title=paper.title,
                source_type=paper.source_type or "arxiv",
                source_id=paper.source_id or "",
                item_id=paper.item_id,
                error=str(exc),
            )

    matches = llm_result["content"].get("matches", [])
    match = next(
        (m for m in matches if m.get("itemId") == paper.item_id),
        matches[0] if matches else None,
    )

    return PairEvaluation(
        filter_id=filt.id,
        filter_name=filt.name,
        paper_id=paper.id,
        paper_title=paper.title,
        source_type=paper.source_type,
        source_id=paper.source_id,
        item_id=paper.item_id,
        result=match,
        model=llm_result["model"],
        response_id=llm_result["response_id"],
    )


async def _evaluate_filter_paper_with_timeout(
    *,
    semaphore: asyncio.Semaphore,
    filt: FilterPayload,
    paper: PaperPayload,
) -> PairEvaluation:
    try:
        return await asyncio.wait_for(
            _evaluate_filter_paper(semaphore=semaphore, filt=filt, paper=paper),
            timeout=PAIR_TIMEOUT_SECONDS,
        )
    except asyncio.TimeoutError:
        return PairEvaluation(
            filter_id=filt.id,
            filter_name=filt.name,
            paper_id=paper.id,
            paper_title=paper.title,
            source_type=paper.source_type,
            source_id=paper.source_id,
            item_id=paper.item_id,
            error=f"Timed out after {PAIR_TIMEOUT_SECONDS:g}s",
        )


async def _evaluate_pairs(
    *,
    filters: list[FilterPayload],
    papers: list[PaperPayload],
    on_result,
) -> None:
    semaphore = asyncio.Semaphore(max(LLM_MAX_CONCURRENCY, 1))
    task_pairs = {}
    for filt in filters:
        for paper in papers:
            task = asyncio.create_task(
                _evaluate_filter_paper_with_timeout(
                    semaphore=semaphore,
                    filt=filt,
                    paper=paper,
                )
            )
            task_pairs[task] = (filt, paper)

    pending = set(task_pairs)
    loop = asyncio.get_running_loop()
    deadline = loop.time() + PAIRING_PHASE_TIMEOUT_SECONDS

    while pending:
        remaining = max(deadline - loop.time(), 0)
        if remaining <= 0:
            break
        done, pending = await asyncio.wait(
            pending,
            timeout=remaining,
            return_when=asyncio.FIRST_COMPLETED,
        )
        if not done:
            break
        for task in done:
            await on_result(await task)

    if pending:
        for task in pending:
            task.cancel()
        await asyncio.gather(*pending, return_exceptions=True)
        for task in pending:
            filt, paper = task_pairs[task]
            await on_result(
                PairEvaluation(
                    filter_id=filt.id,
                    filter_name=filt.name,
                    paper_id=paper.id,
                    paper_title=paper.title,
                    source_type=paper.source_type,
                    source_id=paper.source_id,
                    item_id=paper.item_id,
                    error=f"Pairing phase timed out after {PAIRING_PHASE_TIMEOUT_SECONDS:g}s",
                )
            )


def run_daily_search(search_run_id: str, job_id: str | None = None) -> None:
    """Worker job: run daily search across all active filters."""
    db = SessionLocal()
    try:
        run = db.query(SearchRun).filter(SearchRun.id == search_run_id).first()
        if not run:
            return
        job = _resolve_daily_search_job(db, search_run_id, job_id)
        job.started_at = datetime.now(timezone.utc)

        run.started_at = datetime.now(timezone.utc)
        _set_progress(
            db,
            run,
            job,
            stage="fetching_items",
            current=0,
            total=1,
            message=f"Selecting items for {run.run_date.isoformat()}",
            status="running",
        )

        papers = _upsert_candidate_papers(db, run, job)
        _set_progress(
            db,
            run,
            job,
            stage="fetching_items",
            current=1,
            total=1,
            message=f"Selected {len(papers)} items",
            status="running",
        )

        active_filters = db.query(Filter).filter(Filter.status == "active").all()
        filter_payloads = _build_filter_payloads(active_filters)
        paper_payloads = _build_paper_payloads(papers)
        pair_total = len(filter_payloads) * len(paper_payloads)

        if not filter_payloads or not paper_payloads:
            run.candidate_count = len(papers)
            run.match_count = 0
            run.summary = (
                "No active filters to search."
                if papers
                else "No items were available for this daily search."
            )
            run.completed_at = datetime.now(timezone.utc)
            _set_progress(
                db,
                run,
                job,
                stage="completed",
                current=max(pair_total, 1),
                total=max(pair_total, 1),
                message=run.summary,
                status="completed",
            )
            return

        all_match_info = []
        completed_pairs = 0
        failed_pairs = 0
        matched_pairs = 0
        irrelevant_pairs = 0
        first_pair_error = ""

        _set_progress(
            db,
            run,
            job,
            stage="matching_filters",
            current=0,
            total=pair_total,
            message=f"Evaluating 0/{pair_total} filter-item pairs",
            status="running",
        )

        async def handle_pair_result(evaluation: PairEvaluation) -> None:
            nonlocal completed_pairs, failed_pairs, matched_pairs
            nonlocal irrelevant_pairs, first_pair_error
            completed_pairs += 1

            if evaluation.error:
                failed_pairs += 1
                if not first_pair_error:
                    first_pair_error = evaluation.error
                message = (
                    f"Pair {completed_pairs}/{pair_total} failed: "
                    f"{evaluation.filter_name} x {evaluation.item_id}: "
                    f"{evaluation.error}"
                )
                _append_progress_log(job, "matching_filters", message)
                tqdm.write(message)
            else:
                match_data = evaluation.result or {}
                stance = match_data.get("stance", "irrelevant")
                if stance != "irrelevant":
                    matched_pairs += 1
                    match = PaperMatch(
                        id=str(uuid.uuid4()),
                        search_run_id=search_run_id,
                        filter_id=evaluation.filter_id,
                        paper_id=evaluation.paper_id,
                        stance=stance,
                        relevance_score=match_data.get("relevanceScore", 0.0),
                        confidence=match_data.get("confidence"),
                        rationale=match_data.get("rationale", ""),
                        matched_claims=match_data.get("matchedClaims", []),
                        abstract_evidence=match_data.get("abstractEvidence", []),
                        llm_model=evaluation.model,
                        llm_response_id=evaluation.response_id,
                    )
                    db.add(match)
                    all_match_info.append({
                        "match_id": match.id,
                        "paper_title": evaluation.paper_title,
                        "item_id": evaluation.item_id,
                        "source_type": evaluation.source_type,
                        "source_id": evaluation.source_id,
                        "filter_name": evaluation.filter_name,
                        "stance": match.stance,
                        "relevance_score": match.relevance_score,
                        "rationale": match.rationale,
                    })
                else:
                    irrelevant_pairs += 1

            job.progress = build_progress(
                stage="matching_filters",
                current=completed_pairs,
                total=pair_total,
                message=f"Evaluated {completed_pairs}/{pair_total} filter-item pairs",
                log=(job.progress or {}).get("log", []),
                append_log=False,
            )
            db.commit()
            pair_progress.update(1)
            _set_pair_progress(
                pair_progress,
                completed=completed_pairs,
                matched=matched_pairs,
                irrelevant=irrelevant_pairs,
                failed=failed_pairs,
            )

        with tqdm(
            total=pair_total,
            desc="filter-item pairs",
            unit="pair",
            dynamic_ncols=True,
            disable=None,
        ) as pair_progress:
            _set_pair_progress(
                pair_progress,
                completed=completed_pairs,
                matched=matched_pairs,
                irrelevant=irrelevant_pairs,
                failed=failed_pairs,
            )
            asyncio.run(
                _evaluate_pairs(
                    filters=filter_payloads,
                    papers=paper_payloads,
                    on_result=handle_pair_result,
                )
            )

        if failed_pairs == pair_total:
            raise RuntimeError(
                f"All {pair_total} filter-item evaluations failed. First error: {first_pair_error}"
            )

        match_count = len(all_match_info)
        _set_progress(
            db,
            run,
            job,
            stage="summarizing",
            current=pair_total,
            total=pair_total,
            message=f"Summarizing {match_count} visible matches",
            status="running",
        )

        if all_match_info:
            matches_text = _build_matches_text(all_match_info)
            user_prompt = SUMMARY_USER_PROMPT.format(matches_text=matches_text)

            result = call_llm(
                system_prompt=SUMMARY_SYSTEM_PROMPT,
                user_prompt=user_prompt,
                response_model=SearchSummaryResponse,
                profile=SUMMARY_PROFILE,
            )
            summary_data = result["content"]
        else:
            summary_data = {
                "summary": "No relevant items found in today's search.",
                "citations": [],
            }

        run.candidate_count = len(papers)
        run.match_count = match_count
        run.summary = summary_data.get("summary", "")
        run.summary_citations = summary_data.get("citations", [])
        run.completed_at = datetime.now(timezone.utc)
        _set_progress(
            db,
            run,
            job,
            stage="completed",
            current=pair_total,
            total=pair_total,
            message=f"Completed daily search with {match_count} matches",
            status="completed",
        )

    except Exception as e:
        db.rollback()
        run = db.query(SearchRun).filter(SearchRun.id == search_run_id).first()
        if run:
            run.status = "failed"
            run.error = str(e)
            run.completed_at = datetime.now(timezone.utc)
            job = _resolve_daily_search_job(db, search_run_id, job_id)
            job.status = "failed"
            job.error = run.error
            job.completed_at = run.completed_at
            job.updated_at = run.completed_at
            job.progress = build_progress(
                stage="failed",
                current=(job.progress or {}).get("current", 0),
                total=(job.progress or {}).get("total", 1),
                message=f"Daily search failed: {e}",
                log=(job.progress or {}).get("log", []),
            )
            db.commit()
        logger.exception("daily_search run=%s failed", search_run_id)
        raise
    finally:
        db.close()
