from app.llm.summary_stream import extract_complete_summary, extract_partial_summary


def test_extract_partial_summary_returns_none_before_field():
    assert extract_partial_summary("") is None
    assert extract_partial_summary('{"citations": []}') is None


def test_extract_partial_summary_mid_string():
    buffer = '{"summary": "CLAIMS\\n\\nFilter'
    assert extract_partial_summary(buffer) == "CLAIMS\n\nFilter"


def test_extract_partial_summary_handles_escapes():
    buffer = '{"summary": "Line one\\nLine two\\", \\"trailing'
    assert extract_partial_summary(buffer) == 'Line one\nLine two", "trailing'


def test_extract_partial_summary_after_citations_started():
    buffer = '{"summary": "Done with summary", "citations": [{"itemId": "arxiv:1"'
    assert extract_partial_summary(buffer) == "Done with summary"


def test_extract_complete_summary():
    buffer = (
        '{"summary": "Final text", "citations": [{"itemId": "arxiv:1", '
        '"sourceType": "arxiv", "sourceId": "1", "paperMatchId": "m1", '
        '"citedFor": "claim"}]}'
    )
    assert extract_complete_summary(buffer) == "Final text"
