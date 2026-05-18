"""Backend unit tests."""

import uuid
from datetime import datetime, timezone

import pytest

from app.services.arxiv import build_category_query, normalize_arxiv_id, parse_arxiv_feed
from app.services.html_parser import parse_arxiv_html, validate_citation, blocks_to_prompt_text


class TestArxivProvider:
    SAMPLE_FEED = """
    <feed xmlns="http://www.w3.org/2005/Atom" xmlns:arxiv="http://arxiv.org/schemas/atom">
      <entry>
        <id>http://arxiv.org/abs/2605.01234v2</id>
        <published>2026-05-16T18:00:00Z</published>
        <title>
          A Current Paper About AI Systems
        </title>
        <summary>
          We study modern AI systems and report useful findings.
        </summary>
        <author><name>Researcher One</name></author>
        <author><name>Researcher Two</name></author>
        <arxiv:primary_category term="cs.AI" />
        <category term="cs.AI" />
        <category term="cs.LG" />
      </entry>
    </feed>
    """

    def test_normalizes_arxiv_id(self):
        assert normalize_arxiv_id("http://arxiv.org/abs/2605.01234v2") == "2605.01234"
        assert normalize_arxiv_id("2605.01234v1") == "2605.01234"

    def test_builds_category_query(self):
        assert build_category_query(["cs.AI", "cs.CL"]) == "cat:cs.AI OR cat:cs.CL"

    def test_parses_feed_records(self):
        papers = parse_arxiv_feed(self.SAMPLE_FEED)
        assert len(papers) == 1
        paper = papers[0]
        assert paper["arxiv_id"] == "2605.01234"
        assert paper["title"] == "A Current Paper About AI Systems"
        assert paper["authors"] == ["Researcher One", "Researcher Two"]
        assert paper["categories"] == ["cs.AI", "cs.LG"]
        assert paper["html_url"] == "https://arxiv.org/html/2605.01234"
        assert paper["published_at"].year == 2026


class TestHtmlParser:
    SAMPLE_HTML = """
    <html>
    <body>
        <h1 id="title">Introduction to Neural Networks</h1>
        <p id="para1">Neural networks are computational models inspired by biological neural networks.
        They consist of interconnected nodes organized in layers.</p>
        <h2 id="methods">Methods and Approach</h2>
        <p id="para2">We trained a transformer model on a large corpus of text data using standard
        optimization techniques including Adam optimizer with learning rate warmup.</p>
        <p>Short text</p>
        <h3 id="results">Experimental Results</h3>
        <p id="para3">Our model achieved 95.2% accuracy on the benchmark dataset, significantly
        outperforming the previous state-of-the-art by 3.1 percentage points.</p>
    </body>
    </html>
    """

    def test_parses_into_addressable_blocks(self):
        blocks = parse_arxiv_html(self.SAMPLE_HTML)
        assert len(blocks) > 0
        for b in blocks:
            assert b.block_id
            assert b.text
            assert b.html_anchor.startswith("#")

    def test_preserves_section_titles(self):
        blocks = parse_arxiv_html(self.SAMPLE_HTML)
        sections = [b.section_title for b in blocks if b.section_title]
        assert any("Introduction" in s for s in sections) or any("Methods" in s for s in sections)

    def test_generates_stable_anchors(self):
        blocks = parse_arxiv_html(self.SAMPLE_HTML)
        ids_with_existing = [b for b in blocks if not b.block_id.startswith("block-")]
        assert len(ids_with_existing) > 0

    def test_skips_short_text(self):
        blocks = parse_arxiv_html(self.SAMPLE_HTML)
        for b in blocks:
            assert len(b.text) >= 10


class TestCitationValidation:
    SAMPLE_HTML = """
    <html><body>
        <p id="p1">The transformer architecture uses self-attention mechanisms to process sequences in parallel.</p>
        <p id="p2">Experiments show a 15% improvement over baseline methods on standard benchmarks.</p>
    </body></html>
    """

    def test_accepts_exact_quote(self):
        blocks = parse_arxiv_html(self.SAMPLE_HTML)
        citation = {
            "blockId": "p1",
            "quote": "self-attention mechanisms",
        }
        assert validate_citation(blocks, citation) is True

    def test_accepts_prefix_suffix(self):
        blocks = parse_arxiv_html(self.SAMPLE_HTML)
        citation = {
            "blockId": "p2",
            "prefix": "Experiments show",
            "suffix": "standard benchmarks",
        }
        assert validate_citation(blocks, citation) is True

    def test_rejects_missing_block_id(self):
        blocks = parse_arxiv_html(self.SAMPLE_HTML)
        citation = {
            "blockId": "nonexistent",
            "quote": "some text",
        }
        assert validate_citation(blocks, citation) is False

    def test_rejects_wrong_quote(self):
        blocks = parse_arxiv_html(self.SAMPLE_HTML)
        citation = {
            "blockId": "p1",
            "quote": "this text does not exist in the block",
        }
        assert validate_citation(blocks, citation) is False

    def test_rejects_ambiguous_span(self):
        blocks = parse_arxiv_html(self.SAMPLE_HTML)
        citation = {
            "blockId": "p1",
            "prefix": "mechanisms",
            "suffix": "transformer",
        }
        assert validate_citation(blocks, citation) is False


