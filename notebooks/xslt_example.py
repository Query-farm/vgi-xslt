"""XSLT notebook charts; namespace checks and XML transformations stay in SQL."""

from __future__ import annotations
import matplotlib.pyplot as plt
from matplotlib.ticker import MaxNLocator
from vgi_notebooks import finish

SOURCE = "Synthetic XML batches · VGI XSLT v0.4.0 · explicit namespace and row coverage"


def sql_text(value):
    """Quote a SQL string literal for visible JupySQL interpolation."""
    return "'" + str(value).replace("'", "''") + "'"


def validate_minimum(value):
    """Bound the report quantity before starting the worker."""
    if type(value) is not int or not 0 <= value <= 1000:
        raise ValueError("MIN_QUANTITY must be an integer from 0 to 1000.")


def plot_document_coverage(coverage):
    """Render the visible SQL result with explicit population and units."""
    colors = {
        "In scope; has items": "#267358",
        "In scope; zero items": "#456fba",
        "Different root namespace": "#c57b40",
        "Malformed XML": "#a95d50",
        "Missing input": "#8a9790",
    }
    fig, ax = plt.subplots(figsize=(12, 7))
    bars = ax.barh(
        coverage.document_state,
        coverage.documents,
        color=[colors[s] for s in coverage.document_state],
        height=0.55,
    )
    ax.bar_label(bars, padding=6, fontsize=12)
    ax.invert_yaxis()
    ax.set_xlim(0, int(coverage.documents.max()) + 1)
    ax.xaxis.set_major_locator(MaxNLocator(integer=True))
    ax.set_xlabel("Authored input documents · Before shredding")
    ax.grid(axis="y", visible=False)
    finish(
        fig,
        "A zero-row result has more than one cause",
        "Full document denominator · Parseability and namespace are separate checks",
        SOURCE,
        name="01_document_coverage",
    )


def plot_selected_quantities(quantities, minimum_quantity):
    """Render the visible SQL result with explicit population and units."""
    fig, ax = plt.subplots(figsize=(12, 6.5))
    bars = ax.barh(quantities.sku, quantities.selected_units, color="#267358", height=0.48)
    ax.bar_label(bars, padding=6, fontsize=12)
    ax.invert_yaxis()
    ax.set_xlim(0, max(1, int(quantities.selected_units.max())) * 1.25)
    ax.xaxis.set_major_locator(MaxNLocator(integer=True))
    ax.set_xlabel("Known units in selected valid rows")
    ax.grid(axis="y", visible=False)
    finish(
        fig,
        "Selected known units are a bounded statement",
        f"Minimum quantity: {minimum_quantity} · Invalid quantities excluded and counted separately",
        SOURCE,
        name="02_selected_quantities",
    )


def plot_rows_and_units(totals, include_zero):
    """Keep line counts and known-unit totals on separately labeled axes."""
    fig, axes = plt.subplots(1, 2, figsize=(12, 5.8))
    for ax, column, label in zip(
        axes,
        ["selected_lines", "known_units"],
        ["Selected source lines · count", "Known units · sum"],
        strict=True,
    ):
        bars = ax.barh(totals.sku, totals[column], color=["#267358", "#456fba"], height=0.5)
        ax.bar_label(bars, padding=5)
        ax.invert_yaxis()
        ax.set_xlim(0, max(1, totals[column].max()) * 1.3)
        ax.xaxis.set_major_locator(MaxNLocator(integer=True))
        ax.set_xlabel(label)
    axes[0].set_ylabel("SKU")
    finish(
        fig,
        "A zero-quantity line changes counts without changing units",
        f"Include explicit zero: {include_zero} · five source lines · one missing quantity excluded · independent axes",
        SOURCE,
        name="03_rows_and_units",
    )
