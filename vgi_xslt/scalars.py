"""Per-row scalar XSLT / XQuery / XPath functions.

Every function here is a true DuckDB **scalar** -- one value (per row) in, one
value out -- so it can be used inline in any projection or predicate:

    SELECT xslt(doc, $$<xsl:stylesheet .../>$$)         FROM documents;
    SELECT id, xpath_string(doc, '//title')             FROM documents;
    SELECT id, UNNEST(xpath_array(doc, '//item'))       FROM documents;  -- shred!

A note on argument syntax
-------------------------
VGI / DuckDB *scalar* functions take **positional** arguments only (the
``name := value`` named-argument syntax is a property of table functions and
macros, not scalars). Every function here is a fixed two-argument shape
(one is a single argument), so there are no arity overloads -- the document and
the stylesheet/expression/query are both positional ``Param`` columns.

NULL semantics
--------------
A NULL in either argument yields NULL output for that row (the row is skipped).
Invalid input -- malformed XML, a bad stylesheet/query, or a bad XPath
expression -- raises (surfaced as a clean DuckDB error), **except**
``is_well_formed``, which reports malformed XML as ``false`` rather than raising.

Set-returning functions (``xpath_nodes``, ``xquery_rows``, ``saxon_version``)
live in :mod:`vgi_xslt.tables`.
"""

from __future__ import annotations

import json
from collections.abc import Callable
from typing import Annotated

import pyarrow as pa
from vgi.arguments import Param, Returns
from vgi.metadata import FunctionExample
from vgi.scalar_function import ScalarFunction

from . import engine
from .meta import object_tags

# VGI509: a guaranteed-runnable, self-contained executable example shipped on at
# least one object. Catalog-qualified SQL; expected_result omitted (optional).
_XSLT_STYLESHEET = (
    '<xsl:stylesheet version="3.0" xmlns:xsl="http://www.w3.org/1999/XSL/Transform">'
    '<xsl:template match="/"><out><xsl:value-of select="//n"/></out></xsl:template>'
    "</xsl:stylesheet>"
)
_XSLT_EXECUTABLE_EXAMPLES = json.dumps(
    [
        {
            "description": (
                "Transform a document, lifting an inner element value into a new "
                "wrapper element via an XSLT 3.0 stylesheet."
            ),
            "sql": f"SELECT xslt.main.xslt('<doc><n>hi</n></doc>', '{_XSLT_STYLESHEET}')",
        },
        {
            "description": "Pull the string value of the first XPath 3.1 match from a document.",
            "sql": "SELECT xslt.main.xpath_string('<r><a>x</a><a>y</a></r>', '//a')",
        },
    ]
)

# ---------------------------------------------------------------------------
# Mapping helpers. Each applies a pure ``(xml, arg) -> X`` engine primitive
# across two aligned string columns, passing NULL (in either column) straight
# through as a NULL result. A constant stylesheet/query down a column compiles
# once thanks to the engine's lru_cache.
# ---------------------------------------------------------------------------


def _map2[T](
    a: pa.StringArray,
    b: pa.StringArray,
    fn: Callable[[str, str], T | None],
    arrow_type: pa.DataType,
) -> pa.Array:
    xs = a.to_pylist()
    ys = b.to_pylist()
    out: list[T | None] = [None if (x is None or y is None) else fn(x, y) for x, y in zip(xs, ys, strict=True)]
    return pa.array(out, type=arrow_type)


