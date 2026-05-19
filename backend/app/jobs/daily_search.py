"""Daily search worker job."""

import asyncio
import logging
from datetime import datetime, timezone

from app.core.config import LLM_MAX_CONCURRENCY
from app.db.session import database
from app.models.filter import Filter
from app.models.paper import Paper
from app.models.paper_match import PaperMatch
from app.models.search_run import SearchRun
from app.models.job import Job
from app.services.jobs import get_or_create_job_for_subject, job_progress, set_job_status
from app.services.source_providers import papers_for_sources
from app.services.source_settings import enabled_source_types
from app.llm.client import async_call_llm
from app.llm.config import JUDGE_PROFILE
from app.llm.prompts import (
    CLAIM_FILTER_SEARCH_SYSTEM_PROMPT,
    CLAIM_FILTER_SEARCH_USER_PROMPT,
    TOPIC_FILTER_SEARCH_SYSTEM_PROMPT,
    TOPIC_FILTER_SEARCH_USER_PROMPT,
)
from app.llm.schemas import ClaimFilterSearchResponse, TopicFilterSearchResponse
from app.schemas.daily_search import FilterPayload, PairEvaluation
from paper_search_core.schemas.daily_search import PaperPayload
from tqdm import tqdm

logger = logging.getLogger(__name__)
PAIR_TIMEOUT_SECONDS = 30.0
PAIRING_PHASE_TIMEOUT_SECONDS = 180.0


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


def _candidate_counts_by_source(papers: list[Paper]) -> dict[str, int]:
    counts: dict[str, int] = {}
    for paper in papers:
        source_type = paper.source_type or "arxiv"
        counts[source_type] = counts.get(source_type, 0) + 1
    return counts


def _complete_daily_search_stage(db, run: SearchRun, job: Job) -> None:
    set_job_status(job, status="completed")
    db.commit()


def _prompts_for_mode(mode: str):
    if mode == "claim":
        return CLAIM_FILTER_SEARCH_SYSTEM_PROMPT, CLAIM_FILTER_SEARCH_USER_PROMPT, ClaimFilterSearchResponse
    return TOPIC_FILTER_SEARCH_SYSTEM_PROMPT, TOPIC_FILTER_SEARCH_USER_PROMPT, TopicFilterSearchResponse


def _extract_result(mode: str, match: dict | None) -> dict | None:
    if not match:
        return None
    if mode == "claim":
        return {"verdict": match.get("verdict", "positive"), "reason": match.get("reason", ""), "evidence": match.get("evidence")}
    return {"reason": match.get("reason", ""), "evidence": match.get("evidence")}


async def _evaluate_filter_paper(
    *,
    semaphore: asyncio.Semaphore,
    filter: FilterPayload,
    paper: PaperPayload,
) -> PairEvaluation:
    definition = filter.definition or {}
    mode = definition.get("mode", "topic")
    system_prompt, user_prompt_template, response_model = _prompts_for_mode(mode)

    user_prompt = user_prompt_template.format(
        filter_name=definition.get("name", filter.name),
        filter_description=definition.get("description", ""),
        papers_text=paper.prompt_text(),
    )
    async with semaphore:
        try:
            llm_result = await async_call_llm(
                system_prompt=system_prompt,
                user_prompt=user_prompt,
                response_model=response_model,
                profile=JUDGE_PROFILE,
            )
        except Exception as exc:
            return PairEvaluation(
                filter_id=filter.id,
                filter_name=filter.name,
                paper_id=paper.id,
                paper_title=paper.title,
                source_type=paper.source_type or "arxiv",
                source_id=paper.source_id or "",
                item_id=paper.item_id,
                error=str(exc),
            )

    matches = llm_result["content"].get("matches", [])
    raw_match = next(
        (m for m in matches if m.get("itemId") == paper.item_id),
        matches[0] if matches else None,
    )
    result = _extract_result(mode, raw_match)

    return PairEvaluation(
        filter_id=filter.id,
        filter_name=filter.name,
        paper_id=paper.id,
        paper_title=paper.title,
        source_type=paper.source_type,
        source_id=paper.source_id,
        item_id=paper.item_id,
        result=result,
        model=llm_result["model"],
        response_id=llm_result["response_id"],
    )


