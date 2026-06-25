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
