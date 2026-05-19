from paper_search_core.schemas.daily_search import (
    SUMMARY_MATCHES_TEXT_MAX_CHARS,
    PaperMatchPayload,
    PaperPayload,
)


def _match(*, text: str = "x", result: str = "relevant") -> PaperMatchPayload:
    return PaperMatchPayload(
        match_id="m1",
        paper=PaperPayload(
            id="p1",
            title="Title",
            source_type="arxiv",
            source_id="1",
            item_id="arxiv:1",
            text=text,
            authors=["A"],
        ),
        filter_name="Filter",
        filter_mode="topic",
        filter_description="desc",
        result=result,
    )


def test_format_grouped_for_summary_truncates_long_excerpts():
    long_text = "word " * 5000
    formatted = PaperMatchPayload.format_grouped_for_summary([_match(text=long_text)])
    assert len(formatted) < SUMMARY_MATCHES_TEXT_MAX_CHARS + 100
    assert "Excerpt: word word" in formatted
    assert formatted.count("word") < 5000


def test_format_grouped_for_summary_caps_total_length():
    matches = [_match(text="z " * 2000, result="r " * 500) for _ in range(40)]
    formatted = PaperMatchPayload.format_grouped_for_summary(matches)
    assert len(formatted) <= SUMMARY_MATCHES_TEXT_MAX_CHARS + 10
    assert "truncated for length" in formatted
