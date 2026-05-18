from __future__ import annotations

from sqlalchemy import inspect, text


def ensure_runtime_schema(engine) -> None:
    if engine.dialect.name != "sqlite":
        return

    inspector = inspect(engine)
    if "papers" not in inspector.get_table_names():
        return

    paper_columns = {column["name"] for column in inspector.get_columns("papers")}
    paper_additions = {
        "source_type": "TEXT NOT NULL DEFAULT 'arxiv'",
        "source_id": "TEXT",
        "source_url": "TEXT",
        "source_metadata": "JSON NOT NULL DEFAULT '{}'",
        "search_text": "TEXT NOT NULL DEFAULT ''",
    }
    search_run_columns = {
        column["name"] for column in inspector.get_columns("search_runs")
    } if "search_runs" in inspector.get_table_names() else set()

    with engine.begin() as conn:
        for name, definition in paper_additions.items():
            if name not in paper_columns:
                conn.execute(text(f"ALTER TABLE papers ADD COLUMN {name} {definition}"))
        if "search_runs" in inspector.get_table_names() and "candidate_counts" not in search_run_columns:
            conn.execute(text("ALTER TABLE search_runs ADD COLUMN candidate_counts JSON"))
        conn.execute(
            text(
                "UPDATE papers "
                "SET source_type = COALESCE(source_type, 'arxiv'), "
                "source_id = COALESCE(source_id, arxiv_id), "
                "source_url = COALESCE(source_url, landing_url), "
                "source_metadata = COALESCE(source_metadata, '{}'), "
                "search_text = COALESCE(NULLIF(search_text, ''), abstract, '')"
            )
        )
