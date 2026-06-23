"""Pure Saxon engine: processor singleton, compile caches, and string primitives.

The singleton processor, the compile caches, and the string-in / string-out
transform / query / XPath primitives all live here.

This module is the only place that touches ``saxonche``. It deliberately has no
Arrow or VGI dependency, so it is directly unit-testable. Everything above it
(``scalars``, ``tables``) is a thin Arrow adapter over the functions here.

Design (read this before changing anything)
--------------------------------------------
1. **One ``PySaxonProcessor`` per process.** Constructing a SaxonC processor
   spins up a native (GraalVM) runtime; doing it per call is expensive and the
   native layer is unhappy with many live instances. We hold a single
   module-level processor created lazily on first use and kept for the lifetime
   of the worker process -- exactly the per-process state VGI's pooled worker
   exists to amortize.
2. **A process-wide lock.** SaxonC's processor and the compiled artifacts it
   produces are not guaranteed thread-safe. Every entry point takes
   ``_LOCK`` so concurrent calls in one worker serialize through Saxon.
3. **Compile once, run many.** Compiling a stylesheet or an XQuery is the
   expensive step; applying it is cheap. We cache compiled executables keyed on
   the *source text* via ``functools.lru_cache`` so a constant stylesheet
   applied down a column compiles exactly once.

Limitations
-----------
SaxonC-HE (the Home Edition, MPL-2.0) is **not schema-aware**: there is no XSD
validation, and schema-aware XSLT/XQuery features are unavailable. That is why
this worker exposes no ``xsd_validate`` function -- see ``CLAUDE.md``.

Errors
------
Every primitive raises :class:`XsltError` (a plain ``ValueError`` subclass) with
a clear message on malformed XML, a bad stylesheet/query, or a bad XPath. The
Arrow adapters let that propagate so DuckDB surfaces a clean error rather than
crashing the worker. The one exception is :func:`is_well_formed`, which reports
malformed XML as ``False`` instead of raising.
"""

from __future__ import annotations

import contextlib
import threading
from functools import lru_cache
from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:  # pragma: no cover - typing only
    from saxonche import (
        PySaxonProcessor,
        PyXdmNode,
        PyXPathProcessor,
        PyXQueryProcessor,
        PyXslt30Processor,
        PyXsltExecutable,
    )


class XsltError(ValueError):
    """A Saxon-side failure (bad XML, stylesheet, query, or XPath expression).

    Subclasses ``ValueError`` so callers can catch it narrowly; the Arrow
    adapters let it propagate to DuckDB as a clean error message.
    """


# Single native processor for the whole process, plus the lock guarding all
# Saxon state. Created lazily so importing this module is cheap and side-effect
# free (the native runtime only boots on first real use).
_LOCK = threading.Lock()
_PROCESSOR: PySaxonProcessor | None = None


def _processor() -> PySaxonProcessor:
    """Return the process-wide :class:`PySaxonProcessor`, creating it once.

    Must be called with ``_LOCK`` held.
    """
    global _PROCESSOR
    if _PROCESSOR is None:
        from saxonche import PySaxonProcessor

        # license=False -> SaxonC-HE (the free MPL-2.0 edition).
        _PROCESSOR = PySaxonProcessor(license=False)
    return _PROCESSOR


def version() -> str:
    """Return the SaxonC version string, e.g. ``'SaxonC-HE 13.0 from Saxonica'``."""
    with _LOCK:
        return str(_processor().version)


# ---------------------------------------------------------------------------
# Compile caches. Keyed on the source text so a constant stylesheet/query down a
# column compiles once. The cached executables live for the process lifetime
# alongside the processor that produced them.
# ---------------------------------------------------------------------------


@lru_cache(maxsize=256)
def _compiled_stylesheet(stylesheet: str) -> PyXsltExecutable:
    """Compile (and cache) an XSLT stylesheet from its source text."""
    proc = _processor()
    xslt: PyXslt30Processor = proc.new_xslt30_processor()
    try:
        executable = xslt.compile_stylesheet(stylesheet_text=stylesheet)
    except Exception as exc:  # SaxonC raises PySaxonApiError on a bad stylesheet.
        raise XsltError(f"failed to compile stylesheet: {exc}") from exc
    if executable is None:
        raise XsltError(_drain_error(xslt, "failed to compile stylesheet"))
    return executable


@lru_cache(maxsize=256)
def _compiled_query(query: str) -> PyXQueryProcessor:
    """Build (and cache) an XQuery processor with the query content set.

    The ``!omit-xml-declaration`` serialization property keeps atomic / text
    results clean (Saxon otherwise prefixes ``<?xml version="1.0"...?>`` when
    serializing a simple value).
    """
    proc = _processor()
    xq: PyXQueryProcessor = proc.new_xquery_processor()
    with contextlib.suppress(Exception):  # property is best-effort.
        xq.set_property("!omit-xml-declaration", "yes")
    try:
        xq.set_query_content(query)
    except Exception as exc:
        raise XsltError(f"failed to compile XQuery: {exc}") from exc
    return xq


def _drain_error(obj: Any, fallback: str) -> str:
    """Pull a human-readable message off a Saxon processor, else use *fallback*."""
    try:
        if getattr(obj, "exception_occurred", False):
            msg = obj.error_message
            if msg:
                return str(msg)
    except Exception:  # pragma: no cover - defensive
        pass
    return fallback