async def _evaluate_filter_paper_with_timeout(
    *,
    semaphore: asyncio.Semaphore,
    filter: FilterPayload,
    paper: PaperPayload,
) -> PairEvaluation:
    try:
        return await asyncio.wait_for(
            _evaluate_filter_paper(semaphore=semaphore, filter=filter, paper=paper),
            timeout=PAIR_TIMEOUT_SECONDS,
        )
    except asyncio.TimeoutError:
        return PairEvaluation(
            filter_id=filter.id,
            filter_name=filter.name,
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
    for filter in filters:
        for paper in papers:
            task = asyncio.create_task(
                _evaluate_filter_paper_with_timeout(
                    semaphore=semaphore,
                    filter=filter,
                    paper=paper,
                )
            )
            task_pairs[task] = (filter, paper)

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
            filter, paper = task_pairs[task]
            await on_result(
                PairEvaluation(
                    filter_id=filter.id,
                    filter_name=filter.name,
                    paper_id=paper.id,
                    paper_title=paper.title,
                    source_type=paper.source_type,
                    source_id=paper.source_id,
                    item_id=paper.item_id,
                    error=f"Pairing phase timed out after {PAIRING_PHASE_TIMEOUT_SECONDS:g}s",
                )
            )


def run_daily_search(search_run_id: str, job_id: str) -> None:
    """Worker job: evaluate filters against daily papers and persist matches."""
    with database.session() as db:
        run = db.query(SearchRun).filter(SearchRun.id == search_run_id).first()
        if not run:
            return

        job = db.query(Job).filter(Job.id == job_id).first()
        if not job:
            return

        try:
            run.status = "running"
            run.started_at = datetime.now(timezone.utc)
            set_job_status(job, status="running")
            db.commit()

            papers = papers_for_sources(db, enabled_source_types(db), run.run_date)

            active_filters = db.query(Filter).filter(Filter.status == "active").all()
            filter_payloads = [f.to_search_payload() for f in active_filters]
            paper_payloads = [p.to_search_payload() for p in papers]
            pair_total = len(filter_payloads) * len(paper_payloads)
            job.progress = job_progress(total=pair_total)
            db.commit()

            run.candidate_count = len(papers)
            run.candidate_counts = _candidate_counts_by_source(papers)

            if not filter_payloads or not paper_payloads:
                run.match_count = 0
                db.commit()
                _complete_daily_search_stage(db, run, job)
                return

            completed_pairs = 0
            failed_pairs = 0
            first_pair_error = ""

            async def handle_pair_result(evaluation: PairEvaluation) -> None:
                nonlocal completed_pairs, failed_pairs, first_pair_error
                completed_pairs += 1

                if evaluation.error:
                    failed_pairs += 1
                    if not first_pair_error:
                        first_pair_error = evaluation.error
                    tqdm.write(
                        f"Pair {completed_pairs}/{pair_total} failed: "
                        f"{evaluation.filter_name} x {evaluation.item_id}: "
                        f"{evaluation.error}"
                    )
                else:
                    result = evaluation.result
                    has_content = result and result.get("reason", "").strip()
                    if has_content:
                        db.add(
                            PaperMatch(
                                search_run_id=search_run_id,
                                filter_id=evaluation.filter_id,
                                paper_id=evaluation.paper_id,
                                result=result,
                                llm_model=evaluation.model,
                                llm_response_id=evaluation.response_id,
                            )
                        )
                db.commit()
                pair_progress.update(1)

            with tqdm(
                total=pair_total,
                desc="filter-item pairs",
                unit="pair",
                dynamic_ncols=True,
                disable=None,
            ) as pair_progress:
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

            run.match_count = (
                db.query(PaperMatch)
                .filter(PaperMatch.search_run_id == search_run_id)
                .count()
            )
            db.commit()
            _complete_daily_search_stage(db, run, job)

        except Exception as e:
            db.rollback()
            run = db.query(SearchRun).filter(SearchRun.id == search_run_id).first()
            if run:
                run.status = "failed"
                run.error = str(e)
                run.completed_at = datetime.now(timezone.utc)
                job = _resolve_daily_search_job(db, search_run_id, job_id)
                set_job_status(job, status="failed", error=str(e))
                db.commit()
            logger.exception("daily_search run=%s failed", search_run_id)
            raise
