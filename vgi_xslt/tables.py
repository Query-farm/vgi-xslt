"""Set-returning table functions for the xslt worker.

These expand a single document into **many rows**, so they are exposed as
**table functions** (the form that accepts DuckDB ``name := value`` arguments):

    SELECT * FROM xslt.xpath_nodes('<r><i>a</i><i>b</i></r>', '//i');
    SELECT * FROM xslt.xquery_rows('<r><i>1</i><i>2</i></r>', 'for $x in //i return $x*2');

For shredding *a column of documents* (one expression applied per row) use the
``xpath_array`` scalar with ``UNNEST`` instead -- a table function binds a single
constant document. ``xpath_nodes`` / ``xquery_rows`` are for exploding one
document with a sequence number per match.
"""

from __future__ import annotations

import json
from dataclasses import dataclass
from typing import Annotated, ClassVar

import pyarrow as pa
from vgi.arguments import Arg
from vgi.metadata import FunctionExample
from vgi.table_function import (
    BindParams,
    ProcessParams,
    TableCardinality,
    TableFunctionGenerator,
    bind_fixed_schema,
    init_single_worker,
)
from vgi_rpc.rpc import OutputCollector

from . import engine
from .meta import object_tags
from .schema_utils import field

# VGI307: a table function with no backing table must declare its result schema
# as a JSON array of {name, type, description}. Both shredding table functions
# return the same fixed (seq, value) shape.
_SEQ_VALUE_COLUMNS_SCHEMA = json.dumps(
    [
        {
            "name": "seq",
            "type": "BIGINT",
            "description": "1-based position of the match in document/sequence order.",
        },
        {
            "name": "value",
            "type": "VARCHAR",
            "description": "String value of the matched node/item.",
        },
    ]
)

_SEQ_VALUE_SCHEMA = pa.schema(
    [
        field("seq", pa.int64(), "1-based position of the match in document/sequence order.", nullable=False),
        field("value", pa.string(), "String value of the matched node/item.", nullable=False),
    ]
)


@dataclass(kw_only=True)
class _DocExprArgs:
    """``(xml, expr)`` -- a document and an XPath/XQuery string."""

    xml: Annotated[str, Arg(0, arrow_type=pa.string(), doc="XML document.")]
    expr: Annotated[str, Arg(1, arrow_type=pa.string(), doc="XPath 3.1 expression / XQuery 3.1 query.")]


