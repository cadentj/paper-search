"""Backend unit tests."""

import pytest
from bs4 import BeautifulSoup

from app.utils.html_parser import (
    blocks_to_prompt_text,
    parse_arxiv_html,
    prepare_arxiv_html_for_viewer,
    validate_citation,
)


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
        for i, b in enumerate(blocks):
            assert b.block_id == f"B{i:03d}"
            assert b.text
            assert len(b.text) >= 10
        sections = [b.section_title for b in blocks if b.section_title]
        assert any("Introduction" in s for s in sections) or any("Methods" in s for s in sections)
        assert blocks[0].html_anchor == "#title"

    def test_prepares_viewer_html_with_canonical_block_markers(self):
        html = prepare_arxiv_html_for_viewer(self.SAMPLE_HTML)
        assert 'data-paper-block-id="B000"' in html
        assert 'data-paper-block-id="B001"' in html
        assert 'id="title"' in html

    def test_prepares_viewer_html_preserves_arxiv_chrome(self):
        source = """
        <html>
        <head><title>Paper</title></head>
        <body>
            <header class="arxiv-html-header">arXiv header</header>
            <article>
                <h1 id="title">A Paper Title With Enough Text</h1>
                <p id="para1">This paragraph has enough text to become addressable.</p>
            </article>
            <div id="beta-badge">BETA</div>
        </body>
        </html>
        """
        html = prepare_arxiv_html_for_viewer(source)

        assert "arxiv-html-header" in html
        assert 'id="beta-badge"' in html

    def test_prepares_viewer_html_replaces_existing_base(self):
        source = """
        <html>
        <head><base href="https://r2.example/data/2012/2012.14425.html"></head>
        <body>
            <base href="https://r2.example/duplicate-base.html">
            <p id="para1">This paragraph has enough text to become addressable.</p>
        </body>
        </html>
        """
        html = prepare_arxiv_html_for_viewer(
            source,
            "https://arxiv.org/html/2012.14425",
        )
        soup = BeautifulSoup(html, "lxml")
        bases = soup.select("base")

        assert len(bases) == 1
        assert bases[0]["href"] == "https://arxiv.org/html/2012.14425"


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
            blocks, {"startBlockId": "B000", "endBlockId": "B000"}
        ) is True
        assert validate_citation(
            blocks, {"startBlockId": "B000", "endBlockId": "B001"}
        ) is True

    def test_rejects_invalid_block_ranges(self):
        blocks = parse_arxiv_html(self.SAMPLE_HTML)
        assert validate_citation(
            blocks, {"startBlockId": "nonexistent", "endBlockId": "B001"}
        ) is False
        assert validate_citation(
            blocks, {"startBlockId": "B000", "endBlockId": "nonexistent"}
        ) is False
        assert validate_citation(
            blocks, {"startBlockId": "B001", "endBlockId": "B000"}
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
        assert "B000" in text
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