class XsltFunction(ScalarFunction):
    """``xslt(xml, stylesheet)`` -- transform xml with an XSLT 3.0 stylesheet."""

    class Meta:
        """Function metadata."""

        name = "xslt"
        description = "Transform an XML document with an XSLT 3.0 stylesheet; returns the serialized result"
        categories = ["xslt", "transform"]
        tags = {
            **object_tags(
                title="Apply XSLT Stylesheet",
                doc_llm=(
                    "## xslt\n\n"
                    "Apply an **XSLT 3.0** stylesheet to an XML document and return the "
                    "serialized transformation result as text.\n\n"
                    "**When to use:** reshape, rename, filter, or compute over XML — the full "
                    "power of XSLT 3.0 (templates, `xsl:value-of`, `xsl:for-each`, modes, "
                    "functions) — directly in SQL.\n\n"
                    "**Inputs:** `xml` (the source document) and `stylesheet` (the XSLT 3.0 "
                    "source). Both are VARCHAR.\n\n"
                    "**Output:** VARCHAR — the serialized result tree (often XML, but the "
                    "stylesheet's `xsl:output` may select text/HTML/JSON).\n\n"
                    "**Behavior & edge cases:** a NULL in either argument yields NULL for that "
                    "row. Malformed XML or a malformed stylesheet raises a clean DuckDB error. "
                    "A constant stylesheet down a column compiles once and is reused. SaxonC-HE "
                    "is not schema-aware, so schema-aware (validating) XSLT is unavailable."
                ),
                doc_md=(
                    "# xslt\n\n"
                    "Transform an XML document with an XSLT 3.0 stylesheet, returning the "
                    "serialized result.\n\n"
                    "## Usage\n\n"
                    "```sql\n"
                    "SELECT xslt.main.xslt(doc, stylesheet) FROM documents;\n"
                    "```\n\n"
                    "## Notes\n\n"
                    "- Powered by SaxonC-HE (XSLT 3.0).\n"
                    "- NULL input -> NULL output.\n"
                    "- Invalid XML or stylesheet raises a DuckDB error.\n"
                    "- A constant stylesheet is compiled once and reused across rows."
                ),
                keywords=[
                    "xslt",
                    "transform",
                    "stylesheet",
                    "xsl",
                    "transformation",
                    "xml",
                    "saxon",
                    "reshape xml",
                ],
            ),
            "vgi.executable_examples": _XSLT_EXECUTABLE_EXAMPLES,
        }
        examples = [
            FunctionExample(
                sql=f"SELECT xslt.main.xslt('<doc><n>hi</n></doc>', '{_XSLT_STYLESHEET}')",
                description="Apply an XSLT stylesheet to a document",
            ),
        ]

    @classmethod
    def compute(
        cls,
        xml: Annotated[pa.StringArray, Param(doc="XML document to transform.")],
        stylesheet: Annotated[pa.StringArray, Param(doc="XSLT 3.0 stylesheet source.")],
    ) -> Annotated[pa.StringArray, Returns()]:
        """Map each input row to its output value."""
        return _map2(xml, stylesheet, engine.transform, pa.string())


class XPathStringFunction(ScalarFunction):
    """``xpath_string(xml, expr)`` -- string value of the first match, or NULL."""

    class Meta:
        """Function metadata."""

        name = "xpath_string"
        description = "String value of the first node/atomic matching an XPath 3.1 expression (NULL if none)"
        categories = ["xslt", "xpath"]
        tags = object_tags(
            title="XPath String Value",
            doc_llm=(
                "## xpath_string\n\n"
                "Evaluate an **XPath 3.1** expression against an XML document and return the "
                "**string value of the first match** (or NULL when nothing matches).\n\n"
                "**When to use:** pull a single text value out of XML — an element's text, an "
                "attribute, or any atomic computed by XPath (`string(...)`, `concat(...)`, etc.).\n\n"
                "**Inputs:** `xml` (the document) and `expr` (an XPath 3.1 expression). Both VARCHAR.\n\n"
                "**Output:** VARCHAR — the string value of the first node/atomic in document order, "
                "or NULL if the expression selects nothing.\n\n"
                "**Behavior & edge cases:** NULL in either argument yields NULL. A malformed "
                "document or a malformed XPath raises a clean DuckDB error. Namespaces follow the "
                "document's in-scope bindings; use `//*:name` or `local-name()` predicates for "
                "namespace-agnostic matching."
            ),
            doc_md=(
                "# xpath_string\n\n"
                "Return the string value of the first XPath 3.1 match in a document, or NULL.\n\n"
                "## Usage\n\n"
                "```sql\n"
                "SELECT xslt.main.xpath_string('<r><a>x</a></r>', '//a');  -- 'x'\n"
                "```\n\n"
                "## Notes\n\n"
                "- Returns the FIRST match only; use `xpath_array` to collect all matches.\n"
                "- NULL input -> NULL output; invalid XML/XPath raises an error.\n"
                "- Namespace-agnostic matching: `//*:tag` or `local-name() = 'tag'`."
            ),
            keywords=[
                "xpath",
                "extract",
                "string value",
                "text",
                "attribute",
                "query xml",
                "select",
                "saxon",
            ],
        )
        examples = [
            FunctionExample(
                sql="SELECT xslt.main.xpath_string('<r><a>x</a><a>y</a></r>', '//a')",
                description="First matching node's string value",
            ),
        ]

    @classmethod
    def compute(
        cls,
        xml: Annotated[pa.StringArray, Param(doc="XML document.")],
        expr: Annotated[pa.StringArray, Param(doc="XPath 3.1 expression.")],
    ) -> Annotated[pa.StringArray, Returns()]:
        """Map each input row to its output value."""
        return _map2(xml, expr, engine.xpath_string, pa.string())


