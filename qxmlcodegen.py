#!/usr/bin/env python3
# Usage: qxmlcodegen.py [--skip-verify] <in> <out_hdr> <out_src>
# Usage: qxmlcodegen.py --verify <in> <out_hdr> <out_src>

import argparse
import requests
import sys

from io import BytesIO

try:
	from defusedxml.ElementTree import parse, ElementTree
except ImportError:
	from xml.etree.ElementTree import parse, ElementTree


def xml_verify(xsd_path, required=False):
	try:
		from lxml import etree
	except ImportError:
		if required:
			raise

	xslt_clear = etree.XML("""
	<xsl:stylesheet version="2.0" xmlns:xsl="http://www.w3.org/1999/XSL/Transform">    
		<xsl:template match="*[namespace-uri()='https://skycoder42.de/QXmlCodeGen']" priority="1"/>
		<xsl:template match="@*[namespace-uri()='https://skycoder42.de/QXmlCodeGen']" priority="1"/>
		<xsl:template match="@* | node()">
			<xsl:copy>
				<xsl:apply-templates select="@* | node()" />
			</xsl:copy>
		</xsl:template>
	</xsl:stylesheet>
	""")

	# if lxml is available: verify the xsd against the W3C scheme (excluding the qsg-stuff)
	xsd_schema_req = requests.get("https://www.w3.org/2009/XMLSchema/XMLSchema.xsd")
	xmlschema_doc = etree.parse(BytesIO(xsd_schema_req.content))
	xmlschema = etree.XMLSchema(xmlschema_doc)
	transform = etree.XSLT(xslt_clear)
	xmlschema.assertValid(transform(etree.parse(xsd_path)))


def xmlcodegen(xsd_path, hdr_path, src_path, verify=True):
	if verify:
		xml_verify(xsd_path)

	xsd = parse(xsd_path)


if __name__ == '__main__':
	parser = argparse.ArgumentParser(description="Convert an XSD to cpp code, and/or optionally verify it")
	parser.add_argument("--skip-verify", action="store_false", help="Do not verify the xsd documents validity")
	parser.add_argument("--verify", action="store_true", help="Only verify the document, do not generate cpp code")
	parser.add_argument("xsd", metavar="xsd_file", help="The XSD file to be specified")
	parser.add_argument("hdr", metavar="header_file", nargs="?", help="The c++ header file to be generated. Required for normal mode")
	parser.add_argument("src", metavar="source_file", nargs="?", help="The c++ sourcecode file to be generated. Required for normal mode")
	res = parser.parse_args(sys.argv[1:])
	if res.verify:
		xml_verify(res.xsd, required=True)
	else:
		xmlcodegen(res.xsd, res.hdr, res.src, res.skip_verify)
