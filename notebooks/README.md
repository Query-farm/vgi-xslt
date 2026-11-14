# VGI XSLT notebooks

[01 · Preserve the documents behind shredded XML rows](01_preserve_documents_when_shredding_xml.ipynb) audits synthetic XML documents, transforms exact namespace matches with XSLT, serializes and shreds records with XPath, and applies an explicit quantity contract in SQL. Empty, malformed, missing and out-of-scope documents remain visible.

## Run

Install [uv](https://docs.astral.sh/uv/). From the repository root:

```sh
uv sync --project notebooks --frozen
uv run --project notebooks --frozen python notebooks/execute.py
```

The whole `notebooks/` directory also runs separately from the worker checkout:

```sh
cd notebooks
uv sync --frozen
uv run --frozen python execute.py
```

Initial setup needs network access for Python dependencies, the community VGI extension, public Git source and SaxonC's native runtime wheel. Inputs and stylesheet are authored visibly in SQL. No credentials, external XML dataset, system Saxon installation or local worker build is required. The tested platform is macOS Apple silicon with Python 3.14; other platforms need compatible SaxonC/PyArrow wheels. The worker's first Saxon operation may take longer while the native runtime initializes.

In VS Code select `notebooks/.venv/bin/python` and use `notebooks/` as the kernel working directory. Other Jupyter editors can optionally register the kernel:

```sh
uv run --project notebooks --frozen python -m ipykernel install --user --name vgi-xslt-notebooks --display-name 'Python (vgi-xslt notebooks)'
```

Restart and run all after editing parameters. Connection and analytical SQL remain expanded; setup, plotting, assertions and cleanup source are folded. Saved outputs embed both charts.

## Experiment

```sh
uv run --project notebooks --frozen python notebooks/execute.py \
  --parameters '{"MIN_QUANTITY":3}' \
  --output-dir notebooks/validation/minimum-3
```

The default minimum is 1. Raising it to 3 changes selection while preserving parsing, normalization, raw values and input coverage. Reset to 1 for the saved default. Values from 0 to 1000 are accepted; zero remains a valid authored quantity even when not selected.

The runner requires a separate output destination for overrides, rejects unknown names and saves only successful full executions. Failed runs leave existing saved notebooks unchanged. Copies include relative branding, helpers, environment and documentation. Review charts, logs and experimental copies are Git-ignored.

## Portable startup and provenance

The visible literal location uses `uvx` with the public v0.4.0 Git revision `c6384204609d5bb4a7b15b65ca54e73c3f260821`, Python 3.14, VGI Python 0.51.0, VGI RPC 0.53.1, PyArrow 26.0.1 and SaxonC 13.1.1. The notebook environment separately pins Haybarn 2.0.0rc11. The worker is not on PyPI; Git installation and its cached environment are handled by uv. Upgrading means explicitly changing the source/runtime pins and rerunning both settings.

Six documents are authored in the notebook. D1 has two order items. D2 has four order items plus a telemetry-namespace item; its order quantities include a true zero, invalid text, a missing attribute and a valid three. D3 is an empty order batch. D4 has the same local element names in a different namespace. D5 is malformed and D6 is SQL NULL. These are synthetic counts, not operational records.

The stylesheet is constant, shown in SQL and uses an explicit `urn:orders` namespace binding. It copies only intended item records and preserves a missing quantity attribute. It performs no resource fetches or stylesheet imports. The example assumes trusted, authored XML and stylesheet input; it is not a general XML sandbox or schema validator.

## Interpretation

`is_well_formed` reports parseability: malformed XML is false and SQL NULL stays NULL. Other XML functions raise errors for malformed input. We materialize successfully parsed documents before further XPath evaluation. The HE engine reports `schema_aware=false`; it does not provide XSD validation.

XPath EQNames select the exact namespace URI without prefix-binding ambiguity. The wildcard count is shown only to illustrate how a broader namespace match includes unrelated items. The XSLT stylesheet also matches the exact namespace.

`xpath_array` returns string values, not node markup by default. The explicit `serialize(.)` expression preserves row attributes before UNNEST. Document ID and ordinal identify the expanded records. Empty documents disappear from the expanded table but remain in the separate document audit, which is reconciled with row counts.

The row contract requires a nonempty SKU and a digits-only nonnegative integer quantity representable as BIGINT. SQL preserves the original text, uses a guarded TRY_CAST, and separates missing/invalid quantities from valid zero. A minimum filter is a reporting decision, not a change to source quality. Unknown quantities do not become zero or enter known-unit sums.

The six intended rows comprise four valid quantities and two invalid/missing quantities. At minimum 1, three rows contribute ten known units; at minimum 3, two rows contribute eight known units. The telemetry quantity 999 and other-namespace quantity 100 never enter the item table. The document coverage chart stays fixed.

Validation covers default and detached experiment execution, four rendered charts, twelve SQL checks plus document/row/unit reconciliations, and three runner guards. The default run took 11.6 seconds; the detached minimum-three experiment took 2.9 seconds. The document chart is byte-identical across settings; document-audit, transformed-XML and typed-item output displays also match. Source checks passed: 54 pytest tests, 76 stdio / 82 HTTP / 76 Unix SQL assertions (three cases each), Ruff, formatting, mypy and pydoclint. Metadata scored 100/100 L2 with zero findings. Source code, tests and root dependencies/lock remain unchanged.

Official Query.Farm Strata Sun and VGI artwork is copied unchanged from the approved assets, with linked Query.Farm branding at the top and bottom.
