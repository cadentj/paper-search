"""Daily search worker job."""

import asyncio
import logging
import uuid
from dataclasses import dataclass
from datetime import datetime, timezone

from app.core.config import LLM_MAX_CONCURRENCY, settings
from app.db.session import SessionLocal
from app.models.filter import Filter
from app.models.paper import Paper
from app.models.paper_match import PaperMatch
from app.models.search_run import SearchRun
from app.models.search_run_paper import SearchRunPaper
from app.services.local_arxiv_cache import fetch_local_cached_papers
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
    arxiv_id: str
    abstract: str
    authors: list[str]


@dataclass
class PairEvaluation:
    filter_id: str
    filter_name: str
    paper_id: str
    paper_title: str
    arxiv_id: str
    result: dict | None = None
    model: str | None = None
    response_id: str | None = None
    error: str | None = None


def _build_papers_text(papers: list[Paper | PaperPayload]) -> str:
    lines = []
    for p in papers:
        lines.append(
            f"ArXiv ID: {p.arxiv_id}\n"
            f"Title: {p.title}\n"
            f"Authors: {', '.join(p.authors) if p.authors else 'Unknown'}\n"
            f"Abstract: {p.abstract}\n"
        )
    return "\n---\n".join(lines)


def _build_paper_text(paper: Paper | PaperPayload) -> str:
    return _build_papers_text([paper])


def _build_matches_text(matches: list[dict]) -> str:
    lines = []
    for m in matches:
        lines.append(
            f"Paper: {m.get('paper_title', 'Unknown')} ({m.get('arxiv_id', '')})\n"
            f"Filter: {m.get('filter_name', 'Unknown')}\n"
            f"Stance: {m.get('stance', '')}\n"
            f"Score: {m.get('relevance_score', 0)}\n"
            f"Rationale: {m.get('rationale', '')}\n"
            f"Match ID: {m.get('match_id', '')}\n"
        )
    return "\n---\n".join(lines)


def _append_progress_log(run: SearchRun, stage: str, message: str) -> None:
    log = list(run.progress_log or [])
    log.append(
        {
            "at": datetime.now(timezone.utc).isoformat(),
            "stage": stage,
            "message": message,
        }
    )
    run.progress_log = log[-50:]


def _set_progress(
    db,
    run: SearchRun,
    *,
    stage: str,
    current: int,
    total: int,
    message: str,
    status: str | None = None,
) -> None:
    logger.info("daily_search run=%s stage=%s %s", run.id, stage, message)
    run.stage = stage
    run.progress_current = current
    run.progress_total = max(total, 1)
    run.progress_message = message
    if status:
        run.status = status
    _append_progress_log(run, stage, message)
    db.commit()


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


def _upsert_candidate_papers(db, run: SearchRun) -> list[Paper]:
    now = datetime.now(timezone.utc)
    daily_papers = fetch_local_cached_papers()
    candidate_paper_ids = set()
    papers: list[Paper] = []

    db.query(SearchRunPaper).filter(SearchRunPaper.search_run_id == run.id).delete()

    for p_data in daily_papers:
        existing = db.query(Paper).filter(Paper.arxiv_id == p_data["arxiv_id"]).first()
        if existing:
            existing.title = p_data["title"]
            existing.abstract = p_data["abstract"]
            existing.authors = p_data["authors"]
            existing.categories = p_data.get("categories")
            existing.published_at = p_data.get("published_at")
            existing.html_url = p_data.get("html_url")
            existing.landing_url = p_data.get("landing_url")
            existing.updated_at = now
            paper = existing
        else:
            paper = Paper(
                id=str(uuid.uuid4()),
                arxiv_id=p_data["arxiv_id"],
                title=p_data["title"],
                abstract=p_data["abstract"],
                authors=p_data["authors"],
                categories=p_data.get("categories"),
                published_at=p_data.get("published_at"),
                html_url=p_data.get("html_url"),
                landing_url=p_data.get("landing_url"),
                created_at=now,
                updated_at=now,
            )
            db.add(paper)

        if paper.id in candidate_paper_ids:
            continue
        candidate_paper_ids.add(paper.id)
        papers.append(paper)
        db.add(
            SearchRunPaper(
                search_run_id=run.id,
                paper_id=paper.id,
                created_at=now,
            )
        )

    run.candidate_count = len(candidate_paper_ids)
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


