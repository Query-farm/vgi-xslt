"""Bring XSLT 3.0 / XQuery 3.1 / XPath 3.1 into DuckDB SQL as a VGI worker.

The implementation is split so each concern stays focused:

- ``engine``  -- pure Saxon primitives: the process-wide ``PySaxonProcessor``
  singleton, the compile caches, and the string-in / string-out transform /
  query / XPath functions. The only module that imports ``saxonche``; no Arrow
  or VGI dependency, so it is directly unit-testable.
- ``scalars`` -- per-row VGI scalar functions (positional-only) wrapping the
  engine primitives over Arrow arrays.
- ``tables``  -- set-returning table functions (``xpath_nodes``, ``xquery_rows``,
  ``saxon_version``) that shred one document into many rows.

``xslt_worker.py`` at the repo root assembles these into the ``xslt`` catalog
and runs the worker over stdio (or HTTP).
"""

from __future__ import annotations

__version__ = "0.1.0"
