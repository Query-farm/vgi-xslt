"""Integration tests for the xslt table functions.

Drives ``xpath_nodes``, ``xquery_rows`` and ``saxon_version`` through the real
bind -> init -> process lifecycle in-process (no worker subprocess).
"""

from __future__ import annotations

import pyarrow as pa

from vgi_xslt.tables import SaxonVersionFunction, XPathNodesFunction, XQueryRowsFunction

from .harness import invoke_table_function


class TestXPathNodes:
    def test_columns_and_rows(self) -> None:
        table = invoke_table_function(
            XPathNodesFunction,
            positional=(pa.scalar("<r><i>a</i><i>b</i></r>"), pa.scalar("//i")),
        )
        assert table.column_names == ["seq", "value"]
        assert table.column("seq").to_pylist() == [1, 2]
        assert table.column("value").to_pylist() == ["a", "b"]

    def test_no_match_is_empty(self) -> None:
        table = invoke_table_function(
            XPathNodesFunction,
            positional=(pa.scalar("<r><i>a</i></r>"), pa.scalar("//z")),
        )
        assert table.num_rows == 0


class TestXQueryRows:
    def test_flwor_doubles(self) -> None:
        table = invoke_table_function(
            XQueryRowsFunction,
            positional=(
                pa.scalar("<r><i>1</i><i>2</i><i>3</i></r>"),
                pa.scalar("for $x in //i return $x * 2"),
            ),
        )
        assert table.column("seq").to_pylist() == [1, 2, 3]
        assert table.column("value").to_pylist() == ["2", "4", "6"]


class TestSaxonVersion:
    def test_single_row(self) -> None:
        table = invoke_table_function(SaxonVersionFunction)
        assert table.column_names == ["version"]
        assert table.num_rows == 1
        assert "Saxon" in table.column("version")[0].as_py()
