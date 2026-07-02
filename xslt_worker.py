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
    "This extension turns DuckDB into an XML processing engine. Instead of exporting data to a "
    "separate XSLT/XQuery toolchain, you can apply stylesheets, evaluate XPath expressions, run "
    "XQuery FLWOR programs, and explode XML documents into relational rows without ever leaving "
    "SQL. It is built for data engineers and analysts who land XML in columns -- SOAP/EDI "
    "payloads, RSS/Atom feeds, OOXML and SVG fragments, scientific and financial document "
    "formats -- and need to extract, reshape, or validate that markup at query time, row by row, "
    "with NULLs passed through cleanly.\n\n"
    "## Key concepts\n\n"
    "- **Per-row scalars vs. set-returning table functions.** Scalars compute one value per row "
    "(a string, boolean, number, or list); table functions and the array-plus-UNNEST pattern "
    "explode a single document into many rows -- the natural way to *shred* XML into a relational "
    "result.\n"
    "- **Transform, query, and validate.** XSLT reshapes documents, XPath and XQuery pull values "
    "out of them, and a well-formedness check lets you filter malformed rows before processing.\n"
    "- **NULL / invalid / error.** A NULL input yields NULL output (or no rows); malformed XML or "
    "a bad stylesheet/expression raises a clean DuckDB error, so bad data never crashes the "
    "worker.\n\n"
    "## When to use it\n\n"
    "Reach for this worker whenever XML lands in a DuckDB column and you need to read a value out "
    "of it, transform it into another shape, or normalize its repeated structure into rows for "
    "downstream SQL. List the schema to discover the available functions and their signatures.\n\n"
    "## Under the hood\n\n"
    "The worker is backed by [SaxonC-HE](https://www.saxonica.com/), the free Home Edition of "
    "[Saxonica](https://www.saxonica.com/)'s Saxon processor -- the reference implementation for "
    "XSLT 3.0 / XQuery 3.1 / XPath 3.1 -- via the "
    "[saxonche](https://pypi.org/project/saxonche/) Python bindings. A single native Saxon "
    "processor is booted once per worker and reused; compiled stylesheets and queries are cached "
    "on their source text, so a constant stylesheet applied down a column compiles once and "
    "transforms many rows. Note that SaxonC-HE is not schema-aware, so there is no XSD "
    "validation; the well-formedness check provides the strongest guarantee the free edition "
    "offers.\n\n"
    "## Learn more\n\n"
    "- [Saxonica homepage](https://www.saxonica.com/)\n"
    "- [Saxon documentation](https://www.saxonica.com/documentation/index.html)\n"
    "- [Saxon-HE source on GitHub](https://github.com/Saxonica/Saxon-HE)\n"
    "- [`saxonche` on PyPI](https://pypi.org/project/saxonche/)\n"
    "- W3C specs: [XSLT 3.0](https://www.w3.org/TR/xslt-30/), "
    "[XPath 3.1](https://www.w3.org/TR/xpath-31/), [XQuery 3.1](https://www.w3.org/TR/xquery-31/)"
)

_SCHEMA_DESCRIPTION_LLM = (
    "XSLT 3.0 / XQuery 3.1 / XPath 3.1 processing over XML, backed by SaxonC-HE. The functions "
    "here fall into a few groups: transform a document with a stylesheet, evaluate an expression "
    "to a single value (text, boolean, or number), and shred a document into many rows -- either "
    "per-row via an array you UNNEST, or as a set-returning table function. A well-formedness "
    "check lets you filter malformed input first. Per-row scalars pass NULLs through; malformed "
    "XML or expressions raise a clean error. List the schema to see each function and its "
    "signature."
)