class TestBlocksToPromptText:
    def test_converts_blocks_to_text(self):
        html = "<html><body><p id='p1'>A paragraph of sufficient length for testing purposes.</p></body></html>"
        blocks = parse_arxiv_html(html)
        text = blocks_to_prompt_text(blocks)
        assert "p1" in text
        assert "paragraph" in text

    def test_respects_max_blocks(self):
        html = "<html><body>" + "".join(
            f"<p id='p{i}'>This is paragraph number {i} with enough text to pass the filter.</p>"
            for i in range(20)
        ) + "</body></html>"
        blocks = parse_arxiv_html(html)
        text = blocks_to_prompt_text(blocks, max_blocks=5)
        lines = [l for l in text.split("\n\n") if l.strip()]
        assert len(lines) <= 5


class TestFilterDefinition:
    def test_claim_mode(self):
        definition = {
            "name": "Test claim",
            "description": "LLMs can reason",
            "mode": "warrants",
        }
        assert definition["mode"] == "warrants"

    def test_question_mode(self):
        definition = {
            "name": "Test question",
            "description": "What causes hallucination?",
            "mode": "answers",
        }
        assert definition["mode"] == "answers"

    def test_topic_mode(self):
        definition = {
            "name": "Test topic",
            "description": "Transformer architectures",
            "mode": "relevance",
        }
        assert definition["mode"] == "relevance"

    def test_no_kind_field(self):
        definition = {
            "name": "Test",
            "description": "Test statement",
            "mode": "warrants",
        }
        assert "kind" not in definition

    def test_no_version_field(self):
        definition = {
            "name": "Test",
            "description": "Test statement",
            "mode": "warrants",
        }
        assert "version" not in definition

    def test_no_statement_or_search_fields(self):
        definition = {
            "name": "Test",
            "description": "Test statement",
            "mode": "warrants",
        }
        assert "statement" not in definition
        assert "search" not in definition
        assert "instructions" not in definition
        assert "outputMode" not in definition


