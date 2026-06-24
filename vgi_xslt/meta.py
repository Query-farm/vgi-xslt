"""Shared per-object discovery/description metadata for the xslt worker.

The ``vgi-lint-check`` strict profile (0.26.0) expects a consistent set of
discovery/description tags on **every** function and table:

- ``vgi.title`` (VGI124)        -- human-friendly display name (must NOT
  normalize-equal the machine name, so add a descriptive extra word)
- ``vgi.doc_llm`` (VGI112)      -- a Markdown narrative aimed at LLMs/agents
- ``vgi.doc_md`` (VGI113)       -- a Markdown narrative aimed at human docs
  (must be DISTINCT content from ``vgi.doc_llm``)
- ``vgi.keywords`` (VGI126)     -- comma-separated search terms/synonyms
- ``vgi.source_url`` (VGI128)   -- link to the implementing source file

``object_tags(...)`` builds all five at once; ``source_url(file)`` builds the
canonical GitHub blob URL (pinned to ``main``).
"""

from __future__ import annotations

#: Base GitHub blob URL for source files in this repo (pinned to ``main``).
SOURCE_BASE = "https://github.com/Query-farm/vgi-xslt/blob/main"


def source_url(relative_path: str) -> str:
    """Build the implementation ``vgi.source_url`` for a file in the repo.

    ``relative_path`` is relative to the repository root, e.g.
    ``source_url("vgi_xslt/scalars.py")``.
    """
    return f"{SOURCE_BASE}/{relative_path}"


def object_tags(
    *,
    title: str,
    doc_llm: str,
    doc_md: str,
    keywords: str,
    relative_path: str,
) -> dict[str, str]:
    """Build the five standard per-object discovery/description tags.

    ``relative_path`` is the implementing file relative to the repo root.
    """
    return {
        "vgi.title": title,
        "vgi.doc_llm": doc_llm,
        "vgi.doc_md": doc_md,
        "vgi.keywords": keywords,
        "vgi.source_url": source_url(relative_path),
    }
