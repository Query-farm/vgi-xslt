# /// script
# requires-python = ">=3.13"
# dependencies = [
#     "vgi-python>=0.8.3",
#     "saxonche>=13.0",
# ]
# ///
"""VGI worker bringing XSLT 3.0 / XQuery 3.1 / XPath 3.1 into DuckDB SQL.

Assembles the functions in ``vgi_xslt`` into a single ``xslt`` catalog and runs
the worker over stdio (DuckDB subprocess) or HTTP. Backed by SaxonC-HE via the
``saxonche`` Python bindings (a single ``PySaxonProcessor`` is held for the
process lifetime; compiled stylesheets/queries are cached -- see
``vgi_xslt/engine.py``).

Usage:
    uv run xslt_worker.py               # serve over stdio (DuckDB subprocess)

    INSTALL vgi FROM community; LOAD vgi;
    ATTACH 'xslt' (TYPE vgi, LOCATION 'uv run xslt_worker.py');

    SELECT xslt.xpath_string('<r><a>x</a></r>', '//a');         -- 'x'
    SELECT xslt.xpath_boolean('<r><a/></r>', 'count(//a) = 1'); -- true
    SELECT xslt.xpath_number('<r><n>42</n></r>', 'number(//n)');-- 42.0
    SELECT UNNEST(xslt.xpath_array('<r><i>a</i><i>b</i></r>', '//i'));  -- 'a','b'
    SELECT xslt.xquery('<r><i>a</i><i>b</i></r>', 'string-join(//i, ",")');
    SELECT xslt.is_well_formed('<a></a>');                      -- true
    SELECT * FROM xslt.xpath_nodes('<r><i>a</i><i>b</i></r>', '//i');
    SELECT * FROM xslt.saxon_version();
"""

from __future__ import annotations

from vgi import Worker
from vgi.catalog import Catalog, Schema

from vgi_xslt.scalars import SCALAR_FUNCTIONS
from vgi_xslt.tables import TABLE_FUNCTIONS

_FUNCTIONS: list[type] = [
    *SCALAR_FUNCTIONS,
    *TABLE_FUNCTIONS,
]

_XSLT_CATALOG = Catalog(
    name="xslt",
    default_schema="main",
    schemas=[
        Schema(
            name="main",
            comment="XSLT 3.0 / XQuery 3.1 / XPath 3.1 over XML for SQL (SaxonC-HE)",
            functions=list(_FUNCTIONS),
        ),
    ],
)


class XsltWorker(Worker):
    """Worker process hosting the ``xslt`` catalog."""

    catalog = _XSLT_CATALOG


def main() -> None:
    """Run the xslt worker process (stdio or, via flags, HTTP)."""
    XsltWorker.main()


if __name__ == "__main__":
    main()
