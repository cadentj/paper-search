from app.llm.partial_json import complete_array_items


def test_complete_array_items_returns_complete_objects_before_stream_finishes():
    buffer = (
        '{"claims": ['
        '{"id": "c1", "text": "First"},'
        '{"id": "c2", "text": "Second"},'
        '{"id": "c3"'
    )

    items = complete_array_items(buffer, "claims", lambda item: item)

    assert items == [
        {"id": "c1", "text": "First"},
        {"id": "c2", "text": "Second"},
    ]


def test_complete_array_items_skips_items_rejected_by_normalizer():
    buffer = '{"warrants": [{"id": "w1"}, {"bad": true}]}'

    items = complete_array_items(
        buffer,
        "warrants",
        lambda item: item if "id" in item else None,
    )

    assert items == [{"id": "w1"}]