class XPathBooleanFunction(ScalarFunction):
    """``xpath_boolean(xml, expr)`` -- effective boolean value of the expression."""

    class Meta:
        """Function metadata."""

        name = "xpath_boolean"
        description = "Effective boolean value of an XPath 3.1 expression over the document"
        categories = ["xslt", "xpath"]
        tags = object_tags(
            title="XPath Boolean Test",
            doc_llm=(
                "## xpath_boolean\n\n"
                "Evaluate an **XPath 3.1** expression against an XML document and return its "
                "**effective boolean value** (EBV).\n\n"
                "**When to use:** test a condition over XML inside a SQL `WHERE`/`CASE` — does a "
                "node exist (`boolean(//x)`), does a count match (`count(//a) = 1`), or any "
                "predicate that XPath can express.\n\n"
                "**Inputs:** `xml` (the document) and `expr` (an XPath 3.1 expression). Both VARCHAR.\n\n"
                "**Output:** BOOLEAN — the EBV of the expression (a non-empty node-set is true, an "
                "empty one is false; numeric/string EBV rules apply for atomics).\n\n"
                "**Behavior & edge cases:** NULL in either argument yields NULL. Malformed XML or "
                "XPath raises a clean DuckDB error."
            ),
            doc_md=(
                "# xpath_boolean\n\n"
                "Return the effective boolean value of an XPath 3.1 expression over a document.\n\n"
                "## Usage\n\n"
                "```sql\n"
                "SELECT xslt.main.xpath_boolean('<r><a/></r>', 'count(//a) = 1');  -- true\n"
                "```\n\n"
                "## Notes\n\n"
                "- Follows XPath effective-boolean-value rules (existence, numbers, strings).\n"
                "- NULL input -> NULL output; invalid XML/XPath raises an error."
            ),
            keywords=[
                "xpath",
                "boolean",
                "predicate",
                "exists",
                "test",
                "condition",
                "ebv",
                "query xml",
                "saxon",
            ],
        )
        examples = [
            FunctionExample(
                sql="SELECT xslt.main.xpath_boolean('<r><a/></r>', 'count(//a) = 1')",
                description="Boolean XPath predicate",
            ),
        ]

    @classmethod
    def compute(
        cls,
        xml: Annotated[pa.StringArray, Param(doc="XML document.")],
        expr: Annotated[
            pa.StringArray,
            Param(doc="XPath 3.1 expression evaluated as a true/false test, e.g. existence or a count predicate."),
        ],
    ) -> Annotated[pa.BooleanArray, Returns()]:
        """Map each input row to its output value."""
        return _map2(xml, expr, engine.xpath_boolean, pa.bool_())


class XPathNumberFunction(ScalarFunction):
    """``xpath_number(xml, expr)`` -- numeric value of the first match, or NULL."""

    class Meta:
        """Function metadata."""

        name = "xpath_number"
        description = "Numeric (DOUBLE) value of the first XPath 3.1 match (NULL if non-numeric)"
        categories = ["xslt", "xpath"]
        tags = object_tags(
            title="XPath Numeric Value",
            doc_llm=(
                "## xpath_number\n\n"
                "Evaluate an **XPath 3.1** expression against an XML document and return its "
                "**numeric value** as a DOUBLE.\n\n"
                "**When to use:** extract a number from XML and use it in SQL arithmetic — a "
                "measurement, a count (`count(//item)`), a sum (`sum(//price)`), or any numeric "
                "XPath computation.\n\n"
                "**Inputs:** `xml` (the document) and `expr` (an XPath 3.1 expression). Both VARCHAR.\n\n"
                "**Output:** DOUBLE — the numeric value of the first match, or NULL when the value "
                "is non-numeric (XPath NaN) or nothing matches.\n\n"
                "**Behavior & edge cases:** NULL in either argument yields NULL. Wrap a path in "
                "`number(...)` to coerce a text node. Malformed XML or XPath raises a clean DuckDB "
                "error."
            ),
            doc_md=(
                "# xpath_number\n\n"
                "Return the numeric (DOUBLE) value of the first XPath 3.1 match, or NULL.\n\n"
                "## Usage\n\n"
                "```sql\n"
                "SELECT xslt.main.xpath_number('<r><n>42</n></r>', 'number(//n)');  -- 42.0\n"
                "```\n\n"
                "## Notes\n\n"
                "- Non-numeric results (XPath NaN) come back as NULL.\n"
                "- Use XPath aggregates like `count(...)` / `sum(...)` directly.\n"
                "- NULL input -> NULL output; invalid XML/XPath raises an error."
            ),
            keywords=[
                "xpath",
                "number",
                "numeric",
                "double",
                "count",
                "sum",
                "measurement",
                "query xml",
                "saxon",
            ],
        )
        examples = [
            FunctionExample(
                sql="SELECT xslt.main.xpath_number('<r><n>42</n></r>', 'number(//n)')",
                description="Numeric value via XPath",
            ),
        ]

    @classmethod
    def compute(
        cls,
        xml: Annotated[pa.StringArray, Param(doc="XML document.")],
        expr: Annotated[
            pa.StringArray,
            Param(doc="XPath 3.1 expression whose value (e.g. a count, sum, or measurement) is read as a number."),
        ],
    ) -> Annotated[pa.DoubleArray, Returns()]:
        """Map each input row to its output value."""
        return _map2(xml, expr, engine.xpath_number, pa.float64())