@init_single_worker
@bind_fixed_schema
class XPathNodesFunction(TableFunctionGenerator[_DocExprArgs]):
    """One ``(seq, value)`` row per XPath match in a single document."""

    FIXED_SCHEMA: ClassVar[pa.Schema] = _SEQ_VALUE_SCHEMA

    class Meta:
        """Function metadata."""

        name = "xpath_nodes"
        description = "One (seq, value) row per XPath 3.1 match in a single document"
        categories = ["xslt", "xpath"]
        tags = {
            **object_tags(
                title="XPath Nodes Table",
                category="shred",
                doc_llm=(
                    "## xpath_nodes\n\n"
                    "Explode a single XML document into rows: emit **one `(seq, value)` row per "
                    "XPath 3.1 match**, in document order.\n\n"
                    "**When to use:** shred one constant document into a relational result — turn "
                    "`//item` matches into a numbered table you can join, filter, and aggregate. "
                    "For shredding a *column* of documents instead, use the `xpath_array` scalar "
                    "with `UNNEST`.\n\n"
                    "**Inputs:** `xml` (the document) and `expr` (an XPath 3.1 expression). Both "
                    "`VARCHAR`; table-function named-argument syntax (`name := value`) is supported.\n\n"
                    "**Output columns:** `seq` (`BIGINT`, 1-based position) and `value` (`VARCHAR`, the "
                    "match's string value).\n\n"
                    "**Behavior & edge cases:** no matches -> zero rows. Malformed XML or XPath "
                    "raises a clean DuckDB error."
                ),
                doc_md=(
                    "# xpath_nodes\n\n"
                    "Table function: one `(seq, value)` row per XPath 3.1 match in one document.\n\n"
                    "## Usage\n\n"
                    "Call `xslt.main.xpath_nodes(xml, expr)` in a `FROM` clause to expand each "
                    "match into a numbered `(seq, value)` row.\n\n"
                    "## Notes\n\n"
                    "- Binds a single constant document; use `xpath_array` + `UNNEST` per row.\n"
                    "- `seq` is the 1-based document-order position of each match.\n"
                    "- Invalid XML/XPath raises an error."
                ),
                keywords=[
                    "xpath",
                    "table",
                    "rows",
                    "shred",
                    "explode",
                    "nodes",
                    "sequence",
                    "query xml",
                    "saxon",
                ],
                examples=[
                    (
                        "Number each XPath match and return it in document order.",
                        "SELECT seq, value FROM xslt.main.xpath_nodes('<r><i>a</i><i>b</i></r>', '//i') ORDER BY seq",
                    ),
                ],
            ),
            "vgi.result_columns_schema": _SEQ_VALUE_COLUMNS_SCHEMA,
        }
        examples = [
            FunctionExample(
                sql="SELECT seq, value FROM xslt.main.xpath_nodes('<r><i>a</i><i>b</i></r>', '//i') ORDER BY seq",
                description="Number each XPath match and return it in document order",
            ),
        ]

    @classmethod
    def cardinality(cls, params: BindParams[_DocExprArgs]) -> TableCardinality:
        """Estimated and maximum row count for the planner."""
        return TableCardinality(estimate=None, max=None)

    @classmethod
    def process(cls, params: ProcessParams[_DocExprArgs], state: None, out: OutputCollector) -> None:
        """Emit the output rows produced by this invocation."""
        a = params.args
        values = engine.xpath_array(a.xml, a.expr)
        out.emit(
            pa.RecordBatch.from_pydict(
                {
                    "seq": list(range(1, len(values) + 1)),
                    "value": values,
                },
                schema=params.output_schema,
            )
        )
        out.finish()


