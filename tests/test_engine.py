"""Unit tests for the pure Saxon engine primitives in ``engine``.

Strong error / edge coverage: malformed XML, empty strings, bad XPath
expressions, expressions matching nothing, namespaced documents, a real XSLT
identity + value-extract transform, and an XQuery FLWOR returning a sequence.
The engine is string-in / string-out (no Arrow/VGI), so these call it directly.
"""

from __future__ import annotations

import pytest

from vgi_xslt import engine

# A small reusable identity stylesheet (XSLT 3.0).
_IDENTITY = (
    '<xsl:stylesheet version="3.0" xmlns:xsl="http://www.w3.org/1999/XSL/Transform">'
    '<xsl:template match="@*|node()">'
    '<xsl:copy><xsl:apply-templates select="@*|node()"/></xsl:copy>'
    "</xsl:template>"
    "</xsl:stylesheet>"
)

# A value-extract stylesheet that pulls one element's text into <out>.
_EXTRACT = (
    '<xsl:stylesheet version="3.0" xmlns:xsl="http://www.w3.org/1999/XSL/Transform">'
    '<xsl:output method="xml" omit-xml-declaration="yes"/>'
    '<xsl:template match="/"><out><xsl:value-of select="//name"/></out></xsl:template>'
    "</xsl:stylesheet>"
)


class TestVersion:
    def test_version_mentions_saxon(self) -> None:
        assert "Saxon" in engine.version()


class TestTransform:
    def test_identity_roundtrips_content(self) -> None:
        out = engine.transform("<doc><n>hi</n></doc>", _IDENTITY)
        assert "<n>hi</n>" in out

    def test_value_extract(self) -> None:
        out = engine.transform("<p><name>Ada</name></p>", _EXTRACT)
        assert out.strip() == "<out>Ada</out>"

    def test_malformed_xml_raises(self) -> None:
        with pytest.raises(engine.XsltError):
            engine.transform("<doc><n>hi</doc>", _IDENTITY)

    def test_bad_stylesheet_raises(self) -> None:
        with pytest.raises(engine.XsltError):
            engine.transform("<doc/>", "<not-a-stylesheet/>")

    def test_empty_xml_raises(self) -> None:
        with pytest.raises(engine.XsltError):
            engine.transform("", _IDENTITY)

    def test_compile_cache_reuses(self) -> None:
        # Same stylesheet text twice -> one compiled executable.
        engine._compiled_stylesheet.cache_clear()
        engine.transform("<a><name>x</name></a>", _EXTRACT)
        engine.transform("<b><name>y</name></b>", _EXTRACT)
        info = engine._compiled_stylesheet.cache_info()
        assert info.hits >= 1


class TestXPathString:
    def test_first_match(self) -> None:
        assert engine.xpath_string("<r><a>x</a><a>y</a></r>", "//a") == "x"

    def test_no_match_is_none(self) -> None:
        assert engine.xpath_string("<r><a>x</a></r>", "//z") is None

    def test_attribute(self) -> None:
        assert engine.xpath_string('<r id="42"/>', "string(/r/@id)") == "42"

    def test_bad_expression_raises(self) -> None:
        with pytest.raises(engine.XsltError):
            engine.xpath_string("<r/>", "//[broken")

    def test_malformed_xml_raises(self) -> None:
        with pytest.raises(engine.XsltError):
            engine.xpath_string("<r>", "//a")


class TestXPathBoolean:
    def test_true(self) -> None:
        assert engine.xpath_boolean("<r><a/></r>", "count(//a) = 1") is True

    def test_false(self) -> None:
        assert engine.xpath_boolean("<r><a/></r>", "count(//a) = 2") is False

    def test_existence(self) -> None:
        assert engine.xpath_boolean("<r><a/></r>", "exists(//a)") is True
        assert engine.xpath_boolean("<r><a/></r>", "exists(//z)") is False

    def test_bad_expression_raises(self) -> None:
        with pytest.raises(engine.XsltError):
            engine.xpath_boolean("<r/>", "count(")


class TestXPathNumber:
    def test_number(self) -> None:
        assert engine.xpath_number("<r><n>42</n></r>", "number(//n)") == 42.0

    def test_count(self) -> None:
        assert engine.xpath_number("<r><i/><i/><i/></r>", "count(//i)") == 3.0

    def test_non_numeric_is_none(self) -> None:
        assert engine.xpath_number("<r><n>abc</n></r>", "//n") is None

    def test_no_match_is_none(self) -> None:
        assert engine.xpath_number("<r/>", "//z") is None


class TestXPathArray:
    def test_all_matches(self) -> None:
        assert engine.xpath_array("<r><i>a</i><i>b</i><i>c</i></r>", "//i") == ["a", "b", "c"]

    def test_single_match_is_one_element(self) -> None:
        assert engine.xpath_array("<r><i>only</i></r>", "//i") == ["only"]

    def test_no_match_is_empty(self) -> None:
        assert engine.xpath_array("<r><i>a</i></r>", "//z") == []

    def test_atomic_sequence(self) -> None:
        # An XPath returning atomic values, not nodes.
        assert engine.xpath_array("<r/>", "(1, 2, 3)") == ["1", "2", "3"]

    def test_attributes(self) -> None:
        xml = '<r><i k="1"/><i k="2"/></r>'
        assert engine.xpath_array(xml, "//i/@k") == ["1", "2"]

    def test_bad_expression_raises(self) -> None:
        with pytest.raises(engine.XsltError):
            engine.xpath_array("<r/>", "//[oops")


class TestNamespaces:
    XML = '<r xmlns:n="http://example.com/ns"><n:item>x</n:item><n:item>y</n:item></r>'

    def test_declared_namespace_in_expression(self) -> None:
        # XPath 3.1 in-scope namespace via fn:* not needed: use a wildcard or
        # a namespace-qualified path through Saxon's expression context.
        assert engine.xpath_array(self.XML, "//*:item") == ["x", "y"]

    def test_local_name_predicate(self) -> None:
        assert engine.xpath_string(self.XML, "//*[local-name() = 'item']") == "x"


class TestXQuery:
    def test_string_join(self) -> None:
        assert engine.xquery("<r><i>a</i><i>b</i></r>", 'string-join(//i, ",")') == "a,b"

    def test_flwor_sequence(self) -> None:
        items = engine.xquery_items("<r><i>1</i><i>2</i><i>3</i></r>", "for $x in //i return $x * 2")
        assert items == ["2", "4", "6"]

    def test_arithmetic(self) -> None:
        assert engine.xquery("<r/>", "1 + 2") == "3"

    def test_bad_query_raises(self) -> None:
        with pytest.raises(engine.XsltError):
            engine.xquery("<r/>", "for $x in")

    def test_malformed_xml_raises(self) -> None:
        with pytest.raises(engine.XsltError):
            engine.xquery("<r>", "//i")


class TestIsWellFormed:
    def test_well_formed(self) -> None:
        assert engine.is_well_formed("<a><b/></a>") is True

    def test_malformed_is_false_not_error(self) -> None:
        assert engine.is_well_formed("<a><b></a>") is False

    def test_empty_is_false(self) -> None:
        assert engine.is_well_formed("") is False

    def test_garbage_is_false(self) -> None:
        assert engine.is_well_formed("not xml at all") is False

    def test_namespaced_well_formed(self) -> None:
        assert engine.is_well_formed('<r xmlns:n="http://x/"><n:a/></r>') is True
