"""Composed example queries that combine several of the worker's functions.

Each constant is a ``(description, sql)`` pair defined exactly once and reused by
the schema-level ``vgi.example_queries`` list (``worker.py``) and by the example
list of the object that drives the query (``scalars.py`` / ``tables.py``). The
SQL is offline and deterministic; ``test/sql/composed.test`` pins every result.
"""

from __future__ import annotations

# xquery_rows (one serialized <book> per row) -> xpath_string / xpath_number per row.
RECORDS_TO_COLUMNS = (
    "Explode a catalog into one serialized <book> per row with xquery_rows, then pull each "
    "book's title, lang attribute and numeric price out of that row with xpath_string and "
    "xpath_number (Dune/en/9.99, Candide/fr/7.5, Emma/en/12.0).",
    "SELECT r.seq, xslt.main.xpath_string(r.value, '/book/title') AS title, "
    "xslt.main.xpath_string(r.value, 'string(/book/@lang)') AS lang, "
    "xslt.main.xpath_number(r.value, '/book/price') AS price "
    "FROM xslt.main.xquery_rows("
    '\'<catalog><book lang="en"><title>Dune</title><price>9.99</price></book>'
    '<book lang="fr"><title>Candide</title><price>7.5</price></book>'
    '<book lang="en"><title>Emma</title><price>12</price></book></catalog>\', '
    "'for $b in /catalog/book return serialize($b)') AS r ORDER BY r.seq",
)

# is_well_formed filter -> xpath_string + xpath_number over the surviving rows.
VALIDATE_THEN_EXTRACT = (
    "Skip malformed documents with is_well_formed, then read each remaining order's id "
    "attribute and customer with xpath_string and its total (sum of qty * price over its "
    "lines) with xpath_number; the malformed order C3 is dropped (A1/acme/21.5, B7/globex/38.0).",
    "WITH docs(id, doc) AS (VALUES "
    '(1, \'<order id="A1"><customer>acme</customer><line sku="bolt" qty="2" price="9.5"/>'
    '<line sku="nut" qty="10" price="0.25"/></order>\'), '
    '(2, \'<order id="B7"><customer>globex</customer><line sku="bolt" qty="4" price="9.5"/></order>\'), '
    "(3, '<order id=\"C3\"><customer>initech</order>')) "
    "SELECT id, xslt.main.xpath_string(doc, 'string(/order/@id)') AS order_id, "
    "xslt.main.xpath_string(doc, '/order/customer') AS customer, "
    "xslt.main.xpath_number(doc, 'sum(//line/(@qty * @price))') AS total "
    "FROM docs WHERE xslt.main.is_well_formed(doc) ORDER BY id",
)

# xpath_array + UNNEST (line rows, zipped by position) tagged with xpath_string, then aggregated.
SHRED_AND_AGGREGATE = (
    "Shred the lines of a column of order documents with two position-aligned "
    "UNNEST(xpath_array(...)) calls, tag each line with its order's customer via xpath_string, "
    "and total the quantity per SKU (bolt 6 from acme,globex; nut 10 from acme).",
    "WITH docs(id, doc) AS (VALUES "
    '(1, \'<order id="A1"><customer>acme</customer><line sku="bolt" qty="2"/>'
    '<line sku="nut" qty="10"/></order>\'), '
    '(2, \'<order id="B7"><customer>globex</customer><line sku="bolt" qty="4"/></order>\')), '
    "lines AS (SELECT xslt.main.xpath_string(doc, '/order/customer') AS customer, "
    "UNNEST(xslt.main.xpath_array(doc, '//line/@sku')) AS sku, "
    "CAST(UNNEST(xslt.main.xpath_array(doc, '//line/@qty')) AS INTEGER) AS qty FROM docs) "
    "SELECT sku, CAST(SUM(qty) AS BIGINT) AS total_qty, "
    "string_agg(customer, ',' ORDER BY customer) AS customers "
    "FROM lines GROUP BY sku ORDER BY sku",
)

# xslt output (a normalized document) fed straight into the xpath_nodes table function.
TRANSFORM_THEN_SHRED = (
    "Normalize a feed with an XSLT stylesheet (one upper-cased <item> per <entry>), then shred "
    "the transformed output into numbered rows with xpath_nodes (1 A, 2 B).",
    "SELECT seq, value FROM xslt.main.xpath_nodes(xslt.main.xslt("
    "'<feed><entry><t>a</t></entry><entry><t>b</t></entry></feed>', "
    '\'<xsl:stylesheet version="3.0" xmlns:xsl="http://www.w3.org/1999/XSL/Transform">'
    '<xsl:template match="/"><items><xsl:for-each select="//entry">'
    '<item><xsl:value-of select="upper-case(t)"/></item></xsl:for-each></items>'
    "</xsl:template></xsl:stylesheet>'), '//item') ORDER BY seq",
)

#: Every composed example, in the order they appear in the schema-level list.
ALL = (RECORDS_TO_COLUMNS, VALIDATE_THEN_EXTRACT, SHRED_AND_AGGREGATE, TRANSFORM_THEN_SHRED)
