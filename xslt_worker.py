# /// script
# requires-python = ">=3.13"
# dependencies = [
#     "vgi-python[http]>=0.16.0",
#     "saxonche>=13.0",
# ]
# ///
"""Repo-root PEP 723 shim for the vgi-xslt worker.

The worker definition (the ``xslt`` catalog, :class:`XsltWorker`, and
:func:`main`) lives in the wheel-importable :mod:`vgi_xslt.worker`. This file is
kept as a thin PEP 723 entry point so ``uv run xslt_worker.py`` (Makefile,
ci/run-integration.sh, and the subprocess tests) resolves the inline deps and
serves the worker exactly as before, while the built wheel carries the same
worker for the ``vgi-xslt-worker`` console script and the container image.

Running this script adds the repo root to ``sys.path``, so ``vgi_xslt`` imports
resolve even under ``uv run`` (which does not install the local package).

Usage::

    uv run xslt_worker.py               # serve over stdio (DuckDB subprocess)

    INSTALL vgi FROM community; LOAD vgi;
    ATTACH 'xslt' (TYPE vgi, LOCATION 'uv run xslt_worker.py');
"""

from __future__ import annotations

from vgi_xslt.worker import _XSLT_CATALOG, XsltWorker, main

__all__ = ["XsltWorker", "_XSLT_CATALOG", "main"]


if __name__ == "__main__":
    main()
