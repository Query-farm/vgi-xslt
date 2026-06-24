"""Set-returning table functions for the xslt worker.

These expand a single document into **many rows**, so they are exposed as
**table functions** (the form that accepts DuckDB ``name := value`` arguments):

    SELECT * FROM xslt.xpath_nodes('<r><i>a</i><i>b</i></r>', '//i');
    SELECT * FROM xslt.xquery_rows('<r><i>1</i><i>2</i></r>', 'for $x in //i return $x*2');
    SELECT * FROM xslt.saxon_version();

For shredding *a column of documents* (one expression applied per row) use the
``xpath_array`` scalar with ``UNNEST`` instead -- a table function binds a single
constant document. ``xpath_nodes`` / ``xquery_rows`` are for exploding one
document with a sequence number per match.
"""

from __future__ import annotations

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
from .schema_utils import field

_SEQ_VALUE_COLUMNS_MD = (
    "| Column | Type | Description |\n"
    "| --- | --- | --- |\n"
    "| `seq` | BIGINT | 1-based position of the match in document/sequence order |\n"
    "| `value` | VARCHAR | String value of the matched node/item |"
)

_VERSION_COLUMNS_MD = (
    "| Column | Type | Description |\n"
    "| --- | --- | --- |\n"
    "| `version` | VARCHAR | SaxonC version string backing this worker |"
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
        tags = {"vgi.columns_md": _SEQ_VALUE_COLUMNS_MD}
        examples = [
            FunctionExample(
                sql="SELECT * FROM xslt.xpath_nodes('<r><i>a</i><i>b</i></r>', '//i')",
                description="Explode every matching node into a row",
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
        tags = {"vgi.columns_md": _SEQ_VALUE_COLUMNS_MD}
        examples = [
            FunctionExample(
                sql="SELECT * FROM xslt.xquery_rows('<r><i>1</i><i>2</i></r>', 'for $x in //i return $x*2')",
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
    """A discovery table function that takes no arguments."""


_VERSION_SCHEMA = pa.schema([field("version", pa.string(), "SaxonC version string.", nullable=False)])


@init_single_worker
@bind_fixed_schema
class SaxonVersionFunction(TableFunctionGenerator[_NoArgs]):
    """A single row carrying the SaxonC version string (discovery)."""

    FIXED_SCHEMA: ClassVar[pa.Schema] = _VERSION_SCHEMA

    class Meta:
        """Function metadata."""

        name = "saxon_version"
        description = "The SaxonC version string backing this worker (single row)"
        categories = ["xslt", "discovery"]
        tags = {"vgi.columns_md": _VERSION_COLUMNS_MD}
        examples = [
            FunctionExample(
                sql="SELECT * FROM xslt.saxon_version()",
                description="Discover the Saxon version",
            ),
        ]

    @classmethod
    def cardinality(cls, params: BindParams[_NoArgs]) -> TableCardinality:
        """Estimated and maximum row count for the planner."""
        return TableCardinality(estimate=1, max=1)

    @classmethod
    def process(cls, params: ProcessParams[_NoArgs], state: None, out: OutputCollector) -> None:
        """Emit the output rows produced by this invocation."""
        out.emit(
            pa.RecordBatch.from_pydict(
                {"version": [engine.version()]},
                schema=params.output_schema,
            )
        )
        out.finish()


TABLE_FUNCTIONS: list[type] = [
    XPathNodesFunction,
    XQueryRowsFunction,
    SaxonVersionFunction,
]