class XPathArrayFunction(ScalarFunction):
    """``xpath_array(xml, expr)`` -- string values of ALL matches as a VARCHAR[]."""

    class Meta:
        """Function metadata."""

        name = "xpath_array"
        description = (
            "String values of ALL matches of an XPath 3.1 expression, as a list -- "
            "UNNEST it to shred one document into rows"
        )
        categories = ["xslt", "xpath"]
        tags = object_tags(
            title="XPath Match Array",
            doc_llm=(
                "## xpath_array\n\n"
                "Evaluate an **XPath 3.1** expression against an XML document and return the "
                "string values of **all matches** as a `VARCHAR[]` list.\n\n"
                "**When to use:** shred XML into rows. Apply this to a column of documents and "
                "`UNNEST(...)` the result to turn one document into many rows — the per-row "
                "counterpart to the `xpath_nodes` table function (which binds one constant "
                "document).\n\n"
                "**Inputs:** `xml` (the document) and `expr` (an XPath 3.1 expression selecting "
                "many items). Both VARCHAR.\n\n"
                "**Output:** `VARCHAR[]` — the string value of every match, in document order; an "
                "empty list when nothing matches.\n\n"
                "**Behavior & edge cases:** NULL in either argument yields NULL (not an empty "
                "list). Malformed XML or XPath raises a clean DuckDB error."
            ),
            doc_md=(
                "# xpath_array\n\n"
                "Return the string values of ALL XPath 3.1 matches as a `VARCHAR[]` list.\n\n"
                "## Usage\n\n"
                "```sql\n"
                "SELECT UNNEST(xslt.main.xpath_array('<r><i>a</i><i>b</i></r>', '//i'));\n"
                "```\n\n"
                "## Notes\n\n"
                "- `UNNEST` the list to shred a column of documents into rows.\n"
                "- For a single constant document, the `xpath_nodes` table function is handier.\n"
                "- NULL input -> NULL output; invalid XML/XPath raises an error."
            ),
            keywords=[
                "xpath",
                "array",
                "list",
                "shred",
                "unnest",
                "all matches",
                "explode",
                "query xml",
                "saxon",
            ],
        )
        examples = [
            FunctionExample(
                sql="SELECT UNNEST(xslt.main.xpath_array('<r><i>a</i><i>b</i></r>', '//i'))",
                description="Shred all matching nodes into rows",
            ),
        ]

    @classmethod
    def compute(
        cls,
        xml: Annotated[pa.StringArray, Param(doc="XML document.")],
        expr: Annotated[pa.StringArray, Param(doc="XPath 3.1 expression selecting many items.")],
        # A LIST return type must declare its element type explicitly; the SDK
        # raises at class-definition time if Returns() can't infer it.
    ) -> Annotated[pa.ListArray, Returns(arrow_type=pa.list_(pa.string()))]:
        """Map each input row to its output value."""
        return _map2(xml, expr, engine.xpath_array, pa.list_(pa.string()))