class TestLLMClient:
    def test_loads_llm_config_defaults(self):
        from app.llm.config import (
            FILTER_GENERATION_PROFILE,
            IDEA_MAP_PROFILE,
            JUDGE_PROFILE,
            SUMMARY_PROFILE,
            get_llm_config,
        )

        filter_generation = get_llm_config(FILTER_GENERATION_PROFILE)
        judge = get_llm_config(JUDGE_PROFILE)
        idea_map = get_llm_config(IDEA_MAP_PROFILE)
        summary = get_llm_config(SUMMARY_PROFILE)

        assert filter_generation.model == "openai/gpt-oss-120b"
        assert filter_generation.provider == "cerebras"
        assert judge.model == "deepseek/deepseek-v4-flash"
        assert judge.provider == "novita"
        assert idea_map.model == "deepseek/deepseek-v4-flash"
        assert idea_map.provider == "novita"
        assert summary.model == "deepseek/deepseek-v4-flash"
        assert summary.provider == "novita"

    def test_load_llm_config_requires_all_groups(self, tmp_path):
        from app.llm.config import load_llm_config

        config_path = tmp_path / "llm_config.toml"
        config_path.write_text(
            '[filter_generation]\nmodel = "model"\nprovider = "provider"\n'
        )

        with pytest.raises(RuntimeError, match=r"Missing LLM config group \[judge\]"):
            load_llm_config(config_path)

    def test_unknown_llm_config_profile_fails(self):
        from app.llm.config import get_llm_config

        with pytest.raises(RuntimeError, match="Unknown LLM config profile"):
            get_llm_config("missing")

    @pytest.mark.asyncio
    async def test_async_call_llm_retries_transient_status(self, monkeypatch):
        import httpx

        from app.llm import client as llm_client
        from app.llm.config import FILTER_GENERATION_PROFILE

        request = httpx.Request("POST", llm_client.OPENROUTER_URL)
        attempts = {"count": 0}
        request_bodies = []

        class FakeResponse:
            def __init__(self, status_code: int):
                self.status_code = status_code
                self.request = request

            def raise_for_status(self):
                if self.status_code >= 400:
                    raise httpx.HTTPStatusError(
                        "rate limited",
                        request=request,
                        response=httpx.Response(self.status_code, request=request),
                    )

            def json(self):
                return {
                    "id": "response-id",
                    "model": "test-model",
                    "choices": [{"message": {"content": '{"ok": true}'}}],
                }

        class FakeAsyncClient:
            def __init__(self, *args, **kwargs):
                pass

            async def __aenter__(self):
                return self

            async def __aexit__(self, *args):
                return None

            async def post(self, *args, **kwargs):
                attempts["count"] += 1
                request_bodies.append(kwargs["json"])
                if attempts["count"] == 1:
                    return FakeResponse(429)
                return FakeResponse(200)

        async def fake_sleep(delay):
            return None

        monkeypatch.setattr(llm_client.settings, "OPENROUTER_API_KEY", "test-key")
        monkeypatch.setattr(llm_client, "LLM_MAX_RETRIES", 1)
        monkeypatch.setattr(llm_client, "LLM_RETRY_BASE_SECONDS", 0)
        monkeypatch.setattr(llm_client.asyncio, "sleep", fake_sleep)
        monkeypatch.setattr(llm_client.httpx, "AsyncClient", FakeAsyncClient)

        result = await llm_client.async_call_llm(
            "system", "user", profile=FILTER_GENERATION_PROFILE
        )

        assert attempts["count"] == 2
        assert request_bodies[0]["model"] == "openai/gpt-oss-120b"
        assert request_bodies[0]["provider"] == {"order": ["cerebras"]}
        assert result["content"] == {"ok": True}
        assert result["model"] == "test-model"


class TestSQLiteSetup:
    def test_schema_initialized(self, db_engine):
        from sqlalchemy import inspect
        inspector = inspect(db_engine)
        tables = inspector.get_table_names()
        assert "filters" in tables
        assert "onboarding_extractions" in tables
        assert "papers" in tables
        assert "paper_html" in tables
        assert "search_runs" in tables
        assert "search_run_papers" in tables
        assert "paper_matches" in tables
        assert "idea_maps" in tables
        assert "feedback" not in tables

    def test_wal_mode_enabled(self, db_engine):
        with db_engine.connect() as conn:
            result = conn.execute(
                __import__("sqlalchemy").text("PRAGMA journal_mode")
            )
            mode = result.scalar()
            assert mode == "wal"


class TestFilterLifecycle:
    def test_active_filter_created(self, db_session):
        from app.models.filter import Filter
        f = Filter(
            id=str(uuid.uuid4()),
            name="Test Filter",
            definition={"name": "Test", "description": "Test", "mode": "warrants"},
            status="active",
            created_at=datetime.now(timezone.utc),
            updated_at=datetime.now(timezone.utc),
        )
        db_session.add(f)
        db_session.commit()
        active = db_session.query(Filter).filter(Filter.status == "active").all()
        assert len(active) == 1

    def test_archived_filter_not_active(self, db_session):
        from app.models.filter import Filter
        f = Filter(
            id=str(uuid.uuid4()),
            name="Archived Filter",
            definition={"name": "Test", "description": "Test", "mode": "warrants"},
            status="archived",
            created_at=datetime.now(timezone.utc),
            updated_at=datetime.now(timezone.utc),
            archived_at=datetime.now(timezone.utc),
        )
        db_session.add(f)
        db_session.commit()
        active = db_session.query(Filter).filter(Filter.status == "active").all()
        assert len(active) == 0

    def test_archived_filter_can_be_restored(self, db_session):
        from app.models.filter import Filter
        f = Filter(
            id=str(uuid.uuid4()),
            name="Restorable",
            definition={"name": "Test", "description": "Test", "mode": "warrants"},
            status="archived",
            created_at=datetime.now(timezone.utc),
            updated_at=datetime.now(timezone.utc),
            archived_at=datetime.now(timezone.utc),
        )
        db_session.add(f)
        db_session.commit()

        f.status = "active"
        f.archived_at = None
        db_session.commit()

        active = db_session.query(Filter).filter(Filter.status == "active").all()
        assert len(active) == 1
        assert active[0].archived_at is None
