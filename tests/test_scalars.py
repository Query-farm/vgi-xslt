"""End-to-end tests for the per-row scalar xslt functions.

These spawn ``xslt_worker.py`` as a subprocess via ``vgi.client.Client`` and
call each scalar exactly as DuckDB would after ``ATTACH``. Both arguments travel
as columns in the input batch; the ``positional`` arguments are column
references (by name) into that batch, mirroring how DuckDB binds column inputs.
"""

from __future__ import annotations

import sys
from collections.abc import Iterator
from pathlib import Path

import pyarrow as pa
import pytest
from vgi import Arguments
from vgi.client import Client, ClientError

_WORKER = str(Path(__file__).resolve().parent.parent / "xslt_worker.py")

_IDENTITY = (
    '<xsl:stylesheet version="3.0" xmlns:xsl="http://www.w3.org/1999/XSL/Transform">'
    '<xsl:output method="xml" omit-xml-declaration="yes"/>'
    '<xsl:template match="/"><out><xsl:value-of select="//name"/></out></xsl:template>'
    "</xsl:stylesheet>"
)


@pytest.fixture(scope="module")
def client() -> Iterator[Client]:
    # Current interpreter (deps already installed) + worker_limit=1 so output
    # order matches input order for deterministic per-row assertions.
    with Client(f"{sys.executable} {_WORKER}", worker_limit=1) as c:
        yield c


def _scalar2(client: Client, name: str, xml: list, arg: list) -> list:
    """Call a 2-arg scalar; both args are columns in the input batch."""
    batch = pa.RecordBatch.from_pydict(
        {
            "xml": pa.array(xml, type=pa.string()),
            "arg": pa.array(arg, type=pa.string()),
        }
    )
    results = list(
        client.scalar_function(
            function_name=name,
            input=iter([batch]),
            arguments=Arguments(positional=[pa.scalar("xml"), pa.scalar("arg")]),
        )
    )
    return results[0]["result"].to_pylist()


def _scalar1(client: Client, name: str, xml: list) -> list:
    """Call a 1-arg scalar; the single arg is a column in the input batch."""
    batch = pa.RecordBatch.from_pydict({"xml": pa.array(xml, type=pa.string())})
    results = list(
        client.scalar_function(
            function_name=name,
            input=iter([batch]),
            arguments=Arguments(positional=[pa.scalar("xml")]),
        )
    )
    return results[0]["result"].to_pylist()


class TestXslt:
    def test_value_extract(self, client: Client) -> None:
        out = _scalar2(client, "xslt", ["<p><name>Ada</name></p>"], [_IDENTITY])
        assert out == ["<out>Ada</out>"]

    def test_null_passthrough(self, client: Client) -> None:
        assert _scalar2(client, "xslt", [None], [_IDENTITY]) == [None]

    def test_bad_stylesheet_errors(self, client: Client) -> None:
        with pytest.raises(ClientError):
            _scalar2(client, "xslt", ["<p/>"], ["<not-a-stylesheet/>"])


class TestXPathString:
    def test_first_match_and_null(self, client: Client) -> None:
        out = _scalar2(
            client,
            "xpath_string",
            ["<r><a>x</a><a>y</a></r>", "<r/>", None],
            ["//a", "//z", "//a"],
        )
        assert out == ["x", None, None]


class TestXPathBoolean:
    def test_predicates(self, client: Client) -> None:
        out = _scalar2(
            client,
            "xpath_boolean",
            ["<r><a/></r>", "<r><a/></r>"],
            ["count(//a) = 1", "exists(//z)"],
        )
        assert out == [True, False]


class TestXPathNumber:
    def test_number(self, client: Client) -> None:
        out = _scalar2(client, "xpath_number", ["<r><n>42</n></r>"], ["number(//n)"])
        assert out == [42.0]


class TestXPathArray:
    def test_shred(self, client: Client) -> None:
        out = _scalar2(client, "xpath_array", ["<r><i>a</i><i>b</i><i>c</i></r>"], ["//i"])
        assert out == [["a", "b", "c"]]

    def test_no_match_empty_list(self, client: Client) -> None:
        out = _scalar2(client, "xpath_array", ["<r><i>a</i></r>"], ["//z"])
        assert out == [[]]


class TestXQuery:
    def test_string_join(self, client: Client) -> None:
        out = _scalar2(client, "xquery", ["<r><i>a</i><i>b</i></r>"], ['string-join(//i, ",")'])
        assert out == ["a,b"]


class TestIsWellFormed:
    def test_well_formed_and_malformed(self, client: Client) -> None:
        out = _scalar1(client, "is_well_formed", ["<a><b/></a>", "<a><b></a>", None])
        assert out == [True, False, None]
