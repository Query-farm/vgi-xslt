# /// script
# requires-python = ">=3.13"
# dependencies = [
#     "vgi-python[http]>=0.8.5",
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

import json

from vgi import Worker
from vgi.catalog import Catalog, Schema, Table

from vgi_xslt.scalars import SCALAR_FUNCTIONS
from vgi_xslt.tables import TABLE_FUNCTIONS, SaxonVersionFunction

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
    "# XSLT, XQuery & XPath for XML in SQL\n\n"
    "![Saxonica SaxonC-HE logo](https://avatars.githubusercontent.com/u/3630933?s=240&v=4)\n\n"
    "Transform, query, and shred XML directly in DuckDB SQL with full **XSLT 3.0**, "
    "**XQuery 3.1**, and **XPath 3.1** support, powered by the production-grade Saxon "
    "processor.\n\n"
    "The `xslt` extension turns DuckDB into an XML processing engine. Instead of exporting "
    "data to a separate XSLT/XQuery toolchain, you can apply stylesheets, evaluate XPath "
    "expressions, run XQuery FLWOR programs, and explode XML documents into relational rows "
    "without ever leaving SQL. It is built for data engineers and analysts who land XML in "
    "columns -- SOAP/EDI payloads, RSS/Atom feeds, OOXML and SVG fragments, scientific and "
    "financial document formats -- and need to extract, reshape, or validate that markup at "
    "query time, row by row, with NULLs passed through cleanly.\n\n"
    "Under the hood the worker is backed by [SaxonC-HE](https://www.saxonica.com/), the free "
    "Home Edition of [Saxonica](https://www.saxonica.com/)'s Saxon processor -- the reference "
    "implementation for XSLT 3.0 / XQuery 3.1 / XPath 3.1 -- via the "
    "[`saxonche`](https://pypi.org/project/saxonche/) Python bindings. A single native Saxon "
    "processor is booted once per worker and reused; compiled stylesheets and queries are "
    "cached on their source text, so a constant stylesheet applied down a column compiles once "
    "and transforms many rows. Note that SaxonC-HE is not schema-aware, so there is no XSD "
    "validation; `is_well_formed` provides the strongest well-formedness check the free edition "
    "offers.\n\n"
    "## Function surface\n\n"
    "**Scalar functions** operate per row: `xslt` applies an XSLT stylesheet to a document; "
    "`xpath_string`, `xpath_boolean`, and `xpath_number` evaluate an XPath expression and return "
    "its string, boolean, or numeric value; `xpath_array` collects every XPath match into a "
    "`VARCHAR[]` you can `UNNEST` to shred a document into rows; `xquery` runs an XQuery with the "
    "document as the context item; and `is_well_formed` tests whether text parses as well-formed "
    "XML.\n\n"
    "**Table functions** explode one document into many rows: `xpath_nodes` emits one row per "
    "XPath match, `xquery_rows` emits one row per item in an XQuery result sequence, and "
    "`saxon_version` reports the SaxonC build backing the worker (a handy connectivity smoke "
    "test).\n\n"
    "## Example\n\n"
    "```sql\n"
    "SELECT UNNEST(xslt.main.xpath_array('<r><i>a</i><i>b</i></r>', '//i'));  -- 'a', 'b'\n"
    "SELECT xslt.main.xpath_number('<r><n>42</n></r>', 'number(//n)');       -- 42.0\n"
    "SELECT * FROM xslt.main.xpath_nodes('<r><i>a</i><i>b</i></r>', '//i');\n"
    "```\n\n"
    "## Learn more\n\n"
    "- [Saxonica homepage](https://www.saxonica.com/)\n"
    "- [Saxon documentation](https://www.saxonica.com/documentation/index.html)\n"
    "- [Saxon-HE source on GitHub](https://github.com/Saxonica/Saxon-HE)\n"
    "- [`saxonche` on PyPI](https://pypi.org/project/saxonche/)\n"
    "- W3C specs: [XSLT 3.0](https://www.w3.org/TR/xslt-30/), "
    "[XPath 3.1](https://www.w3.org/TR/xpath-31/), [XQuery 3.1](https://www.w3.org/TR/xquery-31/)"
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

# VGI138: vgi.keywords must be a JSON array of strings, not a comma-separated string.
_CATALOG_KEYWORDS = json.dumps(
    [
        "xslt",
        "xquery",
        "xpath",
        "xml",
        "transform",
        "shred",
        "query xml",
        "well-formed",
        "saxon",
        "stylesheet",
        "flwor",
        "xml processing",
    ]
)

