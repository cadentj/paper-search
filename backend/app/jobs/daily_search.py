"""Daily search worker job."""

import asyncio
import logging
import uuid
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
from app.services.source_providers import candidates_for_sources
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
from app.schemas.daily_search import FilterPayload, PairEvaluation
from paper_search_core.schemas.daily_search import PaperPayload
from tqdm import tqdm

logger = logging.getLogger(__name__)
PAIR_TIMEOUT_SECONDS = 30.0
PAIRING_PHASE_TIMEOUT_SECONDS = 180.0


def _build_papers_text(papers: list[PaperPayload]) -> str:
    lines = []
    for p in papers:
        lines.append(
            f"Item ID: {p.item_id}\n"
            f"Source Type: {p.source_type}\n"
            f"Source ID: {p.source_id}\n"
            f"Title: {p.title}\n"
            f"Authors: {', '.join(p.authors) if p.authors else 'Unknown'}\n"
            f"Excerpt: {p.text}\n"
        )
    return "\n---\n".join(lines)


def _build_paper_text(paper: PaperPayload) -> str:
    return _build_papers_text([paper])


def _build_matches_text(matches: list[dict]) -> str:
    lines = []
    for m in matches:
        lines.append(
            f"Item: {m.get('paper_title', 'Unknown')} ({m.get('item_id', '')})\n"
            f"Source: {m.get('source_type', '')} {m.get('source_id', '')}\n"
            f"Filter: {m.get('filter_name', 'Unknown')}\n"
            f"Result: {m.get('result', '')}\n"
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


def _link_candidate_papers(db, run: SearchRun, job: Job | None = None) -> list[Paper]:
    now = datetime.now(timezone.utc)
    active_sources = enabled_source_types(db)
    fetch_result = candidates_for_sources(active_sources, run.run_date)
    if job:
        for error in fetch_result.errors:
            _append_progress_log(job, "fetching_items", error)
        for stype, count in sorted(fetch_result.skipped_missing_text.items()):
            if count:
                _append_progress_log(
                    job,
                    "fetching_items",
                    f"skipped_missing_text[{stype}]={count} (no excerpt in index shard)",
                )
    if active_sources and fetch_result.errors and not fetch_result.papers:
        raise RuntimeError("; ".join(fetch_result.errors))

    paper_ids = [paper.id for paper in fetch_result.papers]
    if paper_ids:
        papers = db.query(Paper).filter(Paper.id.in_(paper_ids)).all()
        papers_by_id = {paper.id: paper for paper in papers}
        ordered_papers = [
            papers_by_id[paper_id]
            for paper_id in paper_ids
            if paper_id in papers_by_id
        ]
    else:
        ordered_papers = []

    candidate_paper_ids: set[str] = set()
    papers: list[Paper] = []
    counts: dict[str, int] = {}

    db.query(SearchRunPaper).filter(SearchRunPaper.search_run_id == run.id).delete()

    for paper in ordered_papers:
        if paper.id in candidate_paper_ids:
            continue
        candidate_paper_ids.add(paper.id)
        source_type = paper.source_type or "arxiv"
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


def _filter_behavior(mode: str) -> str:
    if mode == "claim":
        return "Look for evidence that supports, refutes, or complicates the described claim."
    return "Look for items relevant to the described topic or question."


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

        papers = _link_candidate_papers(db, run, job)
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
        filter_payloads = [f.to_search_payload() for f in active_filters]
        paper_payloads = [p.to_search_payload() for p in papers]
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
                result_text = str(match_data.get("result") or "").strip()
                if result_text:
                    matched_pairs += 1
                    match = PaperMatch(
                        id=str(uuid.uuid4()),
                        search_run_id=search_run_id,
                        filter_id=evaluation.filter_id,
                        paper_id=evaluation.paper_id,
                        result=result_text,
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
                        "result": match.result,
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
