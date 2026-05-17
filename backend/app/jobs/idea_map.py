"""Idea map generation worker job."""

import hashlib
from datetime import datetime, timezone

import httpx
from sqlalchemy.orm import Session

from app.core.config import settings
from app.db.session import SessionLocal
from app.models.paper import Paper
from app.models.paper_html import PaperHtml
from app.models.idea_map import IdeaMap
from app.services.html_parser import parse_arxiv_html, validate_citation, blocks_to_prompt_text
from app.llm.client import call_llm, build_json_schema
from app.llm.prompts import (
    IDEA_MAP_SYSTEM_PROMPT,
    IDEA_MAP_USER_PROMPT,
    IDEA_MAP_SCHEMA,
)


def generate_idea_map(idea_map_id: str) -> None:
    """Worker job: generate idea map from arXiv HTML."""
    db = SessionLocal()
    try:
        idea_map = db.query(IdeaMap).filter(IdeaMap.id == idea_map_id).first()
        if not idea_map:
            return

        idea_map.status = "running"
        idea_map.updated_at = datetime.now(timezone.utc)
        db.commit()

        paper = db.query(Paper).filter(Paper.id == idea_map.paper_id).first()
        if not paper or not paper.arxiv_id:
            idea_map.status = "skipped"
            idea_map.dropped_reason = "Paper not found or missing arxiv_id"
            idea_map.updated_at = datetime.now(timezone.utc)
            db.commit()
            return

        html_url = f"https://arxiv.org/html/{paper.arxiv_id}"
        idea_map.source_url = html_url

        cached = db.query(PaperHtml).filter(PaperHtml.paper_id == paper.id).first()

        if cached:
            html_content = cached.html
        else:
            try:
                with httpx.Client(timeout=30.0, follow_redirects=True) as client:
                    resp = client.get(html_url)
                    resp.raise_for_status()
                    html_content = resp.text
            except Exception:
                idea_map.status = "skipped"
                idea_map.dropped_reason = f"Could not fetch HTML from {html_url}"
                idea_map.updated_at = datetime.now(timezone.utc)
                db.commit()
                return

            content_hash = hashlib.sha256(html_content.encode()).hexdigest()
            paper_html = PaperHtml(
                paper_id=paper.id,
                source_url=html_url,
                html=html_content,
                content_hash=content_hash,
                fetched_at=datetime.now(timezone.utc),
            )
            db.add(paper_html)
            db.commit()

        blocks = parse_arxiv_html(html_content)
        if not blocks:
            idea_map.status = "skipped"
            idea_map.dropped_reason = "HTML could not be parsed into addressable blocks"
            idea_map.updated_at = datetime.now(timezone.utc)
            db.commit()
            return

        if not settings.OPENROUTER_API_KEY:
            idea_map.claims = [
                {
                    "id": "demo-claim-1",
                    "text": "The paper presents a novel approach to the problem.",
                    "warrants": [
                        {
                            "id": "demo-warrant-1",
                            "text": "Experimental results show improvement over baselines.",
                            "citation": {
                                "blockId": blocks[0].block_id if blocks else "block-0",
                                "quote": blocks[0].text[:50] if blocks else "",
                                "prefix": "",
                                "suffix": "",
                                "htmlAnchor": blocks[0].html_anchor if blocks else "#block-0",
                                "sectionTitle": blocks[0].section_title if blocks else "",
                            },
                        }
                    ],
                }
            ]
            idea_map.status = "completed"
            idea_map.updated_at = datetime.now(timezone.utc)
            db.commit()
            return

        blocks_text = blocks_to_prompt_text(blocks)
        user_prompt = IDEA_MAP_USER_PROMPT.format(blocks_text=blocks_text)
        response_format = build_json_schema("idea_map", IDEA_MAP_SCHEMA)

        result = call_llm(
            system_prompt=IDEA_MAP_SYSTEM_PROMPT,
            user_prompt=user_prompt,
            response_format=response_format,
        )

        content = result["content"]
        raw_claims = content.get("claims", [])

        validated_claims = []
        for claim in raw_claims:
            valid_warrants = []
            for warrant in claim.get("warrants", []):
                citation = warrant.get("citation", {})
                if validate_citation(blocks, citation):
                    valid_warrants.append(warrant)
            if valid_warrants:
                claim["warrants"] = valid_warrants
                validated_claims.append(claim)

        idea_map.claims = validated_claims
        idea_map.llm_model = result["model"]
        idea_map.llm_response_id = result["response_id"]
        idea_map.status = "completed"
        idea_map.updated_at = datetime.now(timezone.utc)
        db.commit()

    except Exception as e:
        db.rollback()
        idea_map = db.query(IdeaMap).filter(IdeaMap.id == idea_map_id).first()
        if idea_map:
            idea_map.status = "failed"
            idea_map.error = str(e)
            idea_map.updated_at = datetime.now(timezone.utc)
            db.commit()
        raise
    finally:
        db.close()
