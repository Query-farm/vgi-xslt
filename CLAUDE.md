# CLAUDE.md — vgi-xslt

Contributor/agent notes. User-facing docs live in `README.md`; this is the
"how it's built and where the sharp edges are" companion.

## What this is

A [VGI](https://query.farm) worker that brings **XSLT 3.0 / XQuery 3.1 /
XPath 3.1** into DuckDB SQL — transform, query, and **shred** XML — backed by
**SaxonC-HE** through the `saxonche` (SaxonC-HE 13.0, MPL-2.0) Python bindings.
`xslt_worker.py` assembles every function into one `xslt` catalog (single `main`
schema) over stdio. Sibling style/tooling to `vgi-conform` / `vgi-calendar`.

## Layout

```
xslt_worker.py         repo-root stdio entry point; PEP 723 inline deps; main()
vgi_xslt/
  engine.py            pure Saxon primitives; the singleton processor + compile caches; ONLY saxonche importer
  scalars.py           per-row scalars (xslt, xpath_string/boolean/number/array, xquery, is_well_formed)
  tables.py            table functions: xpath_nodes, xquery_rows, saxon_version
  schema_utils.py      pa.Field comment / column-doc helper
tests/                 pytest: test_engine (pure), test_tables (in-proc), test_scalars (Client RPC)
test/sql/*.test        haybarn-unittest sqllogictest — authoritative E2E
Makefile               test / test-unit / test-sql / lint
```

To add a function: implement the string-in / string-out logic in `engine.py`
(pure, total where possible; raise `XsltError` on bad input), wrap it as a
scalar or table function in the matching module, register it in
`xslt_worker.py`'s `_FUNCTIONS`.

## The pure-logic / Arrow-adapter split (read first)

`engine.py` is the **only** module that imports `saxonche`. It is string-in /
string-out (or returns Python scalars/lists), has no Arrow or VGI dependency,
and is therefore directly unit-testable in `tests/test_engine.py`. `scalars.py`
and `tables.py` are thin Arrow adapters that map an engine primitive across a
column, passing NULLs through. Keep new Saxon logic in `engine.py`.

## CRITICAL design: one processor, compile caches, one lock

This is the heart of the worker — do not regress it.

1. **One `PySaxonProcessor` per process.** Constructing a SaxonC processor boots
   a native (GraalVM) runtime; per-call construction is expensive and the native
   layer dislikes many live instances. `engine._PROCESSOR` is a module-level
   singleton, created **lazily** on first use (`engine._processor()`), and kept
   for the worker's lifetime — exactly the per-process state VGI's pooled worker
   exists to amortize. Never construct a second processor.
2. **Compile once, run many.** Compiling a stylesheet / building an XQuery is the
   expensive step; applying it is cheap. `_compiled_stylesheet` and
   `_compiled_query` are `functools.lru_cache`d **on the source text**, so a
   constant stylesheet down a column compiles exactly once and transforms many
   rows. The cached executables live for the process lifetime.
3. **One process-wide `threading.Lock`.** SaxonC's processor and its compiled
   artifacts are not guaranteed thread-safe. Every engine entry point acquires
   `engine._LOCK` for the whole Saxon interaction, so concurrent calls in one
   worker serialize through Saxon. (The lru_caches are also mutated under the
   lock — they aren't separately synchronized.)

## Sharp edges (learned the hard way)

1. **`haybarn-unittest` skips `require vgi`.** Under haybarn the extension is not
   autoloaded for `require`, so a `.test` using `require vgi` is silently
   SKIPPED. Use an explicit `statement ok` / `LOAD vgi;` instead (every `.test`
   here already does). `LOAD vgi` also works under the locally-built vgi
   unittest. Run the SQL suite with:
   `VGI_XSLT_WORKER="uv run --python 3.13 xslt_worker.py" haybarn-unittest --test-dir . "test/sql/*"`.
2. **A LIST return type needs an explicit `Returns(arrow_type=...)`.**
   `xpath_array` returns `VARCHAR[]`; its `compute` is annotated
   `-> Annotated[pa.ListArray, Returns(arrow_type=pa.list_(pa.string()))]`. The
   SDK **raises at class-definition time** if it can't infer the element type
   from a bare `Returns()` — the same gotcha `vgi-calendar` hit with its
   TIMESTAMPTZ scalars. Any future list/array scalar must declare its element
   type the same way.
3. **No XSD validation (HE limitation).** SaxonC-**HE** is **not schema-aware** —
   no XSD validation, no schema-aware XSLT/XQuery. There is deliberately **no
   `xsd_validate` function**. `is_well_formed` checks *well-formedness* (does it
   parse), which is the strongest XML check HE offers. PE/EE add schema
   awareness but are commercial; we stay on the free HE edition. Document this if
   asked for validation.
4. **NULL vs invalid vs error.** NULL input → NULL output (scalars) / no rows
   (tables). **Invalid** input — malformed XML, bad stylesheet/query, bad XPath —
   raises `engine.XsltError` (a `ValueError`), which the Arrow adapters let
   propagate so DuckDB shows a clean error, never a worker crash. The **one**
   exception is `is_well_formed`, which catches the malformed-XML case and
   returns `false`. SQL covers the error path with `statement error` blocks
   (malformed stylesheet, malformed XPath).
5. **Namespaces.** Saxon evaluates XPath over the document's in-scope
   namespaces. Binding an arbitrary prefix inside a single SQL string is limited
   by SaxonC's expression context; the portable patterns are the
   wildcard-namespace test `//*:item` and `local-name() = 'item'` predicates
   (both in `test_engine.py` / `xpath.test`). Document this limitation rather
   than papering over it.
6. **`evaluate` vs `evaluate_single`.** XPath `evaluate` returns a `PyXdmValue`
   (has `size` / `item_at`) or `None` when empty; `evaluate_single` returns a
   single item with `.string_value` or `None`. `_xdm_value_to_strings` handles
   both a multi-item value and a lone item; an empty result is an empty list.

## The unit suite can pass while the RPC path is broken

`test_engine.py` calls pure functions directly; only `test_scalars.py` (real
`vgi.client.Client` subprocess) and `test/sql/*.test` (real `ATTACH` + `SELECT`)
exercise the wire. **Run the SQL suite** — it's authoritative.

## Testing

```sh
uv run pytest -q              # unit: pure engine + in-proc tables + Client RPC scalars
make test-sql                 # E2E: haybarn-unittest over test/sql/*  (authoritative)
make test                     # both
uv run ruff check . && uv run mypy vgi_xslt/
```

`make test-sql` sets `VGI_XSLT_WORKER="uv run --python 3.13 xslt_worker.py"`,
puts `~/.local/bin` on PATH, and runs `haybarn-unittest --test-dir . "test/sql/*"`.
Install the runner once with `uv tool install haybarn-unittest`. CI
(`.github/workflows/ci.yml`) runs unit + lint + a gated `e2e` job that installs
haybarn-unittest and runs `make test-sql`.

Everything is offline (no network) — the first run downloads the `saxonche`
wheel (~38 MB, the bundled native runtime), after which the suite is fast and
hermetic.
