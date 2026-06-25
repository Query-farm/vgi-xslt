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


def object_tags(
    *,
    title: str,
    doc_llm: str,
    doc_md: str,
    keywords: Sequence[str],
) -> dict[str, str]:
    """Build the four standard per-object discovery/description tags.

    ``keywords`` is a sequence of search terms serialized to a JSON array
    (VGI138). ``vgi.source_url`` is intentionally omitted -- it belongs only on
    the catalog object (VGI139).
    """
    return {
        "vgi.title": title,
        "vgi.doc_llm": doc_llm,
        "vgi.doc_md": doc_md,
        "vgi.keywords": keywords_json(keywords),
    }
