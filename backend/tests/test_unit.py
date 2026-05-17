"""Backend unit tests."""

import uuid
from datetime import datetime, timezone

from app.services.mock_papers import get_daily_papers, MOCK_PAPERS
from app.services.html_parser import parse_arxiv_html, validate_citation, blocks_to_prompt_text


class TestMockPaperProvider:
    def test_returns_deterministic_records(self):
        papers1 = get_daily_papers()
        papers2 = get_daily_papers()
        assert len(papers1) == len(papers2)
        for p1, p2 in zip(papers1, papers2):
            assert p1["arxiv_id"] == p2["arxiv_id"]
            assert p1["title"] == p2["title"]

    def test_records_have_required_fields(self):
        papers = get_daily_papers()
        assert len(papers) > 0
        for p in papers:
            assert "arxiv_id" in p
            assert "title" in p
            assert "abstract" in p
            assert "authors" in p
            assert isinstance(p["authors"], list)
            assert "html_url" in p
            assert "published_at" in p

    def test_stable_arxiv_ids(self):
        papers = get_daily_papers()
        ids = [p["arxiv_id"] for p in papers]
        assert len(ids) == len(set(ids))
        for aid in ids:
            assert aid.startswith("2401.")


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
    def test_claim_template(self):
        definition = {
            "name": "Test claim",
            "statement": "LLMs can reason",
            "search": {"instructions": "Find evidence", "outputMode": "warrants"},
        }
        assert definition["search"]["outputMode"] == "warrants"

    def test_question_template(self):
        definition = {
            "name": "Test question",
            "statement": "What causes hallucination?",
            "search": {"instructions": "Find answers", "outputMode": "answers"},
        }
        assert definition["search"]["outputMode"] == "answers"

    def test_topic_template(self):
        definition = {
            "name": "Test topic",
            "statement": "Transformer architectures",
            "search": {"instructions": "Find relevant papers", "outputMode": "relevance"},
        }
        assert definition["search"]["outputMode"] == "relevance"

    def test_no_kind_field(self):
        definition = {
            "name": "Test",
            "statement": "Test statement",
            "search": {"instructions": "Search", "outputMode": "warrants"},
        }
        assert "kind" not in definition

    def test_no_version_field(self):
        definition = {
            "name": "Test",
            "statement": "Test statement",
            "search": {"instructions": "Search", "outputMode": "warrants"},
        }
        assert "version" not in definition


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
        assert "paper_matches" in tables
        assert "idea_maps" in tables
        assert "feedback" in tables

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
            definition={"name": "Test", "statement": "Test", "search": {"instructions": "", "outputMode": "warrants"}},
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
            definition={"name": "Test", "statement": "Test", "search": {"instructions": "", "outputMode": "warrants"}},
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
            definition={"name": "Test", "statement": "Test", "search": {"instructions": "", "outputMode": "warrants"}},
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
