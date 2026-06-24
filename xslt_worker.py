# /// script
# requires-python = ">=3.13"
# dependencies = [
#     "vgi-python[http]>=0.8.4",
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

_CATALOG_DESCRIPTION_LLM = (
    "Transform, query, and shred XML in SQL using XSLT 3.0, XQuery 3.1, and XPath 3.1, backed by "
    "SaxonC-HE. Apply an XSLT stylesheet to a document (xslt), pull the string/boolean/numeric value "
    "of an XPath expression (xpath_string / xpath_boolean / xpath_number), collect every XPath match "
    "into a list to UNNEST into rows (xpath_array), run an XQuery with the document as context item "
    "(xquery), check whether text is well-formed XML (is_well_formed), and explode one document into "
    "rows via the table functions xpath_nodes (per XPath match) and xquery_rows (per XQuery sequence "
    "item). Use for XML extraction/transformation, shredding XML into relational rows, and "
    "well-formedness checks. Note: SaxonC-HE is not schema-aware, so there is no XSD validation."
)

_CATALOG_DESCRIPTION_MD = (
    "# xslt\n\n"
    "XSLT 3.0 / XQuery 3.1 / XPath 3.1 over XML for SQL, backed by SaxonC-HE.\n\n"
    "**Scalars:** `xslt` (transform), `xpath_string`, `xpath_boolean`, `xpath_number`, "
    "`xpath_array` (UNNEST to shred), `xquery`, `is_well_formed`.\n\n"
    "**Table functions:** `xpath_nodes` (one row per XPath match), `xquery_rows` (one row per "
    "XQuery result item), `saxon_version` (the SaxonC version)."
)

_SCHEMA_DESCRIPTION_LLM = (
    "XSLT/XQuery/XPath functions over XML: transform documents, evaluate XPath to string/boolean/"
    "number/list, run XQuery, test well-formedness, and shred a document into rows. Scalars: "
    "`xslt`, `xpath_string`, `xpath_boolean`, `xpath_number`, `xpath_array`, `xquery`, "
    "`is_well_formed`. Table functions: `xpath_nodes`, `xquery_rows`, `saxon_version`."
)

_SCHEMA_DESCRIPTION_MD = (
    "# main\n\n"
    "XSLT 3.0 / XQuery 3.1 / XPath 3.1 functions over XML, backed by SaxonC-HE.\n\n"
    "Use the scalars (`xslt`, `xpath_string`, `xpath_boolean`, `xpath_number`, `xpath_array`, "
    "`xquery`, `is_well_formed`) for per-row work, and the table functions (`xpath_nodes`, "
    "`xquery_rows`, `saxon_version`) to explode one document into rows."
)

_SCHEMA_KEYWORDS = (
    "xslt, xquery, xpath, xml, transform, shred, query xml, well-formed, saxon, "
    "xpath_string, xpath_array, xquery_rows, xpath_nodes"
)

_SCHEMA_EXAMPLE_QUERIES = (
    "SELECT xslt.main.xpath_string('<r><a>x</a></r>', '//a');\n"
    "SELECT xslt.main.xpath_boolean('<r><a/></r>', 'count(//a) = 1');\n"
    "SELECT xslt.main.xpath_number('<r><n>42</n></r>', 'number(//n)');\n"
    "SELECT UNNEST(xslt.main.xpath_array('<r><i>a</i><i>b</i></r>', '//i'));\n"
    "SELECT xslt.main.xquery('<r><i>a</i><i>b</i></r>', 'string-join(//i, \",\")');\n"
    "SELECT xslt.main.is_well_formed('<a></a>');\n"
    "SELECT * FROM xslt.main.xpath_nodes('<r><i>a</i><i>b</i></r>', '//i');\n"
    "SELECT * FROM xslt.main.saxon_version();"
)

_PROVENANCE_TAGS = {
    "vgi.author": "Query.Farm",
    "vgi.copyright": "Copyright 2026 Query Farm LLC - https://query.farm",
    "vgi.license": "MIT",
    "vgi.support_contact": "https://github.com/Query-farm/vgi-xslt/issues",
    "vgi.support_policy_url": "https://github.com/Query-farm/vgi-xslt/blob/main/README.md",
}

_XSLT_CATALOG = Catalog(
    name="xslt",
    default_schema="main",
    comment="XSLT 3.0 / XQuery 3.1 / XPath 3.1 over XML for SQL (SaxonC-HE).",
    source_url="https://github.com/Query-farm/vgi-xslt",
    tags={
        "vgi.title": "XSLT, XQuery & XPath for XML",
        "vgi.keywords": (
            "xslt, xquery, xpath, xml, transform, shred, query xml, well-formed, "
            "saxon, stylesheet, flwor, xml processing"
        ),
        "vgi.doc_llm": _CATALOG_DESCRIPTION_LLM,
        "vgi.doc_md": _CATALOG_DESCRIPTION_MD,
        **_PROVENANCE_TAGS,
    },
    schemas=[
        Schema(
            name="main",
            comment="XSLT 3.0 / XQuery 3.1 / XPath 3.1 over XML for SQL (SaxonC-HE)",
            tags={
                "vgi.title": "XSLT — main",
                "vgi.keywords": _SCHEMA_KEYWORDS,
                # VGI123 classifying tags use BARE keys (not vgi.-namespaced).
                "domain": "xml",
                "category": "xml-processing",
                "topic": "xslt-xquery-xpath",
                "vgi.source_url": "https://github.com/Query-farm/vgi-xslt/blob/main/xslt_worker.py",
                "vgi.doc_llm": _SCHEMA_DESCRIPTION_LLM,
                "vgi.doc_md": _SCHEMA_DESCRIPTION_MD,
                # VGI506 representative example queries for the schema.
                "vgi.example_queries": _SCHEMA_EXAMPLE_QUERIES,
            },
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
