"""Shared per-object discovery/description metadata for the xslt worker.

The ``vgi-lint-check`` strict profile expects a consistent set of
discovery/description tags on **every** function and table:

- ``vgi.title`` (VGI124)        -- human-friendly display name (must NOT
  normalize-equal the machine name, so add a descriptive extra word)
- ``vgi.doc_llm`` (VGI112)      -- a Markdown narrative aimed at LLMs/agents
- ``vgi.doc_md`` (VGI113)       -- a Markdown narrative aimed at human docs
  (must be DISTINCT content from ``vgi.doc_llm``)
- ``vgi.keywords`` (VGI126/VGI138) -- a JSON array of search terms/synonyms,
  e.g. ``["a", "b"]`` (NOT a comma-separated string)

Note: ``vgi.source_url`` is set only on the catalog object (VGI139 warns
against per-object ``vgi.source_url``), so ``object_tags`` no longer emits it.

``object_tags(...)`` builds the four per-object tags at once.
"""

from __future__ import annotations

import json
from collections.abc import Sequence

#: Base GitHub blob URL for source files in this repo (pinned to ``main``).
SOURCE_BASE = "https://github.com/Query-farm/vgi-xslt/blob/main"


def keywords_json(keywords: Sequence[str]) -> str:
    """Serialize search keywords as a JSON array string (VGI138).

    ``vgi.keywords`` must be a JSON array of strings (``["a", "b"]``), not a
    comma-separated string.
    """
    return json.dumps(list(keywords))


def example_queries_json(examples: Sequence[tuple[str, str]]) -> str:
    """Serialize described example queries as a JSON array string (VGI515).

    Each element is a ``(description, sql)`` pair rendered as a
    ``{"description": ..., "sql": ...}`` object. ``vgi.example_queries`` is the
    executed, coverage-checked, description-carrying example carrier: the native
    ``duckdb_functions().examples`` slot drops the description, so every object's
    runnable examples live here with a non-empty description each.
    """
    return json.dumps([{"description": d, "sql": s} for d, s in examples])


def object_tags(
    *,
    title: str,
    doc_llm: str,
    doc_md: str,
    keywords: Sequence[str],
    category: str,
    examples: Sequence[tuple[str, str]],
) -> dict[str, str]:
    """Build the standard per-object discovery/description tags.

    ``keywords`` is a sequence of search terms serialized to a JSON array
    (VGI138). ``category`` is the name of one of the schema's ``vgi.categories``
    entries (VGI413) -- it groups the object in the worker's navigation/listing.
    ``examples`` is a sequence of ``(description, sql)`` pairs emitted as the
    ``vgi.example_queries`` described-example carrier (VGI515). ``vgi.source_url``
    is intentionally omitted -- it belongs only on the catalog object (VGI139).
    """
    return {
        "vgi.title": title,
        "vgi.doc_llm": doc_llm,
        "vgi.doc_md": doc_md,
        "vgi.keywords": keywords_json(keywords),
        # VGI413: classify the object into one of the schema's vgi.categories.
        "vgi.category": category,
        # VGI515: described, executed, coverage-checked example queries.
        "vgi.example_queries": example_queries_json(examples),
    }