def _build_paper_payloads(papers: list[Paper]) -> list[PaperPayload]:
    return [
        PaperPayload(
            id=paper.id,
            title=paper.title,
            arxiv_id=paper.arxiv_id or "",
            abstract=paper.abstract,
            authors=list(paper.authors or []),
        )
        for paper in papers
    ]


def _filter_behavior(mode: str) -> str:
    if mode == "claim":
        return "Look for evidence that supports, refutes, or complicates the described claim."
    if mode == "question":
        return "Look for papers that answer or partially answer the described question."
    return "Look for papers relevant to the described topic."


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
                arxiv_id=paper.arxiv_id or "",
                error=str(exc),
            )

    matches = llm_result["content"].get("matches", [])
    match = next(
        (m for m in matches if m.get("arxivId") == paper.arxiv_id),
        matches[0] if matches else None,
    )

    return PairEvaluation(
        filter_id=filt.id,
        filter_name=filt.name,
        paper_id=paper.id,
        paper_title=paper.title,
        arxiv_id=paper.arxiv_id or "",
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
            arxiv_id=paper.arxiv_id,
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
                    arxiv_id=paper.arxiv_id,
                    error=f"Pairing phase timed out after {PAIRING_PHASE_TIMEOUT_SECONDS:g}s",
                )
            )


def run_daily_search(search_run_id: str) -> None:
    """Worker job: run daily search across all active filters."""
    db = SessionLocal()
    try:
        run = db.query(SearchRun).filter(SearchRun.id == search_run_id).first()
        if not run:
            return

        run.started_at = datetime.now(timezone.utc)
        _set_progress(
            db,
            run,
            stage="fetching_papers",
            current=0,
            total=1,
            message="Selecting local cached arXiv papers",
            status="running",
        )

        papers = _upsert_candidate_papers(db, run)
        _set_progress(
            db,
            run,
            stage="fetching_papers",
            current=1,
            total=1,
            message=f"Selected {len(papers)} local cached arXiv papers",
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
                else "No arXiv papers were available for this daily search."
            )
            run.completed_at = datetime.now(timezone.utc)
            _set_progress(
                db,
                run,
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
            stage="matching_filters",
            current=0,
            total=pair_total,
            message=f"Evaluating 0/{pair_total} filter-paper pairs",
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
                    f"{evaluation.filter_name} x {evaluation.arxiv_id}: "
                    f"{evaluation.error}"
                )
                _append_progress_log(run, "matching_filters", message)
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
                        "arxiv_id": evaluation.arxiv_id,
                        "filter_name": evaluation.filter_name,
                        "stance": match.stance,
                        "relevance_score": match.relevance_score,
                        "rationale": match.rationale,
                    })
                else:
                    irrelevant_pairs += 1

            run.stage = "matching_filters"
            run.progress_current = completed_pairs
            run.progress_total = pair_total
            run.progress_message = f"Evaluated {completed_pairs}/{pair_total} filter-paper pairs"
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
            desc="filter-paper pairs",
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
                f"All {pair_total} filter-paper evaluations failed. First error: {first_pair_error}"
            )

        match_count = len(all_match_info)
        _set_progress(
            db,
            run,
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
                "summary": "No relevant papers found in today's search.",
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
            run.stage = "failed"
            run.error = str(e)
            run.progress_message = f"Daily search failed: {e}"
            _append_progress_log(run, "failed", run.progress_message)
            db.commit()
        logger.exception("daily_search run=%s failed", search_run_id)
        raise
    finally:
        db.close()
