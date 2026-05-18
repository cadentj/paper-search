"""Backend unit tests."""

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

    def test_parses_addressable_blocks_with_sections_and_stable_anchors(self):
        blocks = parse_arxiv_html(self.SAMPLE_HTML)
        assert len(blocks) > 0
        for b in blocks:
            assert b.block_id
            assert b.text
            assert b.html_anchor.startswith("#")
            assert len(b.text) >= 10
        sections = [b.section_title for b in blocks if b.section_title]
        assert any("Introduction" in s for s in sections) or any("Methods" in s for s in sections)
        ids_with_existing = [b for b in blocks if not b.block_id.startswith("block-")]
        assert len(ids_with_existing) > 0


class TestCitationValidation:
    SAMPLE_HTML = """
    <html><body>
        <p id="p1">The transformer architecture uses self-attention mechanisms to process sequences in parallel.</p>
        <p id="p2">Experiments show a 15% improvement over baseline methods on standard benchmarks.</p>
    </body></html>
    """

    def test_accepts_valid_block_ranges(self):
        blocks = parse_arxiv_html(self.SAMPLE_HTML)
        assert validate_citation(
            blocks, {"startBlockId": "p1", "endBlockId": "p1"}
        ) is True
        assert validate_citation(
            blocks, {"startBlockId": "p1", "endBlockId": "p2"}
        ) is True

    def test_rejects_invalid_block_ranges(self):
        blocks = parse_arxiv_html(self.SAMPLE_HTML)
        assert validate_citation(
            blocks, {"startBlockId": "nonexistent", "endBlockId": "p2"}
        ) is False
        assert validate_citation(
            blocks, {"startBlockId": "p1", "endBlockId": "nonexistent"}
        ) is False
        assert validate_citation(
            blocks, {"startBlockId": "p2", "endBlockId": "p1"}
        ) is False


class TestBlocksToPromptText:
    def test_converts_blocks_to_text_and_respects_limit(self):
        html = "<html><body>" + "".join(
            f"<p id='p{i}'>This is paragraph number {i} with enough text to pass the filter.</p>"
            for i in range(20)
        ) + "</body></html>"
        blocks = parse_arxiv_html(html)
        text = blocks_to_prompt_text(blocks, max_blocks=5)
        lines = [l for l in text.split("\n\n") if l.strip()]
        assert "p0" in text
        assert "paragraph" in text
        assert len(lines) <= 5


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

    def test_llm_config_rejects_missing_and_unknown_profiles(self, tmp_path):
        from app.llm.config import load_llm_config
        from app.llm.config import get_llm_config

        config_path = tmp_path / "llm_config.toml"
        config_path.write_text(
            '[filter_generation]\nmodel = "model"\nprovider = "provider"\n'
        )

        with pytest.raises(RuntimeError, match=r"Missing LLM config group \[judge\]"):
            load_llm_config(config_path)

        with pytest.raises(RuntimeError, match="Unknown LLM config profile"):
            get_llm_config("missing")

    @pytest.mark.asyncio
    async def test_async_call_llm_retries_transient_status(self, monkeypatch):
        import httpx
        from types import SimpleNamespace

        from app.llm import client as llm_client
        from app.llm.config import FILTER_GENERATION_PROFILE
        from app.llm.schemas import FilterSearchResponse

        request = httpx.Request("POST", "https://openrouter.ai/api/v1/responses")
        attempts = {"count": 0}
        parse_calls = []

        parsed = FilterSearchResponse(matches=[])
        parsed_response = SimpleNamespace(
            id="response-id",
            model="test-model",
            output=[
                SimpleNamespace(
                    content=[
                        SimpleNamespace(parsed=parsed),
                    ]
                )
            ],
        )

        class FakeResponses:
            async def parse(self, **kwargs):
                attempts["count"] += 1
                parse_calls.append(kwargs)
                if attempts["count"] == 1:
                    raise llm_client.APIConnectionError(request=request)
                return parsed_response

        class FakeAsyncClient:
            responses = FakeResponses()

            async def __aenter__(self):
                return self

            async def __aexit__(self, *args):
                return None

        async def fake_sleep(delay):
            return None

        monkeypatch.setattr(llm_client.settings, "OPENROUTER_API_KEY", "test-key")
        monkeypatch.setattr(llm_client, "LLM_MAX_RETRIES", 1)
        monkeypatch.setattr(llm_client, "LLM_RETRY_BASE_SECONDS", 0)
        monkeypatch.setattr(llm_client.asyncio, "sleep", fake_sleep)
        monkeypatch.setattr(llm_client, "_async_client", lambda: FakeAsyncClient())

        result = await llm_client.async_call_llm(
            "system",
            "user",
            response_model=FilterSearchResponse,
            profile=FILTER_GENERATION_PROFILE,
        )

        assert attempts["count"] == 2
        assert parse_calls[0]["model"] == "openai/gpt-oss-120b"
        assert parse_calls[0]["extra_body"] == {"provider": {"order": ["cerebras"]}}
        assert parse_calls[0]["text_format"] is FilterSearchResponse
        assert result["content"] == {"matches": []}
        assert result["model"] == "test-model"
