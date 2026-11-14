# XSLT and XQuery examples

[Worker repository](https://github.com/Query-farm/vgi-xslt) · [Shared notebook tools and standard](https://github.com/Query-farm/vgi-example-notebooks)

| Notebook | Investigation | Run |
|---|---|---|
| [Preserve the documents behind shredded XML rows](01_preserve_documents_when_shredding_xml.ipynb) | Audit six documents, isolate namespaces, normalize with XSLT, and retain zero/missing/invalid quantities through reporting. | [Open in Colab](https://colab.research.google.com/github/Query-farm/vgi-xslt/blob/main/notebooks/01_preserve_documents_when_shredding_xml.ipynb) |
| [The same unit total can describe different rows](02_same_units_different_row_counts.ipynb) | Compare XPath rows, XQuery rows and a scalar summary; excluding a zero line changes counts while leaving known units unchanged. | [Open in Colab](https://colab.research.google.com/github/Query-farm/vgi-xslt/blob/main/notebooks/02_same_units_different_row_counts.ipynb) |

Both notebooks have saved outputs, visible SQL, result-driven interpretation,
linked worker titles and Colab buttons. Three SVG figures remain sharp on GitHub.
GitHub displays executable code expanded; shared setup and small plotting helpers
keep these cells concise. The VGI connection remains visible.

## Run locally or in Colab

Open either Colab link and run all cells. Locally, run from this directory:

```sh
uv sync --locked
uv run --locked vgi-notebooks --timeout 300
```

Select `.venv/bin/python` for an interactive kernel. The notebook bootstrap installs
the shared base tools and preserves compatible preinstalled plotting/kernel
packages. The local environment additionally includes the runner. Its companion
is fetched from an immutable revision and SHA-256 verified, so a standalone
notebook does not require a worker checkout or copied standard/runner scripts.

Each visible ATTACH runs the public release in a separate environment:

```text
uvx --python 3.13 --from git+https://github.com/Query-farm/vgi-xslt@v0.4.0 vgi-xslt-worker
```

No SDK override is needed. First setup requires Git/network access and downloads
the SaxonC-HE native wheel. The authored XML, stylesheets and queries then run
locally with no API key or remote document retrieval. A worker release tag fixes
its code; dependency ranges can resolve newer compatible packages on future installs.

## XML scope and row meaning

The first notebook deliberately includes an empty valid batch, an unrelated
namespace, malformed XML and missing input. Parseability is materialized before
calling functions that raise on malformed XML. EQNames and explicit XSLT namespace
bindings restrict processing to the intended `urn:orders` elements. Selecting an
element's string value does not preserve its markup: explicit `serialize(.)`
retains attributes before array expansion and typed SQL extraction.

All six documents stay in the audit even when they produce no item rows. The
quantity contract is explicit: digits-only nonnegative integer text and a nonempty
SKU. An authored zero is valid; missing and nonnumeric quantities remain unknown.
The reporting minimum selects valid rows without changing source quality.

The second notebook keeps five source line IDs across two row-returning query
forms. Duplicate SKUs remain distinct lines. Result positions number the selected
sequence and can change after filtering; they are not permanent source identities.
The scalar XQuery summary is reconciled against typed row results, not compared
only by total. One missing quantity remains outside the known-quantity view.

SaxonC-HE reports `schema_aware=false`. Well-formedness, namespace scope and these
small SQL contracts do not establish XSD validity or complete business correctness.

## Run the experiments separately

Raise the first notebook's minimum from one to three:

```sh
uv run --locked vgi-notebooks 01_preserve_documents_when_shredding_xml.ipynb \
  --parameters '{"MIN_QUANTITY":3}' --output-dir artifacts/minimum-three
```

Input documents, normalized XML, raw fields and invalid-row counts should remain
unchanged. Only the selected valid rows and known-unit totals change. The accepted
range is integer `0–1000`; restore `1` for the default.

Exclude the second notebook's explicit zero:

```sh
uv run --locked vgi-notebooks 02_same_units_different_row_counts.ipynb \
  --parameters '{"INCLUDE_ZERO":false}' --output-dir artifacts/exclude-zero
```

Expect four selected lines to become three while ten known units remain ten.
Source line IDs and the unknown quantity stay fixed. Restore `True` for the default.

The shared runner requires a separate output directory for overrides, rejects
unknown parameter names and writes a notebook only after success. SQL assertions
and chart reconciliations check document/line identity, namespace scope, quantities,
row-function equivalence and aggregate consistency. SVG assets are committed for
GitHub; experiment copies and review PNGs are ignored.

[Coverage evidence](coverage.json) accounts for all ten public logical SQL surfaces.
It records actual released execution separately from current-source compatibility.
Current changes add examples/metadata; runtime implementation, schemas and root
dependencies are unchanged. Existing green source CI is reused for this notebook update.
