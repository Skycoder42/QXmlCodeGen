#!/usr/bin/env python3
# Usage: qxmlcodegen.py [--skip-verify] <in> <out_hdr> <out_src>
# Usage: qxmlcodegen.py --verify <in> <out_hdr> <out_src>

import argparse
import os
from enum import Enum

import requests
import sys

from io import BytesIO, TextIOBase

try:
	from defusedxml.ElementTree import parse, ElementTree, Element
except ImportError:
	from xml.etree.ElementTree import parse, ElementTree, Element


def xml_verify(xsd_path: str, required: bool=False):
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

	try:
		# if lxml is available: verify the xsd against the W3C scheme (excluding the qsg-stuff)
		xsd_schema_req = requests.get("https://www.w3.org/2009/XMLSchema/XMLSchema.xsd")
		xmlschema_doc = etree.parse(BytesIO(xsd_schema_req.content))
		xmlschema = etree.XMLSchema(xmlschema_doc)
		transform = etree.XSLT(xslt_clear)
		xmlschema.assertValid(transform(etree.parse(xsd_path)))
	except requests.exceptions.RequestException as rexc:
		if required:
			raise
		else:
			print("Skipping XSD validation because of network error:", rexc, file=sys.stderr)


class QxgConfig:
	class Visibility(Enum):
		Public = "public"
		Protected = "protected"
		Private = "private"

	class Include:
		include: str
		local: bool

		def __init__(self, inc: str, local: bool = False):
			self.include = inc
			self.local = local

		def __repr__(self):
			return ("\"{}\"" if self.local else "<{}>").format(self.include)

	className: str = ""
	prefix: str = ""
	ns: str = ""
	visibility: Visibility = Visibility.Protected
	includes: list
	stdcompat: bool = False

	def __init__(self, xsd_path = None):
		self.includes = []
		if xsd_path is not None:
			self.className = os.path.splitext(os.path.basename(xsd_path))[0].title()

	def __repr__(self):
		return "QxgConfig{className='" + self.className + \
			"', prefix='" + self.prefix + \
			"', ns='" + self.ns + \
			"', visibility=" + str(self.visibility) + \
			", includes=" + str(self.includes) + \
			", stdcompat=" + str(self.stdcompat) + "}"


class MemberDef:
	name: str = ""
	member: str = ""
	xmlType: str = ""
	cppType: str = ""

	required: bool = False
	default: str = ""

	def __repr__(self):
		return self.name + ": " + self.xmlType + " {" + self.member + ": " + self.cppType + "}"


class TypeDef:
	xmlName: str = ""
	cppName: str = ""
	members: list

	def __init__(self):
		self.members = []

	def __repr__(self):
		return self.xmlName + " {" + self.cppName + "} -> " + str(self.members)


class SimpleTypeDef(TypeDef):
	contentMember: str = ""
	contentXmlType: str = ""
	contentCppType: str = ""

	def __repr__(self):
		return self.xmlName + "[" + self.contentXmlType + "]" + \
			" {" + self.cppName + "[" + self.contentMember + ": " + self.contentCppType + "]" + \
			"} -> " + str(self.members)


class ComplexTypeDef(TypeDef):
	baseType: str = ""

	def __repr__(self):
		return self.xmlName + "[" + self.baseType + "]" + \
			" {" + self.cppName + \
			"} -> " + str(self.members)


class GroupTypeDef(TypeDef):
	pass


class AttrGroupTypeDef(TypeDef):
	pass