def _parse_xml(proc: PySaxonProcessor, xml: str) -> PyXdmNode:
    """Parse *xml* into an XDM node, raising :class:`XsltError` if malformed."""
    try:
        node = proc.parse_xml(xml_text=xml)
    except Exception as exc:  # Saxon raises on some malformed input.
        raise XsltError(f"malformed XML: {exc}") from exc
    if node is None:
        raise XsltError("malformed XML: could not be parsed")
    return node


# ---------------------------------------------------------------------------
# Primitives. Each is string-in / string-out (or a Python scalar / list) and
# takes the lock for the duration of the Saxon interaction.
# ---------------------------------------------------------------------------


def transform(xml: str, stylesheet: str) -> str:
    """Transform *xml* with *stylesheet* (XSLT 3.0); return the serialized result."""
    with _LOCK:
        proc = _processor()
        node = _parse_xml(proc, xml)
        executable = _compiled_stylesheet(stylesheet)
        try:
            result = executable.transform_to_string(xdm_node=node)
        except Exception as exc:
            raise XsltError(f"XSLT transform failed: {exc}") from exc
        if result is None:
            raise XsltError(_drain_error(executable, "XSLT transform produced no result"))
        return str(result)


def _xpath(proc: PySaxonProcessor, xml: str, expr: str) -> PyXPathProcessor:
    """Build an XPath processor with the parsed *xml* set as the context item."""
    node = _parse_xml(proc, xml)
    xp: PyXPathProcessor = proc.new_xpath_processor()
    xp.set_context(xdm_item=node)
    return xp


def xpath_string(xml: str, expr: str) -> str | None:
    """String value of the first node/atomic matching *expr*, or ``None`` if none."""
    with _LOCK:
        proc = _processor()
        xp = _xpath(proc, xml, expr)
        try:
            item = xp.evaluate_single(expr)
        except Exception as exc:
            raise XsltError(f"bad XPath expression: {exc}") from exc
        if item is None:
            return None
        return str(item.string_value)


def xpath_boolean(xml: str, expr: str) -> bool:
    """Effective boolean value of *expr* evaluated over *xml*."""
    with _LOCK:
        proc = _processor()
        xp = _xpath(proc, xml, expr)
        try:
            return bool(xp.effective_boolean_value(expr))
        except Exception as exc:
            raise XsltError(f"bad XPath expression: {exc}") from exc


def xpath_number(xml: str, expr: str) -> float | None:
    """Numeric value of the first match of *expr*, or ``None`` if it isn't numeric."""
    with _LOCK:
        proc = _processor()
        xp = _xpath(proc, xml, expr)
        try:
            item = xp.evaluate_single(expr)
        except Exception as exc:
            raise XsltError(f"bad XPath expression: {exc}") from exc
        if item is None:
            return None
        try:
            return float(item.string_value)
        except (TypeError, ValueError):
            return None


def xpath_array(xml: str, expr: str) -> list[str]:
    """String values of **all** matches of *expr* over *xml*, in document order.

    This is the headline shredding primitive: every node/atomic the expression
    selects becomes one element of the returned list, so an UNNEST over it
    explodes an XML document into rows.
    """
    with _LOCK:
        proc = _processor()
        xp = _xpath(proc, xml, expr)
        try:
            value = xp.evaluate(expr)
        except Exception as exc:
            raise XsltError(f"bad XPath expression: {exc}") from exc
        return _xdm_value_to_strings(value)


def _xdm_value_to_strings(value: Any) -> list[str]:
    """Flatten an XDM value (single item or sequence) into a list of strings."""
    if value is None:
        return []
    # A sequence exposes ``size`` / ``item_at``; a single item does not.
    size = getattr(value, "size", None)
    if size is None:
        return [str(value.string_value)]
    return [str(value.item_at(i).string_value) for i in range(size)]


def xquery(xml: str, query: str) -> str:
    """Run *query* (XQuery 3.1) with *xml* as the context item; serialized result."""
    with _LOCK:
        proc = _processor()
        node = _parse_xml(proc, xml)
        xq = _compiled_query(query)
        xq.set_context(xdm_item=node)
        try:
            result = xq.run_query_to_string()
        except Exception as exc:
            raise XsltError(f"XQuery failed: {exc}") from exc
        if result is None:
            raise XsltError(_drain_error(xq, "XQuery produced no result"))
        return str(result)


def xquery_items(xml: str, query: str) -> list[str]:
    """Run *query* and return the string value of each item in the result sequence."""
    with _LOCK:
        proc = _processor()
        node = _parse_xml(proc, xml)
        xq = _compiled_query(query)
        xq.set_context(xdm_item=node)
        try:
            value = xq.run_query_to_value()
        except Exception as exc:
            raise XsltError(f"XQuery failed: {exc}") from exc
        return _xdm_value_to_strings(value)


def is_well_formed(xml: str) -> bool:
    """True if *xml* parses as well-formed XML; False otherwise (never raises)."""
    with _LOCK:
        proc = _processor()
        try:
            node = proc.parse_xml(xml_text=xml)
        except Exception:
            return False
        return node is not None