_SCHEMA_DESCRIPTION_MD = (
    "# main\n\n"
    "XSLT 3.0 / XQuery 3.1 / XPath 3.1 processing over XML, backed by SaxonC-HE.\n\n"
    "The functions in this schema group into four capabilities:\n\n"
    "- **Transform** an XML document with an XSLT 3.0 stylesheet.\n"
    "- **Query** a document with XPath or XQuery to pull out a string, boolean, or numeric "
    "value.\n"
    "- **Shred** a document into relational rows -- per row via an array you UNNEST, or via a "
    "set-returning table function.\n"
    "- **Validate** that text is well-formed XML before you process it.\n\n"
    "List the schema to discover the individual functions, their arguments, and worked examples."
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

# VGI413: an ordered category registry for the schema. Every function/table
# carries a `vgi.category` naming exactly one of these; the registry drives the
# worker's navigation, listing sections, and SEO descriptions.
_SCHEMA_CATEGORIES = json.dumps(
    [
        {
            "name": "transform",
            "description": "Apply XSLT 3.0 stylesheets to reshape or rewrite XML documents.",
        },
        {
            "name": "query",
            "description": "Evaluate XPath 3.1 / XQuery 3.1 expressions to pull a value out of a document.",
        },
        {
            "name": "shred",
            "description": "Explode one XML document into relational rows for downstream SQL.",
        },
        {
            "name": "validate",
            "description": "Check whether text parses as well-formed XML.",
        },
        {
            "name": "diagnostics",
            "description": "Worker and Saxon engine discovery and version info.",
        },
    ]
)

# A small, self-contained XSLT 3.0 stylesheet reused by the agent task suite: it
# lifts the //name value into a <hello> wrapper.
_TASK_STYLESHEET = (
    '<xsl:stylesheet version="3.0" xmlns:xsl="http://www.w3.org/1999/XSL/Transform">'
    '<xsl:template match="/"><hello><xsl:value-of select="//name"/></hello></xsl:template>'
    "</xsl:stylesheet>"
)

# VGI152: a fixed analyst-task suite so `vgi-lint simulate` (and the --ai
# agent-check) can measure how well an agent actually uses this worker. Each task
# gives the analyst only a `prompt`; `reference_sql` is the grader-only canonical
# solution (run live in the same engine, so version/serialization match exactly).
# Row-returning tasks set `unordered` + `ignore_column_names` so a correct answer
# with different aliasing/ordering still grades as a pass.
_AGENT_TEST_TASKS = json.dumps(
    [
        {
            "name": "extract-title-text",
            "prompt": (
                "The XML document '<book><title>Dune</title><author>Herbert</author></book>' is "
                "stored as a string. Return the text of the <title> element."
            ),
            "reference_sql": (
                "SELECT xslt.main.xpath_string('<book><title>Dune</title><author>Herbert</author></book>', '//title')"
            ),
            "ignore_column_names": True,
        },
        {
            "name": "count-item-elements",
            "prompt": (
                "For the XML '<list><item>a</item><item>b</item><item>c</item></list>', return the "
                "number of <item> elements it contains, as a number."
            ),
            "reference_sql": (
                "SELECT xslt.main.xpath_number("
                "'<list><item>a</item><item>b</item><item>c</item></list>', 'count(//item)')"
            ),
            "ignore_column_names": True,
        },
        {
            "name": "test-element-presence",
            "prompt": (
                "For the XML '<config><debug/></config>', return TRUE if it contains at least one "
                "<debug> element and FALSE otherwise."
            ),
            "reference_sql": "SELECT xslt.main.xpath_boolean('<config><debug/></config>', 'boolean(//debug)')",
            "ignore_column_names": True,
        },
        {
            "name": "collect-match-array",
            "prompt": (
                "Write and run a single SQL query that, for the XML "
                "'<colors><c>red</c><c>green</c><c>blue</c></colors>', returns the text of every "
                "<c> element collected into one list/array value."
            ),
            "reference_sql": (
                "SELECT xslt.main.xpath_array('<colors><c>red</c><c>green</c><c>blue</c></colors>', '//c')"
            ),
            "ignore_column_names": True,
        },
        {
            "name": "shred-nodes-to-rows",
            "prompt": (
                "Write and run a single SQL query that explodes the XML "
                "'<colors><c>red</c><c>green</c><c>blue</c></colors>' into one row per <c> element. "
                "Select all columns the matching table function returns (its 1-based position and "
                "the matched text value)."
            ),
            "reference_sql": (
                "SELECT * FROM xslt.main.xpath_nodes('<colors><c>red</c><c>green</c><c>blue</c></colors>', '//c')"
            ),
            "unordered": True,
            "ignore_column_names": True,
        },
        {
            "name": "join-number-values",
            "prompt": (
                "For the XML '<nums><n>1</n><n>2</n><n>3</n></nums>', return a single string that "
                "joins the text of all <n> elements separated by hyphens (for example, 1-2-3)."
            ),
            "reference_sql": (
                "SELECT xslt.main.xquery('<nums><n>1</n><n>2</n><n>3</n></nums>', 'string-join(//n, \"-\")')"
            ),
            "ignore_column_names": True,
        },
        {
            "name": "xquery-rows-sequence",
            "prompt": (
                "Write and run a single SQL query that, using an XQuery selecting every <n> "
                "element (the XQuery expression '//n'), explodes the XML "
                "'<nums><n>1</n><n>2</n><n>3</n></nums>' into one row per <n> element. Select all "
                "columns the matching table function returns (its 1-based position and the item's "
                "text value)."
            ),
            "reference_sql": ("SELECT * FROM xslt.main.xquery_rows('<nums><n>1</n><n>2</n><n>3</n></nums>', '//n')"),
            "unordered": True,
            "ignore_column_names": True,
        },
        {
            "name": "detect-malformed-xml",
            "prompt": (
                "Determine whether the string '<a><b></a>' is well-formed XML. Return TRUE if it "
                "is well-formed and FALSE if it is malformed."
            ),
            "reference_sql": "SELECT xslt.main.is_well_formed('<a><b></a>')",
            "ignore_column_names": True,
        },
        {
            "name": "transform-with-stylesheet",
            "prompt": (
                "Apply the following XSLT 3.0 stylesheet to the document "
                "'<greeting><name>World</name></greeting>' and return the serialized result.\n\n"
                f"Stylesheet:\n{_TASK_STYLESHEET}"
            ),
            "reference_sql": (
                f"SELECT xslt.main.xslt('<greeting><name>World</name></greeting>', '{_TASK_STYLESHEET}')"
            ),
            "ignore_column_names": True,
        },
        {
            "name": "report-engine-version",
            "prompt": (
                "Return the SaxonC engine version string that backs this worker, to confirm the worker is reachable."
            ),
            "reference_sql": "SELECT version FROM xslt.main.saxon_version()",
            "ignore_column_names": True,
        },
    ]
)

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
    # VGI413 category (names one of the schema's vgi.categories entries).
    "vgi.category": "diagnostics",
    "vgi.doc_llm": (
        "## saxon_version (table)\n\n"
        "A single-row table exposing the **SaxonC version string** that backs this worker's "
        "XSLT/XQuery/XPath engine.\n\n"
        "**When to use:** discovery and diagnostics — confirm the worker is reachable and reveal "
        "which SaxonC-HE build is in use before relying on version-specific XSLT 3.0 / "
        "XQuery 3.1 behavior.\n\n"
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
        # VGI152: fixed analyst-task suite for `vgi-lint simulate` / the agent-check.
        "vgi.agent_test_tasks": _AGENT_TEST_TASKS,
        **_PROVENANCE_TAGS,
    },
    schemas=[
        Schema(
            name="main",
            comment="XSLT 3.0 / XQuery 3.1 / XPath 3.1 over XML for SQL (SaxonC-HE)",
            tags={
                "vgi.title": "XSLT — main",
                "vgi.keywords": _SCHEMA_KEYWORDS,
                # VGI413: ordered category registry; each object names one via vgi.category.
                "vgi.categories": _SCHEMA_CATEGORIES,
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
