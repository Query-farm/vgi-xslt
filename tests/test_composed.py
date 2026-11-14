"""Keep the composed example SQL and its E2E pin in ``test/sql/composed.test`` in sync."""

from __future__ import annotations

import json
from pathlib import Path

from vgi_xslt import composed
from vgi_xslt.worker import _SCHEMA_EXAMPLE_QUERIES

_ROOT = Path(__file__).resolve().parent.parent


def test_every_composed_example_is_pinned_in_sql_suite() -> None:
    """Each composed SQL appears verbatim in the haybarn E2E file that checks its rows."""
    pinned = (_ROOT / "test" / "sql" / "composed.test").read_text()
    for description, sql in composed.ALL:
        assert description
        assert f"{sql};\n" in pinned, sql


def test_composed_examples_are_in_schema_list() -> None:
    """Every composed example is published at schema level."""
    published = json.loads(_SCHEMA_EXAMPLE_QUERIES)
    for description, sql in composed.ALL:
        assert {"description": description, "sql": sql} in published


def test_composed_agent_graders_are_pinned_in_sql_suite() -> None:
    """The composed agent-task graders in vgi-agent-tests.yaml appear verbatim in composed.test."""
    pinned = (_ROOT / "test" / "sql" / "composed.test").read_text()
    graders: dict[str, str] = {}
    name = ""
    for line in (_ROOT / "vgi-agent-tests.yaml").read_text().splitlines():
        stripped = line.strip()
        if stripped.startswith("- name:"):
            name = stripped.split(":", 1)[1].strip()
        elif stripped.startswith("reference_sql:"):
            graders[name] = json.loads(stripped.split(":", 1)[1].strip())
    for task in ("well-formed-orders-revenue", "books-over-ten"):
        assert f"# agent-task grader: {task}\n" in pinned, task
        assert f"{graders[task]};\n" in pinned, task