class XQueryFunction(ScalarFunction):
    """``xquery(xml, query)`` -- run an XQuery 3.1 query; serialized result."""

    class Meta:
        """Function metadata."""

        name = "xquery"
        description = "Run an XQuery 3.1 query with the document as context item; returns the serialized result"
        categories = ["xslt", "xquery"]
        tags = object_tags(
            title="Run XQuery Query",
            doc_llm=(
                "## xquery\n\n"
                "Run an **XQuery 3.1** query against an XML document (bound as the context item) "
                "and return the serialized result.\n\n"
                "**When to use:** richer querying than a single XPath — FLWOR expressions "
                "(`for`/`let`/`where`/`order by`/`return`), constructed elements, joins across "
                "parts of the document, and string/sequence functions like "
                "`string-join(//i, ',')`.\n\n"
                "**Inputs:** `xml` (the document, available as `.` and `/`) and `query` (the "
                "XQuery 3.1 source). Both VARCHAR.\n\n"
                "**Output:** VARCHAR — the serialized query result (atomic text, or constructed "
                "XML, depending on the query).\n\n"
                "**Behavior & edge cases:** NULL in either argument yields NULL. Use `xquery_rows` "
                "instead when you want one row per item of the result sequence. Malformed XML or a "
                "malformed query raises a clean DuckDB error."
            ),
            doc_md=(
                "# xquery\n\n"
                "Run an XQuery 3.1 query with the document as the context item; returns the "
                "serialized result.\n\n"
                "## Usage\n\n"
                "```sql\n"
                "SELECT xslt.main.xquery('<r><i>a</i><i>b</i></r>', 'string-join(//i, \",\")');\n"
                "```\n\n"
                "## Notes\n\n"
                "- The document is the context item (`.` / `/`).\n"
                "- For a result sequence, `xquery_rows` returns one row per item.\n"
                "- NULL input -> NULL output; invalid XML/query raises an error."
            ),
            keywords=[
                "xquery",
                "flwor",
                "query xml",
                "string-join",
                "sequence",
                "construct",
                "transform",
                "saxon",
            ],
        )
        examples = [
            FunctionExample(
                sql="SELECT xslt.main.xquery('<r><i>a</i><i>b</i></r>', 'string-join(//i, \",\")')",
                description="Run an XQuery over a document",
            ),
        ]

    @classmethod
    def compute(
        cls,
        xml: Annotated[pa.StringArray, Param(doc="XML document (the context item).")],
        query: Annotated[pa.StringArray, Param(doc="XQuery 3.1 query source.")],
    ) -> Annotated[pa.StringArray, Returns()]:
        """Map each input row to its output value."""
        return _map2(xml, query, engine.xquery, pa.string())


class IsWellFormedFunction(ScalarFunction):
    """``is_well_formed(xml)`` -- true if the document parses; false if malformed."""

    class Meta:
        """Function metadata."""

        name = "is_well_formed"
        description = "True if the text is well-formed XML; false if malformed (never an error)"
        categories = ["xslt", "xml"]
        tags = object_tags(
            title="Check XML Well-Formedness",
            doc_llm=(
                "## is_well_formed\n\n"
                "Test whether a string is **well-formed XML** — returns `true` if it parses, "
                "`false` if it is malformed. **Never raises** (unlike the other functions).\n\n"
                "**When to use:** validate or filter a column of candidate XML before transforming "
                "or querying it, e.g. `WHERE xslt.main.is_well_formed(doc)`, so malformed rows do "
                "not abort the scan.\n\n"
                "**Inputs:** `xml` (the candidate text). VARCHAR.\n\n"
                "**Output:** BOOLEAN — `true` for well-formed XML, `false` for malformed text; "
                "NULL input yields NULL.\n\n"
                "**Behavior & edge cases:** this checks *well-formedness* (does it parse), not "
                "schema validity — SaxonC-HE is not schema-aware, so there is no XSD validation. "
                "Well-formedness is the strongest XML check the HE edition offers."
            ),
            doc_md=(
                "# is_well_formed\n\n"
                "Return `true` if the text is well-formed XML, `false` if malformed (never errors).\n\n"
                "## Usage\n\n"
                "```sql\n"
                "SELECT xslt.main.is_well_formed('<a></a>');   -- true\n"
                "SELECT xslt.main.is_well_formed('<a>');        -- false\n"
                "```\n\n"
                "## Notes\n\n"
                "- Checks well-formedness only; there is no XSD/schema validation (HE limitation).\n"
                "- Safe to use in `WHERE` to filter out malformed rows.\n"
                "- NULL input -> NULL output."
            ),
            keywords=[
                "well-formed",
                "validate",
                "valid xml",
                "parse",
                "malformed",
                "check",
                "filter",
                "xml",
                "saxon",
            ],
        )
        examples = [
            FunctionExample(
                sql="SELECT xslt.main.is_well_formed('<a></a>')",
                description="Check whether a string is well-formed XML",
            ),
        ]

    @classmethod
    def compute(
        cls,
        xml: Annotated[pa.StringArray, Param(doc="Candidate XML text.")],
    ) -> Annotated[pa.BooleanArray, Returns()]:
        """Map each input row to its output value."""
        out = [None if x is None else engine.is_well_formed(x) for x in xml.to_pylist()]
        return pa.array(out, type=pa.bool_())


SCALAR_FUNCTIONS: list[type] = [
    XsltFunction,
    XPathStringFunction,
    XPathBooleanFunction,
    XPathNumberFunction,
    XPathArrayFunction,
    XQueryFunction,
    IsWellFormedFunction,
]
