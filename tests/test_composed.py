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