_SCHEMA_KEYWORDS = json.dumps(
    [
        "xslt",
        "xquery",
        "xpath",
        "xml",
        "transform",
        "shred",
        "query xml",
        "well-formed",
        "saxon",
        "xpath_string",
        "xpath_array",
        "xquery_rows",
        "xpath_nodes",
    ]
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

# Discovery/description tags for the `saxon_version` table (VGI311 exposes the
# parameterless `saxon_version` table function as a table). Tables need the same
# tag set as functions: title, doc_llm, doc_md, a classifying tag, keywords, and
# example queries.
_SAXON_VERSION_TABLE_TAGS = {
    "vgi.title": "Saxon Version Table",
    "vgi.keywords": json.dumps(
        ["saxon", "version", "discovery", "diagnostics", "engine", "info", "smoke test", "xslt"]
    ),
    # VGI123 classifying tags use BARE keys (not vgi.-namespaced).
    "domain": "xml",
    "category": "xml-processing",
    "topic": "xslt-xquery-xpath",
    "vgi.doc_llm": (
        "## saxon_version (table)\n\n"
        "A single-row table exposing the **SaxonC version string** that backs this worker's "
        "XSLT/XQuery/XPath engine.\n\n"
        "**When to use:** discovery and diagnostics — `SELECT * FROM xslt.main.saxon_version` "
        "confirms the worker is reachable and reveals which SaxonC-HE build is in use before "
        "relying on version-specific XSLT 3.0 / XQuery 3.1 behavior.\n\n"
        "**Columns:** `version` (VARCHAR) — the SaxonC version string.\n\n"
        "**Behavior:** always exactly one row; no inputs, so it is a safe smoke-test of the worker."
    ),
    "vgi.doc_md": (
        "# saxon_version\n\n"
        "Single-row table with the SaxonC version string backing the worker.\n\n"
        "## Usage\n\n"
        "```sql\n"
        "SELECT * FROM xslt.main.saxon_version;\n"
        "```\n\n"
        "## Notes\n\n"
        "- Always one row; no arguments.\n"
        "- Handy as a connectivity/version smoke-test."
    ),
    # VGI501/VGI502 example queries for the table: a JSON list of {description, sql}.
    "vgi.example_queries": json.dumps(
        [
            {
                "description": "Read just the SaxonC version string backing the worker.",
                "sql": "SELECT version FROM xslt.main.saxon_version;",
            },
            {
                "description": "Check whether the worker is running a SaxonC 13.x build.",
                "sql": "SELECT version, version LIKE '13.%' AS is_saxon_13 FROM xslt.main.saxon_version;",
            },
        ]
    ),
}

_XSLT_CATALOG = Catalog(
    name="xslt",
    default_schema="main",
    comment="XSLT 3.0 / XQuery 3.1 / XPath 3.1 over XML for SQL (SaxonC-HE).",
    source_url="https://github.com/Query-farm/vgi-xslt",
    tags={
        "vgi.title": "XSLT, XQuery & XPath for XML",
        "vgi.keywords": _CATALOG_KEYWORDS,
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
                # VGI139: vgi.source_url belongs only on the catalog object, not per-schema.
                "vgi.doc_llm": _SCHEMA_DESCRIPTION_LLM,
                "vgi.doc_md": _SCHEMA_DESCRIPTION_MD,
                # VGI506 representative example queries for the schema.
                "vgi.example_queries": _SCHEMA_EXAMPLE_QUERIES,
            },
            functions=list(_FUNCTIONS),
            # VGI311: a parameterless table function is also exposed as a table so
            # `SELECT * FROM xslt.main.saxon_version` resolves directly. The schema
            # is fixed (@bind_fixed_schema) and the function takes no arguments, so
            # the bind result is safe to inline for the catalog cache lifetime.
            tables=[
                Table(
                    name="saxon_version",
                    function=SaxonVersionFunction,
                    inline_bind=True,
                    comment="The SaxonC version string backing this worker (single row).",
                    # The version string uniquely identifies the single row (VGI807).
                    primary_key=(("version",),),
                    not_null=("version",),
                    tags=_SAXON_VERSION_TABLE_TAGS,
                ),
            ],
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
