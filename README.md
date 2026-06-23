<p align="center">
  <img src="docs/vgi-logo.png" alt="Vector Gateway Interface (VGI)" width="320">
</p>

<p align="center"><em>A <a href="https://query.farm">Query.Farm</a> VGI worker for DuckDB.</em></p>

# vgi-xslt

[![CI](https://github.com/Query-farm/vgi-xslt/actions/workflows/ci.yml/badge.svg)](https://github.com/Query-farm/vgi-xslt/actions/workflows/ci.yml)

A [VGI](https://query.farm) worker that brings **XSLT 3.0 / XQuery 3.1 /
XPath 3.1** into DuckDB/SQL. Transform, query, and **shred** XML documents from
plain SQL — extract values, evaluate XPath, run XQuery FLWORs, and explode one
document into many rows — backed by [SaxonC-HE](https://www.saxonica.com/) via
the [`saxonche`](https://pypi.org/project/saxonche/) Python bindings.

```sql
INSTALL vgi FROM community; LOAD vgi;
ATTACH 'xslt' (TYPE vgi, LOCATION 'uv run xslt_worker.py');

SELECT xslt.xpath_string('<r><a>x</a></r>', '//a');            -- 'x'
SELECT xslt.xpath_boolean('<r><a/></r>', 'count(//a) = 1');    -- true
SELECT xslt.xpath_number('<r><n>42</n></r>', 'number(//n)');   -- 42.0
SELECT UNNEST(xslt.xpath_array('<r><i>a</i><i>b</i></r>', '//i'));  -- 'a','b'  ← shred!
SELECT xslt.xquery('<r><i>a</i><i>b</i></r>', 'string-join(//i, ",")');  -- 'a,b'
SELECT xslt.is_well_formed('<a></a>');                         -- true
SELECT * FROM xslt.xpath_nodes('<r><i>a</i><i>b</i></r>', '//i');  -- (seq, value) rows
SELECT * FROM xslt.saxon_version();
```

The headline is **`xpath_array`** + `UNNEST`: it turns a column of XML documents
into shredded rows, one per matching node, in a single SQL statement:

```sql
SELECT id, UNNEST(xpath_array(doc, '//item')) AS item
FROM documents;
```

## Scalars (per-row) vs. table functions

* **Scalars** take **positional** arguments only (DuckDB's `name := value`
  syntax is a table-function/macro feature, not a scalar one). Every per-row
  answer is a scalar, so it works inline in any projection or predicate. All
  scalars here are a fixed shape — `(xml)` or `(xml, expr)` — so there are no
  arity overloads.

* **Table functions** expand one document into **many rows** and accept named
  arguments: `xpath_nodes(xml, expr)`, `xquery_rows(xml, query)`, and the no-arg
  discovery `saxon_version()`.

**NULL semantics.** A NULL in any scalar argument yields NULL output for that
row; a table function over a NULL document yields no rows. **Invalid** input —
malformed XML, a bad stylesheet/query, or a bad XPath expression — raises a
clean DuckDB error (never a worker crash), **except** `is_well_formed`, which
reports malformed XML as `false` rather than erroring.

## Function catalog

| Function | Form | Signature | Returns |
| --- | --- | --- | --- |
| `xslt` | scalar | `(xml, stylesheet)` | `VARCHAR` (serialized result) |
| `xpath_string` | scalar | `(xml, expr)` | `VARCHAR` (first match, NULL if none) |
| `xpath_boolean` | scalar | `(xml, expr)` | `BOOLEAN` (effective boolean value) |
| `xpath_number` | scalar | `(xml, expr)` | `DOUBLE` (first match, NULL if non-numeric) |
| `xpath_array` | scalar | `(xml, expr)` | `VARCHAR[]` (string value of **all** matches) |
| `xquery` | scalar | `(xml, query)` | `VARCHAR` (serialized result) |
| `is_well_formed` | scalar | `(xml)` | `BOOLEAN` (false if malformed, never errors) |
| `xpath_nodes` | table | `(xml, expr)` | `(seq BIGINT, value VARCHAR)` |
| `xquery_rows` | table | `(xml, query)` | `(seq BIGINT, value VARCHAR)` |
| `saxon_version` | table | `()` | `(version VARCHAR)` |

### XSLT transforms

`xslt(xml, stylesheet)` compiles the stylesheet (XSLT 3.0) and applies it to the
document, returning the serialized result. A **constant** stylesheet applied
down a column compiles **once** and transforms many rows (compiled executables
are cached by their source text).

```sql
SELECT id, xslt(doc, (SELECT stylesheet FROM my_xslt)) AS html
FROM documents;
```

### XPath

`xpath_string` / `xpath_boolean` / `xpath_number` evaluate an XPath 3.1
expression and return the first match's string value, the expression's effective
boolean value, or the first match's numeric value respectively. `xpath_array`
returns the string value of **every** match as a `VARCHAR[]` — `UNNEST` it to
shred a document into rows.

```sql
SELECT xpath_string(doc, '//title')                 AS title,
       xpath_boolean(doc, 'exists(//published)')    AS is_published,
       xpath_number(doc, 'count(//comment)')        AS num_comments
FROM articles;
```

**Namespaces.** XPath expressions are evaluated by Saxon over the document's
in-scope namespaces. The most portable way to match namespaced elements without
binding a prefix is the wildcard-namespace test `//*:item` or a
`local-name() = 'item'` predicate (both shown in the test suite). Binding a
specific prefix inside a single SQL string is limited by SaxonC's expression
context; prefer wildcard / `local-name()` where you can't declare a prefix.

### XQuery

`xquery(xml, query)` runs an XQuery 3.1 query with the document as the context
item and returns the serialized result; `xquery_rows(xml, query)` explodes the
result **sequence** into `(seq, value)` rows.

```sql
SELECT * FROM xquery_rows(
  '<order><line>1</line><line>2</line><line>3</line></order>',
  'for $l in //line return $l * 10'
);   -- (1,'10'), (2,'20'), (3,'30')
```

### Shredding XML

Two complementary tools:

* **`xpath_array` + `UNNEST`** — shred a **column** of documents (one expression
  applied per row). This is the headline:

  ```sql
  SELECT id, UNNEST(xpath_array(doc, '//item')) AS item FROM documents;
  ```

* **`xpath_nodes(xml, expr)` / `xquery_rows(xml, query)`** — explode a **single**
  document into rows with a 1-based `seq`:

  ```sql
  SELECT seq, value FROM xpath_nodes('<r><i>a</i><i>b</i></r>', '//i');
  ```

## Dependencies & licensing

| Component | License | Notes |
| --- | --- | --- |
| `vgi-xslt` (this worker) | **MIT** | This repository's own code. |
| [`saxonche`](https://pypi.org/project/saxonche/) (SaxonC-**HE** 13.0) | **Mozilla Public License 2.0** | The free/open-source **Home Edition** of Saxon. |
| [`vgi-python`](https://github.com/Query-farm/vgi-python) | Query Farm Source-Available | The VGI SDK. |

### Saxon edition note (HE, MPL-2.0)

This worker uses **SaxonC-HE** — the **Home Edition**, distributed under the
**Mozilla Public License 2.0** (the free/open-source Saxon edition). The
`saxonche` wheel on PyPI ships SaxonC-HE 13.0. The processor is created with
`license=False`, so no Saxon licence file is required and no commercial Saxon
key is involved.

> **No XSD / schema awareness.** SaxonC-HE is **not schema-aware**: there is no
> XSD validation and no schema-aware XSLT/XQuery. This worker therefore exposes
> **no `xsd_validate` function** — `is_well_formed` checks *well-formedness*
> (does it parse), which is the strongest XML check HE can offer. Saxon's
> commercial **PE/EE** editions add schema awareness; this worker deliberately
> stays on the free HE edition.

MPL-2.0 is a permissive, file-level copyleft licence: using `saxonche` as an
unmodified, separately pip-installed dependency keeps **`vgi-xslt`'s own code
MIT** and fine for commercial use.

## Local development

```sh
uv sync --all-extras     # create .venv with vgi-python + saxonche + dev tools
make test                # pytest (unit + integration) + SQL end-to-end
make test-unit           # pytest only
make test-sql            # DuckDB sqllogictest files via haybarn-unittest
uv run ruff check .      # lint
uv run mypy vgi_xslt/
```

`tests/test_engine.py` covers the pure Saxon primitives directly (malformed XML,
empty strings, bad XPath, no-match, namespaces, a real XSLT identity +
value-extract transform, an XQuery FLWOR sequence); `tests/test_tables.py`
drives the table functions through the real bind→init→process lifecycle
in-process; `tests/test_scalars.py` spawns `xslt_worker.py` over the VGI
client/RPC stack exactly as DuckDB would after `ATTACH`. The `test/sql/*.test`
files are DuckDB sqllogictest cases run by
[`haybarn-unittest`](https://pypi.org/project/haybarn-unittest/)
(`uv tool install haybarn-unittest`) against a real `ATTACH` + `SELECT`.

## Layout

```
xslt_worker.py           entry point; assembles the `xslt` catalog (inline uv script metadata)
Makefile                 test / test-unit / test-sql targets
vgi_xslt/
  engine.py              pure Saxon primitives: singleton processor + compile caches (only saxonche importer)
  scalars.py             per-row scalars (xslt, xpath_*, xquery, is_well_formed)
  tables.py              table functions: xpath_nodes, xquery_rows, saxon_version
  schema_utils.py        Arrow field/comment helper
tests/
  harness.py             in-process bind→init→process driver
  test_engine.py         pure-logic unit + error/edge tests
  test_tables.py         table-function integration tests
  test_scalars.py        per-row scalars via vgi.client.Client
test/sql/
  *.test                 DuckDB sqllogictest end-to-end cases (haybarn-unittest)
```

---

## Authorship & License

Written by [Query.Farm](https://query.farm) — every VGI worker is designed and built by Query.Farm.

Copyright 2026 Query Farm LLC - https://query.farm

