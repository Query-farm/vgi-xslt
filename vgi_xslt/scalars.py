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

from collections.abc import Callable
from typing import Annotated

import pyarrow as pa
from vgi.arguments import Param, Returns
from vgi.metadata import FunctionExample
from vgi.scalar_function import ScalarFunction

from . import engine

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
        examples = [
            FunctionExample(
                sql=(
                    "SELECT xslt('<doc><n>hi</n></doc>', "
                    '\'<xsl:stylesheet version="3.0" xmlns:xsl="http://www.w3.org/1999/XSL/Transform">'
                    '<xsl:template match="/"><out><xsl:value-of select="//n"/></out></xsl:template>'
                    "</xsl:stylesheet>')"
                ),
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
        examples = [
            FunctionExample(
                sql="SELECT xpath_string('<r><a>x</a><a>y</a></r>', '//a')",
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
        examples = [
            FunctionExample(
                sql="SELECT xpath_boolean('<r><a/></r>', 'count(//a) = 1')",
                description="Boolean XPath predicate",
            ),
        ]

    @classmethod
    def compute(
        cls,
        xml: Annotated[pa.StringArray, Param(doc="XML document.")],
        expr: Annotated[pa.StringArray, Param(doc="XPath 3.1 boolean expression.")],
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
        examples = [
            FunctionExample(
                sql="SELECT xpath_number('<r><n>42</n></r>', 'number(//n)')",
                description="Numeric value via XPath",
            ),
        ]

    @classmethod
    def compute(
        cls,
        xml: Annotated[pa.StringArray, Param(doc="XML document.")],
        expr: Annotated[pa.StringArray, Param(doc="XPath 3.1 numeric expression.")],
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
        examples = [
            FunctionExample(
                sql="SELECT UNNEST(xpath_array('<r><i>a</i><i>b</i></r>', '//i'))",
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
        examples = [
            FunctionExample(
                sql="SELECT xquery('<r><i>a</i><i>b</i></r>', 'string-join(//i, \",\")')",
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
        examples = [
            FunctionExample(
                sql="SELECT is_well_formed('<a></a>')",
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