@init_single_worker
@bind_fixed_schema
class XQueryRowsFunction(TableFunctionGenerator[_DocExprArgs]):
    """One ``(seq, value)`` row per item in an XQuery result sequence."""

    FIXED_SCHEMA: ClassVar[pa.Schema] = _SEQ_VALUE_SCHEMA

    class Meta:
        """Function metadata."""

        name = "xquery_rows"
        description = "One (seq, value) row per item in an XQuery 3.1 result sequence"
        categories = ["xslt", "xquery"]
        tags = {
            **object_tags(
                title="XQuery Rows Table",
                category="shred",
                doc_llm=(
                    "## xquery_rows\n\n"
                    "Run an **XQuery 3.1** query against one document and emit **one `(seq, value)` "
                    "row per item** of the result sequence, in sequence order.\n\n"
                    "**When to use:** when the query yields a sequence (e.g. a FLWOR "
                    "`for $x in //i return $x*2`) and you want each item as its own row to join, "
                    "filter, or aggregate in SQL. Use the `xquery` scalar instead when you want the "
                    "whole result serialized into one value.\n\n"
                    "**Inputs:** `xml` (the document, bound as the context item) and `expr` (the "
                    "XQuery 3.1 source). Both `VARCHAR`; named-argument syntax supported.\n\n"
                    "**Output columns:** `seq` (`BIGINT`, 1-based position) and `value` (`VARCHAR`, the "
                    "item's string value).\n\n"
                    "**Behavior & edge cases:** an empty result sequence -> zero rows. Malformed "
                    "XML or a malformed query raises a clean DuckDB error."
                ),
                doc_md=(
                    "# xquery_rows\n\n"
                    "Table function: one `(seq, value)` row per item in an XQuery 3.1 result "
                    "sequence.\n\n"
                    "## Usage\n\n"
                    "Call `xslt.main.xquery_rows(xml, expr)` in a `FROM` clause to expand each "
                    "item of the result sequence into a numbered `(seq, value)` row.\n\n"
                    "## Notes\n\n"
                    "- One row per sequence item; `seq` is the 1-based position.\n"
                    "- Use the `xquery` scalar for a single serialized result.\n"
                    "- Invalid XML/query raises an error."
                ),
                keywords=[
                    "xquery",
                    "table",
                    "rows",
                    "flwor",
                    "sequence",
                    "explode",
                    "shred",
                    "query xml",
                    "saxon",
                ],
                examples=[
                    (
                        "Explode an XQuery FLWOR result into numbered rows.",
                        "SELECT seq, value FROM xslt.main.xquery_rows("
                        "'<r><i>1</i><i>2</i></r>', 'for $x in //i return $x*2') ORDER BY seq",
                    ),
                ],
            ),
            "vgi.result_columns_schema": _SEQ_VALUE_COLUMNS_SCHEMA,
        }
        examples = [
            FunctionExample(
                sql="SELECT seq, value FROM xslt.main.xquery_rows("
                "'<r><i>1</i><i>2</i></r>', 'for $x in //i return $x*2') ORDER BY seq",
                description="Explode an XQuery FLWOR result into rows",
            ),
        ]

    @classmethod
    def cardinality(cls, params: BindParams[_DocExprArgs]) -> TableCardinality:
        """Estimated and maximum row count for the planner."""
        return TableCardinality(estimate=None, max=None)

    @classmethod
    def process(cls, params: ProcessParams[_DocExprArgs], state: None, out: OutputCollector) -> None:
        """Emit the output rows produced by this invocation."""
        a = params.args
        values = engine.xquery_items(a.xml, a.expr)
        out.emit(
            pa.RecordBatch.from_pydict(
                {
                    "seq": list(range(1, len(values) + 1)),
                    "value": values,
                },
                schema=params.output_schema,
            )
        )
        out.finish()


@dataclass(kw_only=True)
class _NoArgs:
    """A reference table function that takes no arguments."""


# The XSLT/XQuery/XPath language levels and edition are fixed by the bundled
# SaxonC-HE build; only the version string is read at runtime.
_SAXON_INFO_SCHEMA = pa.schema(
    [
        field("version", pa.string(), "SaxonC version string of the bundled engine.", nullable=False),
        field(
            "edition",
            pa.string(),
            "Saxon edition (HE = Home Edition, the free, non-schema-aware build).",
            nullable=False,
        ),
        field("xslt_version", pa.string(), "XSLT language level the engine implements.", nullable=False),
        field("xquery_version", pa.string(), "XQuery language level the engine implements.", nullable=False),
        field("xpath_version", pa.string(), "XPath language level the engine implements.", nullable=False),
        field(
            "schema_aware",
            pa.bool_(),
            "Whether the engine can do XSD validation / schema-aware processing (always false on HE).",
            nullable=False,
        ),
    ]
)

# VGI307 result schema for the browsable capabilities table.
_SAXON_INFO_COLUMNS_SCHEMA = json.dumps(
    [
        {"name": "version", "type": "VARCHAR", "description": "SaxonC version string of the bundled engine."},
        {
            "name": "edition",
            "type": "VARCHAR",
            "description": "Saxon edition (HE = Home Edition, the free, non-schema-aware build).",
        },
        {"name": "xslt_version", "type": "VARCHAR", "description": "XSLT language level the engine implements."},
        {"name": "xquery_version", "type": "VARCHAR", "description": "XQuery language level the engine implements."},
        {"name": "xpath_version", "type": "VARCHAR", "description": "XPath language level the engine implements."},
        {
            "name": "schema_aware",
            "type": "BOOLEAN",
            "description": "Whether the engine can do XSD validation / schema-aware processing (always false on HE).",
        },
    ]
)


