"""Opt-in OpenRouter smoke tests.

Run only when both OPENROUTER_API_KEY and RUN_LIVE_LLM_TESTS=1 are set.
Uses tiny fixtures to verify schema shape and minimal semantic behavior.
"""

import os
import uuid
import pytest

pytestmark = pytest.mark.skipif(
    not (os.getenv("OPENROUTER_API_KEY") and os.getenv("RUN_LIVE_LLM_TESTS") == "1"),
    reason="Set OPENROUTER_API_KEY and RUN_LIVE_LLM_TESTS=1 to run",
)


class TestOnboardingExtraction:
    def test_returns_proposed_filters(self):
        from app.llm.client import call_llm, build_json_schema
        from app.llm.prompts import (
            ONBOARDING_SYSTEM_PROMPT,
            ONBOARDING_USER_PROMPT,
            ONBOARDING_SCHEMA,
        )

        user_prompt = ONBOARDING_USER_PROMPT.format(
            input_text="I study how large language models handle multi-step reasoning."
        )
        result = call_llm(
            ONBOARDING_SYSTEM_PROMPT,
            user_prompt,
            build_json_schema("OnboardingExtractionOutput", ONBOARDING_SCHEMA),
        )
        content = result["content"]
        assert "proposedFilters" in content
        filters = content["proposedFilters"]
        assert len(filters) >= 1
        f = filters[0]
        assert "id" in f
        assert "name" in f
        assert "description" in f
        assert f["mode"] in ("warrants", "answers", "relevance")


class TestFilterSearch:
    def test_returns_matches(self):
        from app.llm.client import call_llm, build_json_schema
        from app.llm.prompts import (
            FILTER_SEARCH_SYSTEM_PROMPT,
            FILTER_SEARCH_USER_PROMPT,
            FILTER_SEARCH_SCHEMA,
        )

        papers_text = (
            "arXiv:2401.00001 | Chain-of-Thought Prompting Elicits Reasoning in Large Language Models\n"
            "Abstract: We show that generating a chain of thought improves performance on arithmetic, commonsense, and symbolic reasoning benchmarks.\n\n"
            "arXiv:2401.00002 | Efficient Image Compression with Neural Networks\n"
            "Abstract: We propose a learned image codec that achieves state-of-the-art rate-distortion performance."
        )
        user_prompt = FILTER_SEARCH_USER_PROMPT.format(
            filter_name="LLM reasoning",
            filter_description="Large language models can perform multi-step reasoning",
            filter_behavior="Look for evidence that supports, refutes, or complicates the described claim.",
            papers_text=papers_text,
        )
        result = call_llm(
            FILTER_SEARCH_SYSTEM_PROMPT,
            user_prompt,
            build_json_schema("FilterSearchOutput", FILTER_SEARCH_SCHEMA),
        )
        content = result["content"]
        assert "matches" in content
        assert isinstance(content["matches"], list)
        for m in content["matches"]:
            assert "arxivId" in m
            assert "stance" in m
            assert "relevanceScore" in m


class TestDailySummary:
    def test_returns_summary_and_citations(self):
        from app.llm.client import call_llm, build_json_schema
        from app.llm.prompts import (
            SUMMARY_SYSTEM_PROMPT,
            SUMMARY_USER_PROMPT,
            SUMMARY_SCHEMA,
        )

        matches_text = (
            "Paper: Chain-of-Thought Prompting (arXiv:2401.00001)\n"
            "Filter: LLM reasoning\n"
            "Stance: supports (score: 0.9)\n"
            "Rationale: Demonstrates multi-step reasoning via chain-of-thought.\n\n"
            "Paper: Efficient Image Compression (arXiv:2401.00002)\n"
            "Filter: LLM reasoning\n"
            "Stance: irrelevant (score: 0.1)\n"
            "Rationale: Unrelated to language model reasoning."
        )
        user_prompt = SUMMARY_USER_PROMPT.format(matches_text=matches_text)
        result = call_llm(
            SUMMARY_SYSTEM_PROMPT,
            user_prompt,
            build_json_schema("SearchRunSummaryOutput", SUMMARY_SCHEMA),
        )
        content = result["content"]
        assert "summary" in content
        assert len(content["summary"]) > 10
        assert "citations" in content
        assert isinstance(content["citations"], list)


class TestIdeaMapExtraction:
    def test_returns_claims_with_warrants(self):
        from app.llm.client import call_llm, build_json_schema
        from app.llm.prompts import (
            IDEA_MAP_SYSTEM_PROMPT,
            IDEA_MAP_USER_PROMPT,
            IDEA_MAP_SCHEMA,
        )

        blocks_text = (
            "[block-1] (Section: Introduction)\n"
            "Large language models have shown remarkable reasoning abilities when prompted with chain-of-thought examples.\n\n"
            "[block-2] (Section: Results)\n"
            "Our experiments demonstrate a 15% improvement in accuracy on GSM8K when using chain-of-thought prompting compared to standard prompting.\n\n"
            "[block-3] (Section: Results)\n"
            "The improvement is consistent across model sizes from 7B to 70B parameters."
        )
        user_prompt = IDEA_MAP_USER_PROMPT.format(blocks_text=blocks_text)
        result = call_llm(
            IDEA_MAP_SYSTEM_PROMPT,
            user_prompt,
            build_json_schema("IdeaMapOutput", IDEA_MAP_SCHEMA),
        )
        content = result["content"]
        assert "claims" in content
        assert len(content["claims"]) >= 1
        claim = content["claims"][0]
        assert "text" in claim
        assert "warrants" in claim
        if claim["warrants"]:
            w = claim["warrants"][0]
            assert "text" in w
            assert "citation" in w
            assert "blockId" in w["citation"]
            assert "quote" in w["citation"]