class XmlCodeGenerator:
	ns_map: dict = {
		"qxg": "https://skycoder42.de/QXmlCodeGen"
	}

	xs_type_map: dict = {
		"xs:string": "QString",
		"xs:normalizedString": "QString",
		"xs:token": "QString",
		"xs:language": "QLocale",
		"xs:decimal": "qreal",
		"xs:double": "double",
		"xs:float": "float",
		"xs:integer": "int",
		"xs:byte": "qint8",
		"xs:short": "qint16",
		"xs:int": "qint32",
		"xs:long": "qint64",
		"xs:unsignedByte": "quint8",
		"xs:unsignedShort": "quint16",
		"xs:unsignedInt": "quint32",
		"xs:unsignedLong": "quint64",
		"xs:boolean": "bool",
		"xs:date": "QDate",
		"xs:time": "QTime",
		"xs:dateTime": "QDateTime",
		"xs:base64Binary": "QByteArray",
		"xs:hexBinary": "QByteArray",
		"xs:anyURI": "QUrl",
	}

	config: QxgConfig
	hdr: TextIOBase
	src: TextIOBase

	def twrite(self, indent: int, text: str):
		self.hdr.write("\t" * indent)
		self.hdr.write(text)

	def ns_replace(self, name: str) -> str:
		ns_replace_map = {
			"{https://skycoder42.de/QXmlCodeGen}": "qxg:",
			"{http://www.w3.org/2001/XMLSchema}": "xs:",
			"{https://www.w3.org/2001/XMLSchema}": "xs:",
			"{http://www.w3.org/2009/XMLSchema/XMLSchema}": "xs:",
			"{https://www.w3.org/2009/XMLSchema/XMLSchema}": "xs:"
		}
		for key, rep in ns_replace_map.items():
			name = name.replace(key, rep)
		return name

	def ns_replace_inv(self, name: str) -> str:
		for key, rep in self.ns_map.items():
			name = name.replace(key + ":", "{" + rep + "}")
		return name

	def read_config(self, node: Element):
		self.config = QxgConfig()
		if "class" in node.attrib:
			self.config.className = node.attrib["class"]
		if "prefix" in node.attrib:
			self.config.prefix = node.attrib["prefix"]
		if "ns" in node.attrib:
			self.config.ns = node.attrib["ns"]
		if "stdcompat" in node.attrib:
			self.config.stdcompat = node.attrib["stdcompat"].lower() == "true"
		if "visibility" in node.attrib:
			self.config.visibility = QxgConfig.Visibility(node.attrib["visibility"].lower())
		for child in node.findall("qxg:include", namespaces=self.ns_map):
			include = QxgConfig.Include(child.text)
			if "local" in child.attrib:
				include.local = child.attrib["local"].lower() == "true"
			self.config.includes.append(include)

	def read_qxg(self, node: Element, attr: str, default: str) -> str:
		rep_attr = self.ns_replace_inv("qxg:" + attr)
		if rep_attr in node.attrib:
			return node.attrib[rep_attr]
		else:
			return default

	def read_type(self, node: Element) -> TypeDef:
		content_node = None
		type_def = None

		# check for simple content
		if content_node is None:
			content_node = node.find("xs:simpleContent", namespaces=self.ns_map)
			if content_node is not None:
				content_node = content_node.find("xs:extension", namespaces=self.ns_map)
				if content_node is None:
					raise Exception("Only xs:simpleContent elements with an xs:extension as child are allowed")

				# read the simple type stuff
				type_def = SimpleTypeDef()
				# read content type later
				type_def.contentXmlType = content_node.attrib["base"]
				type_def.contentCppType = self.read_qxg(content_node, "type", type_def.contentXmlType)
		# check for complex content
		if content_node is None:
			content_node = node.find("xs:complexContent", namespaces=self.ns_map)
			if content_node is not None:
				content_node = content_node.find("xs:extension", namespaces=self.ns_map)
				if content_node is None:
					raise Exception("Only xs:complexContent elements with an xs:extension as child are allowed")
				type_def = ComplexTypeDef()
				type_def.baseType = content_node.attrib["base"]
		# otherwise expect "normal" complex content
		if content_node is None:
			content_node = node
			type_def = ComplexTypeDef()

		# extract the name
		type_def.xmlName = node.attrib["name"]
		type_def.cppName = self.read_qxg(node, "class", type_def.xmlName)
		# simple: content type
		if isinstance(type_def, SimpleTypeDef):
			type_def.contentMember = self.read_qxg(content_node, "member", type_def.cppName.lower())

		# extract all attributes
		for attrib in content_node.findall("xs:attribute", namespaces=self.ns_map):
			member = MemberDef()
			# type
			member.xmlType = attrib.attrib["type"]
			member.cppType = self.read_qxg(attrib, "type", member.xmlType)
			# name
			member.name = attrib.attrib["name"]
			member.member = self.read_qxg(attrib, "member", member.name)

			# append
			type_def.members.append(member)

		print(type_def)
		return type_def

	def write_hdr_begin(self, hdr_path: str):
		inc_guard = os.path.basename(hdr_path).upper().replace(".", "_")
		self.hdr.write("#ifndef {}\n".format(inc_guard))
		self.hdr.write("#define {}\n\n".format(inc_guard))

		if self.config.stdcompat:
			self.hdr.write("#include \"optional.hpp\"\n")
			self.hdr.write("#include \"variant.hpp\"\n\n")
		else:
			self.hdr.write("#include <optional>\n")
			self.hdr.write("#include <variant>\n\n")

		self.hdr.write("#include <QtCore/QString>\n")
		self.hdr.write("#include <QtCore/QList>\n")
		for include in self.config.includes:
			if include.local:
				self.hdr.write("#include \"{}\"\n".format(include.include))
			else:
				self.hdr.write("#include <{}>\n".format(include.include))
		self.hdr.write("\n")

		if self.config.ns != "":
			self.hdr.write("namespace {} {{\n\n".format(self.config.ns))

		self.hdr.write("class {}\n".format(self.config.prefix + " " + self.config.className if self.config.prefix != "" else self.config.className))
		self.hdr.write("{\n")
		self.hdr.write("public:\n")
		self.hdr.write("\t{}();\n\n".format(self.config.className))

		if self.config.visibility is QxgConfig.Visibility.Private:
			self.hdr.write("protected:\n")

	def xmlcodegen(self, xsd_path: str, hdr_path: str, src_path: str, verify: bool = True):
		if verify:
			xml_verify(xsd_path)

		# parse the document and verify it's a schema
		xsd = parse(xsd_path)
		root = xsd.getroot()
		self.ns_map["xs"] = root.tag[1:root.tag.index('}')]
		# read config
		conf_node = root.find("qxg:config", namespaces=self.ns_map)
		if conf_node is None:
			self.config = QxgConfig(xsd_path)
		else:
			self.read_config(conf_node)
		print(self.config)

		# read type definitions
		type_defs = []
		for child in root:
			xtag = self.ns_replace(child.tag)
			if xtag == "xs:complexType":
				type_defs.append(self.read_type(child))
			elif xtag == "xs:element":
				print("ELEM")
			elif xtag == "xs:group":
				print("AGRP")
			elif xtag == "xs:attributeGroup":
				print("GRP")
			elif xtag[0:4] == "qxg:":
				pass
			else:
				raise Exception("XSD-Type {} is not supported as top level element".format(child.tag))

		with open(hdr_path, "w") as hdr:
			self.hdr = hdr
			with open(src_path, "w") as src:
				self.src = src

				# write hdr/src begin
				self.write_hdr_begin(hdr_path)

				# write hdr/src end


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
		XmlCodeGenerator().xmlcodegen(res.xsd, res.hdr, res.src, res.skip_verify)