@init_single_worker
@bind_fixed_schema
class SaxonInfoFunction(TableFunctionGenerator[_NoArgs]):
    """A single row describing the bundled SaxonC engine and its capabilities."""

    FIXED_SCHEMA: ClassVar[pa.Schema] = _SAXON_INFO_SCHEMA

    class Meta:
        """Function metadata."""

        name = "saxon_info"
        description = "One row describing the bundled SaxonC engine: version, edition, and language levels"
        categories = ["xslt", "reference"]
        tags = {
            **object_tags(
                title="Saxon Engine Capabilities",
                category="reference",
                doc_llm=(
                    "## saxon_info\n\n"
                    "A **single-row reference table** describing the SaxonC engine bundled with "
                    "this worker: its version, edition, and the XSLT/XQuery/XPath language levels "
                    "it implements.\n\n"
                    "**When to use:** discover what the engine can do before you rely on it — most "
                    "importantly the `schema_aware` flag (always false on the Home Edition, so "
                    "there is no XSD validation) and the language levels behind `xslt`, `xquery`, "
                    "and the `xpath_*` functions. Because it takes no arguments, it is directly "
                    "browsable — the whole table is a single row of engine facts.\n\n"
                    "**Inputs:** none.\n\n"
                    "**Output columns:** `version`, `edition`, `xslt_version`, `xquery_version`, "
                    "`xpath_version` (all `VARCHAR`) and `schema_aware` (`BOOLEAN`).\n\n"
                    "**Behavior & edge cases:** always exactly one row; the language levels and "
                    "edition are constant, only `version` is read from the running build."
                ),
                doc_md=(
                    "# saxon_info\n\n"
                    "A single-row reference table describing the bundled SaxonC engine and the "
                    "capabilities it exposes to the rest of this catalog.\n\n"
                    "## Usage\n\n"
                    "The table has no arguments and a single row: read the `version`, `edition`, "
                    "and `xslt_version` / `xquery_version` / `xpath_version` columns for the engine "
                    "facts, and the `schema_aware` column to learn whether XSD validation is "
                    "available.\n\n"
                    "## Notes\n\n"
                    "- Always one row; no arguments, so it is directly browsable.\n"
                    "- `schema_aware` is always false on SaxonC-HE (no XSD validation)."
                ),
                keywords=[
                    "saxon",
                    "capabilities",
                    "engine",
                    "version",
                    "edition",
                    "schema aware",
                    "reference",
                    "xslt",
                ],
                examples=[
                    (
                        "Read the engine version and whether XSD validation is available.",
                        "SELECT version, schema_aware FROM xslt.main.saxon_info",
                    ),
                ],
            ),
            "vgi.result_columns_schema": _SAXON_INFO_COLUMNS_SCHEMA,
        }
        examples = [
            FunctionExample(
                sql="SELECT version, schema_aware FROM xslt.main.saxon_info",
                description="Read the engine version and whether XSD validation is available",
            ),
        ]

    @classmethod
    def cardinality(cls, params: BindParams[_NoArgs]) -> TableCardinality:
        """Estimated and maximum row count for the planner."""
        return TableCardinality(estimate=1, max=1)

    @classmethod
    def process(cls, params: ProcessParams[_NoArgs], state: None, out: OutputCollector) -> None:
        """Emit the single capabilities row."""
        out.emit(
            pa.RecordBatch.from_pydict(
                {
                    "version": [engine.version()],
                    "edition": ["Home Edition (HE)"],
                    "xslt_version": ["3.0"],
                    "xquery_version": ["3.1"],
                    "xpath_version": ["3.1"],
                    "schema_aware": [False],
                },
                schema=params.output_schema,
            )
        )
        out.finish()


TABLE_FUNCTIONS: list[type] = [
    XPathNodesFunction,
    XQueryRowsFunction,
    SaxonInfoFunction,
]
