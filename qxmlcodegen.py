#!/usr/bin/env python3
# Usage: qxmlcodegen.py [--skip-verify] <in> <out_hdr> <out_src>
# Usage: qxmlcodegen.py --verify <in> <out_hdr> <out_src>

import argparse
import os
from enum import Enum

import urllib.request
import sys

from io import BytesIO, TextIOBase

try:
	from defusedxml.ElementTree import parse, ElementTree, Element
except ImportError:
	from xml.etree.ElementTree import parse, ElementTree, Element


xslt_qxg_remove_query = """
<xsl:stylesheet version="2.0" xmlns:xsl="http://www.w3.org/1999/XSL/Transform">
	<xsl:template match="*[namespace-uri()='https://skycoder42.de/xml/schemas/QXmlCodeGen']" priority="1"/>
	<xsl:template match="@*[namespace-uri()='https://skycoder42.de/xml/schemas/QXmlCodeGen']" priority="1"/>
	<xsl:template match="@* | node()">
		<xsl:copy>
			<xsl:apply-templates select="@* | node()" />
		</xsl:copy>
	</xsl:template>
</xsl:stylesheet>
"""


def xml_verify(xsd_path: str, required: bool=False):
	try:
		from lxml import etree
	except ImportError as iexc:
		if required:
			raise
		else:
			print("Skipping XSD validation because of unavailable module:", iexc, file=sys.stderr)
			return

	xslt_clear = etree.XML(xslt_qxg_remove_query)

	try:
		# if lxml is available: verify the xsd against the W3C scheme (excluding the qsg-stuff)
		xsd_schema_req = urllib.request.urlopen("https://www.w3.org/2009/XMLSchema/XMLSchema.xsd")
		xmlschema_doc = etree.parse(xsd_schema_req)
		xmlschema = etree.XMLSchema(xmlschema_doc)
		transform = etree.XSLT(xslt_clear)
		xmlschema.assertValid(transform(etree.parse(xsd_path)))
	except urllib.error.URLError as rexc:
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
	schemaUrl: str = ""

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


class QxgMethod:
	class Param:
		name: str = ""
		type_key: str = ""
		default: str = ""

		def __repr__(self):
			return "{}: {} = {}".format(self.name, self.type_key, self.default)

	name: str = ""
	type_key: str = ""
	params: list
	as_group: bool = False

	def __init__(self):
		self.params = []

	def __repr__(self):
		return "{}(data: {}, {})".format(self.name, self.type_key, self.params)


class BasicTypeDef:
	name: str = ""
	xmlType: str = ""
	cppType: str = ""

	def write_typedef(self, hdr: TextIOBase):
		hdr.write("\tusing {} = {};\n\n".format(self.name, self.cppType))

	def write_converter(self, hdr: TextIOBase):
		pass  # nothing needs to be written here


class ListBasicDef(BasicTypeDef):
	def write_typedef(self, hdr: TextIOBase):
		hdr.write("\tusing {} = QList<{}>;\n\n".format(self.name, self.cppType))

	def write_converter(self, src: TextIOBase):
		src.write("\tauto dataList = data.split(XML_CODE_GEN_REGEXP{QStringLiteral(\"\\\\s+\")}, QString::SkipEmptyParts);\n")
		src.write("\t{} resList;\n".format(self.name))
		src.write("\tresList.reserve(dataList.size());\n")
		src.write("\tfor(const auto &elem : dataList)\n")
		src.write("\t\tresList.append(convertData<{}>(reader, elem));\n".format(self.cppType))
		src.write("\treturn resList;\n")


class UnionBasicDef(BasicTypeDef):
	xmlTypeList: list
	cppTypeList: list

	def __init__(self):
		self.xmlTypeList = []
		self.cppTypeList = []

	def write_typedef(self, hdr: TextIOBase):
		hdr.write("\tusing {} = std::tuple<{}>;\n\n".format(self.name, ", ".join(self.cppTypeList)))

	def write_converter(self, src: TextIOBase):
		src.write("\tauto dataList = data.split(XML_CODE_GEN_REGEXP{QStringLiteral(\"\\\\s+\")}, QString::SkipEmptyParts);\n")
		src.write("\tif(dataList.size() != {})\n".format(len(self.cppTypeList)))
		src.write("\t\tthrowSizeError(reader, {}, dataList.size(), true);\n".format(len(self.cppTypeList)))
		src.write("\treturn std::make_tuple(\n")
		elem_index = 0
		for cppType in self.cppTypeList:
			if elem_index != 0:
				src.write(",\n")
			src.write("\t\tconvertData<{}>(reader, dataList[{}])".format(cppType, elem_index))
			elem_index += 1
		src.write("\n\t);\n")


class EnumBasicDef(BasicTypeDef):
	class EnumElement:
		xmlValue: str = ""
		key: str = ""
		value: str = ""

	baseType: str = ""
	elements: list

	def __init__(self):
		self.elements = []

	def write_typedef(self, hdr: TextIOBase):
		hdr.write("\tenum {} ".format(self.name))
		if self.baseType != "":
			hdr.write(": {} ".format(self.baseType))
		hdr.write("{\n")
		for elem in self.elements:
			hdr.write("\t\t" + elem.key)
			if elem.value != "":
				hdr.write(" = " + elem.value)
			hdr.write(",\n")
		hdr.write("\t};\n\n")

	def write_converter(self, src: TextIOBase):
		is_first = True
		for elem in self.elements:
			src.write("\t")
			if is_first:
				is_first = False
			else:
				src.write("else ")
			src.write("if(data == QStringLiteral(\"{}\"))\n".format(elem.xmlValue))
			src.write("\t\treturn {};\n".format(elem.key))
		src.write("\telse\n")
		src.write("\t\tthrowInvalidEnum(reader, data);\n")


class ContentDef:
	def is_inherited(self) -> bool:
		return False

	def inherits(self) -> list:
		return []

	def is_group_type(self) -> bool:
		return False

	def generate_type(self) -> str:
		raise NotImplementedError()

	def read_method(self) -> str:
		return "read_{}".format(self.generate_type())

	def read_method_params(self) -> str:
		return ""

	def member_name(self) -> str:
		raise NotImplementedError()

	def xml_name(self) -> str:
		raise NotImplementedError()

	def write_hdr_content(self, hdr: TextIOBase):
		try:
			if not self.is_inherited():
				hdr.write("\t\t{} {};\n".format(self.generate_type(), self.member_name()))
		except NotImplementedError:
			pass

	def write_src_content(self, src: TextIOBase, need_newline: bool, intendent: int, target_member: str = "", return_target: str = "") -> bool:
		return need_newline

	def twrite(self, out: TextIOBase, intendent: int, text: str):
		out.write("\t" * intendent)
		out.write(text)

	def write_return(self, out: TextIOBase, intendent: int, return_target: str, ok: bool):
		if return_target == "":
			if not ok:
				self.twrite(out, intendent, "throwChild(reader);\n")
		else:
			self.twrite(out, intendent, "{} = {};\n".format(return_target, "true" if ok else "false"))


class TypeContentDef(ContentDef):
	class MethodInfo:
		method: str = ""
		type_key: str = ""
		params: list

		def __init__(self):
			self.params = []

	is_group: bool = False
	name: str = ""
	member: str = ""
	type_key: str = ""
	inherit: bool = False
	is_basic_type: bool = False
	method: MethodInfo = None

	def __repr__(self):
		return self.name + "[" + self.type_key + "] " + \
			("<inherited>" if self.inherit else ("{" + self.member + "}"))

	def is_inherited(self) -> bool:
		return self.inherit

	def inherits(self) -> list:
		return [self.type_key] if self.inherit else []

	def is_group_type(self) -> bool:
		return self.is_group

	def generate_type(self) -> str:
		if self.method is None:
			return self.type_key
		else:
			return self.method.type_key

	def read_method(self) -> str:
		if self.method is not None:
			return self.method.method
		elif self.is_basic_type:
			return "readContent<{}>".format(self.type_key)
		else:
			return super(TypeContentDef, self).read_method()

	def read_method_params(self) -> str:
		if self.method is None:
			return super(TypeContentDef, self).read_method_params()
		elif len(self.method.params) == 0:
			return ""
		else:
			return ", " + ", ".join(self.method.params)

	def member_name(self) -> str:
		return self.member

	def xml_name(self) -> str:
		return self.name

	def write_src_content(self, src: TextIOBase, need_newline: bool, intendent: int, target_member: str = "", return_target: str = "") -> bool:
		if need_newline:
			src.write("\n")

		if target_member == "":
			target_member = "data." + self.member

		if self.is_group:
			if self.inherit:
				self.twrite(src, intendent, "hasNext = {}(reader, data, hasNext);\n".format(self.read_method()))
			else:
				self.twrite(src, intendent, "hasNext = {}(reader, {}, hasNext{});\n".format(self.read_method(), target_member, self.read_method_params()))
		else:
			self.twrite(src, intendent, "if(reader.name() == QStringLiteral(\"{}\")) {{\n".format(self.name))
			self.twrite(src, intendent + 1, "{}(reader, {}{});\n".format(self.read_method(), target_member, self.read_method_params()))
			self.write_return(src, intendent + 1, return_target, True)
			self.twrite(src, intendent, "} else\n")
			self.write_return(src, intendent + 1, return_target, False)

		return True


class SequenceContentDef(ContentDef):
	class Element:
		min: int = 1
		max: int = 1
		element: ContentDef = None

		def is_single(self) -> bool:
			return self.min == 1 and self.max == 1

		def is_optional(self) -> bool:
			return self.min == 0 and self.max == 1

		def __repr__(self):
			return str(self.element) + "[" + str(self.min) + ":" + str(self.max) + "]"

	elements: list

	def __init__(self):
		self.elements = []

	def __repr__(self):
		return ";\n".join(map(str, self.elements)) + ";"

	def inherits(self) -> list:
		inh = []
		for elem in self.elements:
			inh += elem.element.inherits()
		return inh

	def write_hdr_content(self, hdr: TextIOBase):
		for elem in self.elements:
			if elem.element.is_inherited():
				continue

			if elem.is_single():
				elem.element.write_hdr_content(hdr)
			elif elem.is_optional():
				hdr.write("\t\toptional<{}> {};\n".format(elem.element.generate_type(), elem.element.member_name()))
			elif isinstance(elem.element, ChoiceContentDef) and elem.element.unordered:
				elem.element.write_hdr_content(hdr)
			else:
				hdr.write("\t\tQList<{}> {};\n".format(elem.element.generate_type(), elem.element.member_name()))

	def write_src_content(self, src: TextIOBase, need_newline: bool, intendent: int, target_member: str = "", return_target: str = "") -> bool:
		if len(self.elements) == 0:
			return need_newline
		if need_newline:
			src.write("\n")

		self.twrite(src, intendent, "auto _ok = false;\n")

		for elem in self.elements:
			src.write("\n")
			if (elem.element.is_group_type() and elem.is_single()) or isinstance(elem.element, AllContentDef):
				elem.element.write_src_content(src, False, intendent,  return_target="_ok")
			elif elem.element.is_group_type():
				self.twrite(src, intendent, "data.{}.reserve({});\n".format(elem.element.member_name(), elem.max))
				self.twrite(src, intendent, "for(auto i = 0; i < {}; i++) {{\n".format(elem.max))
				self.twrite(src, intendent + 1, "{} _element;\n".format(elem.element.generate_type()))
				elem.element.write_src_content(src, False, intendent + 1, target_member="_element", return_target="_ok")
				self.twrite(src, intendent + 1, "data.{}.append(std::move(_element));\n".format(elem.element.member_name()))
				self.twrite(src, intendent, "}\n")
			elif elem.is_single():
				self.twrite(src, intendent, "if(!hasNext)\n")
				self.twrite(src, intendent + 1, "throwNoChild(reader);\n")
				elem.element.write_src_content(src, False, intendent, target_member="data" if elem.element.is_inherited() else "", return_target="_ok")
				self.twrite(src, intendent, "if(_ok) {\n")
				self.twrite(src, intendent + 1, "hasNext = reader.readNextStartElement();\n")
				self.twrite(src, intendent + 1, "checkError(reader);\n")
				self.twrite(src, intendent, "} else\n")
				self.twrite(src, intendent + 1, "throwChild(reader);\n")
			elif elem.is_optional():
				self.twrite(src, intendent, "if(hasNext) {\n")
				self.twrite(src, intendent + 1, "{} _element;\n".format(elem.element.generate_type()))
				elem.element.write_src_content(src, False, intendent + 1, target_member="_element", return_target="_ok")
				self.twrite(src, intendent + 1, "if(_ok) {\n")
				self.twrite(src, intendent + 2, "data.{} = std::move(_element);\n".format(elem.element.member_name()))
				self.twrite(src, intendent + 2, "hasNext = reader.readNextStartElement();\n")
				self.twrite(src, intendent + 2, "checkError(reader);\n")
				self.twrite(src, intendent + 1, "}\n")
				self.twrite(src, intendent, "}\n")
			elif isinstance(elem.element, ChoiceContentDef) and elem.element.unordered:
				self.twrite(src, intendent, "{\n")
				self.twrite(src, intendent + 1, "int _total = 0;\n")
				self.twrite(src, intendent + 1, "const int _max = {};\n".format(elem.max))
				need_newline = elem.element.write_src_content(src, need_newline, intendent + 1)
				if elem.min > 0:
					self.twrite(src, intendent + 1, "if(_total < {})\n".format(elem.min))
					self.twrite(src, intendent + 2, "throwSizeError(reader, {}, _total);\n".format(elem.min))
				self.twrite(src, intendent, "}\n")
			else:
				if elem.min == elem.max:
					self.twrite(src, intendent, "data.{}.reserve({});\n".format(elem.element.member_name(), elem.max))
				self.twrite(src, intendent, "while(hasNext")
				if elem.max != -1:
					src.write(" && data.{}.size() < {}".format(elem.element.member_name(), elem.max))
				src.write(") {\n")
				self.twrite(src, intendent + 1, "{} _element;\n".format(elem.element.generate_type()))
				elem.element.write_src_content(src, False, intendent + 1, target_member="_element", return_target="_ok")
				self.twrite(src, intendent + 1, "if(!_ok)\n")
				self.twrite(src, intendent + 2, "break;\n")
				self.twrite(src, intendent + 1, "data.{}.append(std::move(_element));\n".format(elem.element.member_name()))
				self.twrite(src, intendent + 1, "hasNext = reader.readNextStartElement();\n")
				self.twrite(src, intendent + 1, "checkError(reader);\n")
				self.twrite(src, intendent, "}\n")
				if elem.min > 0:
					self.twrite(src, intendent, "if(data.{}.size() < {})\n".format(elem.element.member_name(), elem.min))
					self.twrite(src, intendent + 1, "throwSizeError(reader, {}, data.{}.size());\n".format(elem.min, elem.element.member_name()))
		return True


class ChoiceContentDef(ContentDef):
	choices: list  # list of TypeContentDef
	unordered: bool = False
	member: str = ""

	def __init__(self):
		self.choices = []

	def __repr__(self):
		return "[" + " | ".join(map(str, self.choices)) + "]" if self.unordered else self.member + "<" + " | ".join(map(str, self.choices)) + ">"

	def generate_type(self) -> str:
		return "variant<{}>".format(", ".join(map(lambda c: c.generate_type(), self.choices)))

	def member_name(self) -> str:
		return self.member

	def write_hdr_content(self, hdr: TextIOBase):
		if self.unordered:
			for choice in self.choices:
				hdr.write("\t\tQList<{}> {};\n".format(choice.generate_type(), choice.member))
		else:
			super(ChoiceContentDef, self).write_hdr_content(hdr)

	def write_src_content(self, src: TextIOBase, need_newline: bool, intendent: int, target_member: str = "", return_target: str = "") -> bool:
		if len(self.choices) == 0:
			return need_newline
		if need_newline:
			src.write("\n")

		is_first = True
		if self.unordered:
			self.twrite(src, intendent, "while(hasNext && (_max == -1 || _total < _max)) {\n")

			for choice in self.choices:
				if is_first:
					is_first = False
					self.twrite(src, intendent + 1, "if")
				else:
					self.twrite(src, intendent + 1, "} else if")
				src.write("(reader.name() == QStringLiteral(\"{}\")) {{\n".format(choice.name))
				self.twrite(src, intendent + 2, "{} _element;\n".format(choice.generate_type()))
				self.twrite(src, intendent + 2, "{}(reader, _element{});\n".format(choice.read_method(), choice.read_method_params()))
				self.write_return(src, intendent + 2, return_target, True)
				self.twrite(src, intendent + 2, "data.{}.append(std::move(_element));\n".format(choice.member_name()))

			self.twrite(src, intendent + 1, "} else\n")
			self.twrite(src, intendent + 2, "break;\n")
			self.twrite(src, intendent + 1, "++_total;\n")
			self.twrite(src, intendent + 1, "hasNext = reader.readNextStartElement();\n")
			self.twrite(src, intendent + 1, "checkError(reader);\n")
			self.twrite(src, intendent, "}\n")
		else:
			if target_member == "":
				target_member = "data." + self.member
			for choice in self.choices:
				if is_first:
					is_first = False
					self.twrite(src, intendent, "if")
				else:
					self.twrite(src, intendent, "} else if")
				src.write("(reader.name() == QStringLiteral(\"{}\")) {{\n".format(choice.name))
				self.twrite(src, intendent + 1, "{} = {}{{}};\n".format(target_member, choice.generate_type()))
				self.twrite(src, intendent + 1, "{}(reader, get<{}>({}){});\n".format(choice.read_method(), choice.generate_type(), target_member, choice.read_method_params()))
				self.write_return(src, intendent + 1, return_target, True)
			self.twrite(src, intendent, "} else\n")
			self.write_return(src, intendent + 1, return_target, False)

		return True


class AllContentDef(ContentDef):
	class Element:
		optional: bool = False
		element: ContentDef = None

		def __repr__(self):
			return "[{}]".format(str(self.element)) if self.optional else str(self.element)

	elements: list

	def __init__(self):
		self.elements = []

	def __repr__(self):
		return "(" + ", ".join(map(str, self.elements)) + ")"

	def write_hdr_content(self, hdr: TextIOBase):
		for elem in self.elements:
			if elem.optional:
				hdr.write("\t\toptional<{}> {};\n".format(elem.element.generate_type(), elem.element.member_name()))
			else:
				elem.element.write_hdr_content(hdr)

	def write_src_content(self, src: TextIOBase, need_newline: bool, intendent: int, target_member: str = "", return_target: str = "") -> bool:
		if len(self.elements) == 0:
			return need_newline
		if need_newline:
			src.write("\n")

		self.twrite(src, intendent, "{\n")
		self.twrite(src, intendent + 1, "QSet<int> _usedElements;\n")
		self.twrite(src, intendent + 1, "while(hasNext) {")

		cnt = 0
		req_list = []
		for elem in self.elements:
			src.write("\n")
			if elem.optional:
				self.twrite(src, intendent + 2, "{} _element_{};\n".format(elem.element.generate_type(), cnt))
				self.twrite(src, intendent + 2, "if(reader.name() == QStringLiteral(\"{}\")) {{\n".format(elem.element.xml_name()))
				self.twrite(src, intendent + 3, "if(_usedElements.contains({}))\n".format(cnt))
				self.twrite(src, intendent + 4, "break;\n")
				self.twrite(src, intendent + 3, "{}(reader, _element_1{});\n".format(elem.element.read_method(), elem.element.read_method_params()))
				self.twrite(src, intendent + 3, "_usedElements.insert({});\n".format(cnt))
				self.twrite(src, intendent + 3, "data.{} = std::move(_element_{});\n".format(elem.element.member_name(), cnt))
				self.twrite(src, intendent + 3, "hasNext = reader.readNextStartElement();\n")
				self.twrite(src, intendent + 3, "checkError(reader);\n")
				self.twrite(src, intendent + 3, "continue;\n")
				self.twrite(src, intendent + 2, "}\n")
			else:
				self.twrite(src, intendent + 2, "if(reader.name() == QStringLiteral(\"{}\")) {{\n".format(elem.element.xml_name()))
				self.twrite(src, intendent + 3, "if(_usedElements.contains({}))\n".format(cnt))
				self.twrite(src, intendent + 4, "break;\n")
				self.twrite(src, intendent + 3, "{}(reader, data.{});\n".format(elem.element.read_method(), elem.element.member_name(), elem.element.read_method_params()))
				self.twrite(src, intendent + 3, "_usedElements.insert({});\n".format(cnt))
				self.twrite(src, intendent + 3, "hasNext = reader.readNextStartElement();\n")
				self.twrite(src, intendent + 3, "checkError(reader);\n")
				self.twrite(src, intendent + 3, "continue;\n")
				self.twrite(src, intendent + 2, "}\n")
				req_list.append(cnt)
			cnt += 1

		src.write("\n")
		self.twrite(src, intendent + 2, "break;\n")
		self.twrite(src, intendent + 1, "}\n")
		self.twrite(src, intendent + 1, "if(!_usedElements.contains(QSet<int> {{{}}}))\n".format(", ".join(map(str, req_list))))
		self.twrite(src, intendent + 2, "throwNoChild(reader);\n")
		self.twrite(src, intendent, "}\n")

		return True


class MemberDef:
	name: str = ""
	member: str = ""
	xmlType: str = ""
	cppType: str = ""

	required: bool = False
	default: str = None

	def __repr__(self):
		return self.name + ": " + self.xmlType + \
			" {" + self.member + ": " + self.cppType + \
			"} = " + str(self.default) + \
			(" (required)" if self.required else " (optional)")


class TypeDef:
	name: str = ""
	members: list
	member_groups: list
	declare: bool = False

	def __init__(self):
		self.members = []
		self.member_groups = []

	def __repr__(self):
		return self.name + " -> " + str(self.members + self.member_groups)

	def inherits(self) -> list:
		return list(map(lambda m: m.type_key, filter(lambda m: m.inherit, self.member_groups)))

	def write_hdr_content(self, hdr: TextIOBase):
		pass

	def write_src_content(self, src: TextIOBase, need_newline: bool):
		pass


class SimpleTypeDef(TypeDef):
	contentMember: str = ""
	contentXmlType: str = ""
	contentCppType: str = ""

	def __repr__(self):
		return self.name + "[" + self.contentXmlType + "]" + \
			" {" + self.contentMember + ": " + self.contentCppType + \
			"} -> " + str(self.members + self.member_groups)

	def write_hdr_content(self, hdr: TextIOBase):
		hdr.write("\t\t{} {};\n".format(self.contentCppType, self.contentMember))

	def write_src_content(self, src: TextIOBase, need_newline: bool):
		if need_newline:
			src.write("\n")
		src.write("\treadContent<{}>(reader, data.{});\n".format(self.contentCppType, self.contentMember))


class ComplexTypeDef(TypeDef):
	baseType: str = ""
	content: SequenceContentDef = None

	def __repr__(self):
		return self.name + "[" + self.baseType + "] -> " + str(self.members + self.member_groups) + " {\n" + str(self.content) + "\n}"

	def inherits(self) -> list:
		inh = []
		if self.baseType != "":
			inh.append(self.baseType)
		if self.content is not None:
			inh += self.content.inherits()
		inh += super(ComplexTypeDef, self).inherits()
		return inh

	def write_hdr_content(self, hdr: TextIOBase):
		if self.content is not None:
			self.content.write_hdr_content(hdr)

	def write_src_content(self, src: TextIOBase, need_newline: bool):
		# write base class
		if self.baseType != "":
			if need_newline:
				src.write("\n")
			need_newline = True
			src.write("\tread_{}(reader, data, true);\n".format(self.baseType))

		# write content
		if need_newline:
			src.write("\n")
		if self.baseType != "":
			src.write("\tauto hasNext = reader.isStartElement();\n")
		else:
			src.write("\tauto hasNext = reader.readNextStartElement();\n")
		if self.content is not None:
			need_newline = self.content.write_src_content(src, False, 1)
			if need_newline:
				src.write("\n")
		src.write("\tif(hasNext && !keepElementOpen)\n")
		src.write("\t\tthrowChild(reader);\n")


class MixedTypeDef(ComplexTypeDef):
	contentMember: str = ""
	contentCppType: str = ""

	def __repr__(self):
		return self.name + "[" + self.baseType + "]" + \
			" {" + self.contentMember + ": " + self.contentCppType + \
			"} -> " + str(self.members + self.member_groups) + \
			" {\n" + str(self.content) + "\n}"

	def write_hdr_content(self, hdr: TextIOBase):
		super(MixedTypeDef, self).write_hdr_content(hdr)
		hdr.write("\t\toptional<{}> {};\n".format(self.contentCppType, self.contentMember))

	def write_src_content(self, src: TextIOBase, need_newline: bool):
		# read simple content
		src.write("\tQString contentText;\n")
		src.write("\tauto canReadText = true;\n")
		src.write("\twhile(canReadText) {\n")
		src.write("\t\tswitch(reader.readNext()) {\n")
		src.write("\t\tcase QXmlStreamReader::Characters:\n")
		src.write("\t\tcase QXmlStreamReader::EntityReference:\n")
		src.write("\t\t\tcontentText.append(reader.text());\n")
		src.write("\t\t\tbreak;\n")
		src.write("\t\tcase QXmlStreamReader::StartElement:\n")
		src.write("\t\tcase QXmlStreamReader::EndElement:\n")
		src.write("\t\t\tcanReadText = false;\n")
		src.write("\t\t\tbreak;\n")
		src.write("\t\tcase QXmlStreamReader::ProcessingInstruction:\n")
		src.write("\t\tcase QXmlStreamReader::Comment:\n")
		src.write("\t\t\tbreak;\n")
		src.write("\t\tdefault:\n")
		src.write("\t\t\tthrowChild(reader);\n")
		src.write("\t\t}\n")
		src.write("\t}\n\n")

		# save simple content or...
		src.write("\tif(reader.tokenType() == QXmlStreamReader::EndElement) {\n")
		src.write("\t\tdata.{} = QVariant{{std::move(contentText)}}.value<{}>();\n".format(self.contentMember, self.contentCppType))

		# ... read complex content
		src.write("\t} else {\n")
		src.write("\t\tauto hasNext = true;\n")
		if self.content is not None:
			need_newline = self.content.write_src_content(src, False, 2)
			if need_newline:
				src.write("\n")
		src.write("\t\tif(hasNext && !keepElementOpen)\n")
		src.write("\t\t\tthrowChild(reader);\n")
		src.write("\t}\n")


class GroupTypeDef(TypeDef):
	content: SequenceContentDef = None

	def __repr__(self):
		return self.name + " -> {\n" + str(self.content) + "\n}"

	def inherits(self) -> list:
		inh = []
		if self.content is not None:
			inh += self.content.inherits()
		inh += super(GroupTypeDef, self).inherits()
		return inh

	def write_hdr_content(self, hdr: TextIOBase):
		if self.content is not None:
			self.content.write_hdr_content(hdr)

	def write_src_content(self, src: TextIOBase, need_newline: bool):
		if self.content is not None:
			self.content.write_src_content(src, need_newline, 1)
		src.write("\n\treturn hasNext;\n")


class AttrGroupTypeDef(TypeDef):
	pass


class XmlCodeGenerator:
	ns_map: dict = {
		"qxg": "https://skycoder42.de/xml/schemas/QXmlCodeGen"
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
		"xs:base64Binary": "QByteArray",  # TODO implement
		"xs:hexBinary": "QByteArray",  # TODO implement
		"xs:anyURI": "QUrl",
		"": ""  # nothing maps to nothing
	}

	config: QxgConfig
	methods: list

	def __init__(self):
		self.methods = []

	def ns_replace(self, name: str) -> str:
		ns_replace_map = {
			"{https://skycoder42.de/xml/schemas/QXmlCodeGen}": "qxg:",
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
		if "schemaUrl" in node.attrib:
			self.config.schemaUrl = node.attrib["schemaUrl"]
		if "visibility" in node.attrib:
			self.config.visibility = QxgConfig.Visibility(node.attrib["visibility"].lower())
		for child in node.findall("qxg:include", namespaces=self.ns_map):
			include = QxgConfig.Include(child.text)
			if "local" in child.attrib:
				include.local = child.attrib["local"].lower() == "true"
			self.config.includes.append(include)

	def read_method(self, node: Element) -> QxgMethod:
		method = QxgMethod()
		method.name = node.attrib["name"]
		method.type_key = node.attrib["type"]
		method.as_group = node.attrib["asGroup"].lower() == "true" if "asGroup" in node.attrib else False
		for child in node.findall("qxg:param", namespaces=self.ns_map):
			param = QxgMethod.Param()
			param.name = child.attrib["name"]
			param.type_key = child.attrib["type"]
			param.default = child.text
			method.params.append(param)
		return method

	def read_qxg(self, node: Element, attr: str, default: str, map_type: bool = False) -> str:
		rep_attr = self.ns_replace_inv("qxg:" + attr)
		if rep_attr in node.attrib:
			return node.attrib[rep_attr]
		else:
			return self.xs_type_map[default] if map_type else default

	def read_occurs(self, node: Element) -> (int, int):
		min_occurs = node.attrib["minOccurs"] if "minOccurs" in node.attrib else 1
		max_occurs = node.attrib["maxOccurs"] if "maxOccurs" in node.attrib else 1
		return int(min_occurs), -1 if max_occurs == "unbounded" else int(max_occurs)

	def read_sequence_content(self, node: Element) -> SequenceContentDef:
		sequence = SequenceContentDef()
		for child in node:
			nstag = self.ns_replace(child.tag)
			elem = SequenceContentDef.Element()
			elem.min, elem.max = self.read_occurs(child)
			if nstag == "xs:sequence":
				if not elem.is_single():
					raise Exception("A xs:sequence with not exactly 1 occurrence within a xs:sequence is not supported. Make the inner xs:sequence a xs:group")
				else:
					sub_elem = self.read_sequence_content(child)
					sequence.elements += sub_elem.elements
			elif nstag == "xs:choice":
				elem.element = self.read_choice_content(child, allow_unordered=True)
			elif nstag == "xs:all":
				raise Exception("An xs:all within a xs:sequence is not supported. Make the inner xs:all a xs:group")
			elif nstag == "xs:element" or nstag == "xs:group":
				if nstag == "xs:group" and elem.min != elem.max:
					raise Exception("xs:group elements can only appear with a fixed amount within a sequence (i.e. min == max)")
				elem.element = self.read_type_content(child, allow_inherit=elem.is_single())
			else:
				raise Exception("Unsupported element {} within a xs:sequence".format(nstag))

			if elem.element:
				sequence.elements.append(elem)
		return sequence

	def read_choice_content(self, node: Element, allow_unordered: bool = False) -> ChoiceContentDef:
		choice = ChoiceContentDef()
		choice.unordered = self.read_qxg(node, "unordered", "false").lower() == "true"
		if choice.unordered and not allow_unordered:
			raise Exception("Found qxg:unordered in xs:choice, but that is only allowed for choices that are in a xs:sequence")
		choice.member = self.read_qxg(node, "member", "")
		if choice.member == "" and not choice.unordered:
			raise Exception("A xs:choice must have an explicitly set qxg:member")

		for child in node:
			nstag = self.ns_replace(child.tag)
			if nstag == "xs:choice":
				sub_choices = self.read_choice_content(child)
				choice.choices += sub_choices.choices
			elif nstag == "xs:element":
				choice.choices.append(self.read_type_content(child, allow_unnamed=not choice.unordered))
			else:
				raise Exception("Unsupported element {} within a xs:choice".format(nstag))
		return choice

	def read_all_content(self, node: Element) -> AllContentDef:
		allc = AllContentDef()
		for child in node:
			nstag = self.ns_replace(child.tag)
			elem = AllContentDef.Element()
			omin, omax = self.read_occurs(child)
			if omin > 1 or omax != 1:
				raise Exception("Invalid occurrences on element within xs:all")
			elem.optional = omin == 0

			if nstag == "xs:choice":
				elem.element = self.read_choice_content(child)
			elif nstag == "xs:element":
				elem.element = self.read_type_content(child)
			else:
				raise Exception("Unsupported element {} within a xs:choice".format(nstag))

			if elem.element:
				allc.elements.append(elem)
		return allc

	def read_type_content(self, node: Element, allow_inherit: bool = False, allow_unnamed: bool = False) -> TypeContentDef:
		nstag = self.ns_replace(node.tag)
		content = TypeContentDef()

		inherit_mem = self.read_qxg(node, "inherit", "")
		if inherit_mem != "":
			if allow_inherit:
				content.inherit = inherit_mem.lower() == "true"
			else:
				raise Exception("Found qxg:inherit on {} - but it is not allowed in the current scope".format(nstag))

		if nstag == "xs:element":
			content.is_group = False
			content.name = node.attrib["name"]
			content.member = self.read_qxg(node, "member", content.name[0].lower() + content.name[1:])
			content.type_key = node.attrib["type"]
			if self.read_qxg(node, "basicType", "false").lower() == "true":
				content.is_basic_type = True
			elif content.type_key in self.xs_type_map:
				content.is_basic_type = True
				content.type_key = self.xs_type_map[content.type_key]
		elif nstag == "xs:group":
			content.is_group = True
			content.member = self.read_qxg(node, "member", "")
			if content.member == "" and not content.inherit and not allow_unnamed:
				raise Exception("A xs:group must have an explicitly set qxg:member or qxg:inherit set to true")
			content.type_key = node.attrib["ref"]
		else:
			raise Exception("UNREACHABLE")

		method_mem = self.read_qxg(node, "method", "")
		if method_mem != "":
			content.method = TypeContentDef.MethodInfo()
			content.method.method = method_mem
			for method in self.methods:
				if method.name == method_mem:
					content.method.type_key = method.type_key
			if content.method.type_key == "":
				raise Exception("qxg:method specified with a method that was not declared beforehand")
			for child in node.findall("qxg:param", namespaces=self.ns_map):
				content.method.params.append(child.text)

		return content

	def read_single_content(self, node: Element) -> ContentDef:
		content = None
		sub_content = None
		allow_count = False
		if sub_content is None:
			sub_content = node.find("xs:sequence", namespaces=self.ns_map)
			if sub_content is not None:
				content = self.read_sequence_content(sub_content)
		if sub_content is None:
			sub_content = node.find("xs:choice", namespaces=self.ns_map)
			if sub_content is not None:
				content = self.read_choice_content(sub_content)
				allow_count = True
		if sub_content is None:
			sub_content = node.find("xs:all", namespaces=self.ns_map)
			if sub_content is not None:
				content = self.read_all_content(sub_content)
		if sub_content is None:
			sub_content = node.find("xs:element", namespaces=self.ns_map)
			if sub_content is not None:
				content = self.read_type_content(sub_content, allow_inherit=True)
				allow_count = True
		if sub_content is None:
			sub_content = node.find("xs:group", namespaces=self.ns_map)
			if sub_content is not None:
				content = self.read_type_content(sub_content, allow_inherit=True)
				allow_count = True

		# if applicable: apply count
		if content is not None and not isinstance(content, SequenceContentDef):
			elem = SequenceContentDef.Element()
			if allow_count:
				elem.min, elem.max = self.read_occurs(sub_content)
				if (elem.min != 1 or elem.max != 1) and isinstance(content, TypeContentDef) and content.inherit:
					raise Exception("Found qxg:inherit on {} - but it is not allowed in combination with occurs".format(self.ns_replace(sub_content.tag)))
			elem.element = content
			content = SequenceContentDef()
			content.elements.append(elem)

		return content

	def read_attribs(self, node: Element) -> (list, list):
		members = []
		for attrib in node.findall("xs:attribute", namespaces=self.ns_map):
			member = MemberDef()
			member.xmlType = attrib.attrib["type"]
			member.cppType = self.read_qxg(attrib, "type", member.xmlType, map_type=True)
			member.name = attrib.attrib["name"]
			member.member = self.read_qxg(attrib, "member", member.name)
			member.default = attrib.attrib["default"] if "default" in attrib.attrib else None
			member.required = (attrib.attrib["use"] if "use" in attrib.attrib else "optional").lower() == "required"
			members.append(member)

		member_groups = []
		for attrib in node.findall("xs:attributeGroup", namespaces=self.ns_map):
			member = TypeContentDef()
			member.is_group = True

			inherit_mem = self.read_qxg(attrib, "inherit", "")
			if inherit_mem != "":
				member.inherit = inherit_mem.lower() == "true"

			member.member = self.read_qxg(attrib, "member", "")
			if member.member == "" and not member.inherit:
				raise Exception("A xs:attributeGroup must have an explicitly set qxg:member or qxg:inherit set to true")
			member.type_key = attrib.attrib["ref"]
			member_groups.append(member)

		return members, member_groups

	def read_type(self, node: Element) -> TypeDef:
		content_node = None
		type_def = None
		mixed = node.attrib["mixed"].lower() == "true" if "mixed" in node.attrib else False

		# check for simple content
		if content_node is None:
			content_node = node.find("xs:simpleContent", namespaces=self.ns_map)
			if content_node is not None:
				content_node = content_node.find("xs:extension", namespaces=self.ns_map)
				if content_node is None:
					raise Exception("Only xs:simpleContent elements with an xs:extension as child are allowed")
				type_def = SimpleTypeDef()
				type_def.contentXmlType = content_node.attrib["base"]
		# check for complex content
		if content_node is None:
			content_node = node.find("xs:complexContent", namespaces=self.ns_map)
			if content_node is not None:
				content_node = content_node.find("xs:extension", namespaces=self.ns_map)
				if content_node is None:
					raise Exception("Only xs:complexContent elements with an xs:extension as child are allowed")
				if mixed:
					type_def = MixedTypeDef()
					if "base" in content_node.attrib:
						raise Exception("xs:complexType definition that have a xs:base and are xs:mixed are not supported")
				else:
					type_def = ComplexTypeDef()
					type_def.baseType = content_node.attrib["base"]
		# otherwise expect "normal" complex content
		if content_node is None:
			content_node = node
			type_def = MixedTypeDef() if mixed else ComplexTypeDef()

		# extract the name and optiona declare
		type_def.name = node.attrib["name"]
		type_def.declare = self.read_qxg(node, "declare", "false").lower() == "true"
		# simple or mixed: content type
		if isinstance(type_def, SimpleTypeDef) or isinstance(type_def, MixedTypeDef):
			base_type = type_def.contentXmlType if isinstance(type_def, SimpleTypeDef) else "xs:string"
			type_def.contentCppType = self.read_qxg(content_node, "type", base_type, map_type=True)
			type_def.contentMember = self.read_qxg(content_node, "member", (type_def.name[0].lower() + type_def.name[1:]))
		# extract all attributes
		type_def.members, type_def.member_groups = self.read_attribs(content_node)
		# complex: content elements
		if isinstance(type_def, ComplexTypeDef):
			type_def.content = self.read_single_content(content_node)

		return type_def

	def read_group(self, node: Element) -> GroupTypeDef:
		type_def = GroupTypeDef()
		type_def.name = node.attrib["name"]
		type_def.content = self.read_single_content(node)
		return type_def

	def read_attr_group(self, node: Element) -> AttrGroupTypeDef:
		type_def = AttrGroupTypeDef()
		type_def.name = node.attrib["name"]
		type_def.members, type_def.member_groups = self.read_attribs(node)
		return type_def

	def read_simple_list_type(self, node: Element) -> ListBasicDef:
		type_def = ListBasicDef()
		type_def.xmlType = node.attrib["itemType"]
		type_def.cppType = self.read_qxg(node, "type", type_def.xmlType, map_type=True)
		return type_def

	def read_simple_union_type(self, node: Element) -> UnionBasicDef:
		type_def = UnionBasicDef()
		type_def.xmlTypeList = node.attrib["memberTypes"].split(" ")
		for type in type_def.xmlTypeList:
			type_def.cppTypeList.append(self.xs_type_map[type])
		return type_def

	def read_simple_enum_type(self, node: Element) -> EnumBasicDef:
		type_def = None
		for elem in node.findall("xs:enumeration", namespaces=self.ns_map):
			if type_def is None:
				type_def = EnumBasicDef()
			element = EnumBasicDef.EnumElement()
			element.xmlValue = elem.attrib["value"]
			element.key = self.read_qxg(elem, "key", element.xmlValue)
			element.value = self.read_qxg(elem, "value", "")
			type_def.elements.append(element)

		if type_def is None:
			type_def = BasicTypeDef()
			type_def.xmlType = node.attrib["base"]
		type_def.cppType = self.read_qxg(node, "type", type_def.xmlType, map_type=True)

		return type_def

	def read_simple_type(self, node: Element) -> BasicTypeDef:
		basic_def = None
		if basic_def is None:
			content_node = node.find("xs:list", namespaces=self.ns_map)
			if content_node is not None:
				basic_def = self.read_simple_list_type(content_node)
		if basic_def is None:
			content_node = node.find("xs:union", namespaces=self.ns_map)
			if content_node is not None:
				basic_def = self.read_simple_union_type(content_node)
		if basic_def is None:
			content_node = node.find("xs:restriction", namespaces=self.ns_map)
			if content_node is not None:
				basic_def = self.read_simple_enum_type(content_node)
		if basic_def is None:
			raise Exception("Unable to find xs:list, xs:union or xs:restriction in xs:simpleType")

		basic_def.name = node.attrib["name"]
		return basic_def

	def write_hdr_begin(self, hdr: TextIOBase, hdr_path: str):
		inc_guard = os.path.basename(hdr_path).upper().replace(".", "_")
		hdr.write("#ifndef {}\n".format(inc_guard))
		hdr.write("#define {}\n\n".format(inc_guard))

		if self.config.stdcompat:
			hdr.write("#include \"optional.hpp\"\n")
			hdr.write("#include \"variant.hpp\"\n")
		else:
			hdr.write("#include <optional>\n")
			hdr.write("#include <variant>\n")
		hdr.write("#include <tuple>\n")
		hdr.write("#include <exception>\n\n")

		hdr.write("#include <QtCore/QString>\n")
		hdr.write("#include <QtCore/QList>\n")
		hdr.write("#include <QtCore/QFileDevice>\n")
		hdr.write("#include <QtCore/QXmlStreamReader>\n")
		hdr.write("#include <QtCore/QVariant>\n")
		for include in self.config.includes:
			if include.local:
				hdr.write("#include \"{}\"\n".format(include.include))
			else:
				hdr.write("#include <{}>\n".format(include.include))
		hdr.write("\n")

		if self.config.ns != "":
			hdr.write("namespace {} {{\n\n".format(self.config.ns))

		hdr.write("class {}\n".format(self.config.prefix + " " + self.config.className if self.config.prefix != "" else self.config.className))
		hdr.write("{\n")
		hdr.write("\tQ_DISABLE_COPY({})\n".format(self.config.className))
		hdr.write("public:\n")
		if self.config.stdcompat:
			hdr.write("\ttemplate <typename... TArgs>\n")
			hdr.write("\tusing optional = nonstd::optional<TArgs...>;\n")
			hdr.write("\ttemplate <typename... TArgs>\n")
			hdr.write("\tusing variant = nonstd::variant<TArgs...>;\n")
			hdr.write("\ttemplate <typename TGet, typename... TArgs>\n")
			hdr.write("\tstatic inline Q_DECL_CONSTEXPR auto get(TArgs&&... args) -> decltype(nonstd::get<TGet>(std::forward<TArgs>(args)...)) {\n")
			hdr.write("\t\treturn nonstd::get<TGet>(std::forward<TArgs>(args)...);\n")
			hdr.write("\t}\n\n")
		else:
			hdr.write("\ttemplate <typename... TArgs>\n")
			hdr.write("\tusing optional = std::optional<TArgs...>;\n")
			hdr.write("\ttemplate <typename... TArgs>\n")
			hdr.write("\tusing variant = std::variant<TArgs...>;\n")
			hdr.write("\ttemplate <typename TGet, typename... TArgs>\n")
			hdr.write("\tstatic inline Q_DECL_CONSTEXPR auto get(TArgs&&... args) -> decltype(std::get<TGet>(std::forward<TArgs>(args)...)) {\n")
			hdr.write("\t\treturn std::get<TGet>(std::forward<TArgs>(args)...);\n")
			hdr.write("\t}\n\n")

		hdr.write("\tclass Exception : public std::exception\n")
		hdr.write("\t{\n")
		hdr.write("\tpublic:\n")
		hdr.write("\t\tException();\n\n")
		hdr.write("\t\tQString qWhat() const;\n")
		hdr.write("\t\tconst char *what() const noexcept final;\n\n")
		hdr.write("\tprotected:\n")
		hdr.write("\t\tvirtual QString createQWhat() const = 0;\n\n")
		hdr.write("\t\tmutable QByteArray _qWhat;\n")
		hdr.write("\t};\n\n")

		hdr.write("\tclass FileException : public Exception\n")
		hdr.write("\t{\n")
		hdr.write("\tpublic:\n")
		hdr.write("\t\tFileException(QFileDevice &device);\n\n")
		hdr.write("\t\tQString filePath() const;\n")
		hdr.write("\t\tQString errorMessage() const;\n\n")
		hdr.write("\tprotected:\n")
		hdr.write("\t\tQString createQWhat() const override;\n\n")
		hdr.write("\t\tconst QString _path;\n")
		hdr.write("\t\tconst QString _error;\n")
		hdr.write("\t};\n\n")

		hdr.write("\tclass XmlException : public Exception\n")
		hdr.write("\t{\n")
		hdr.write("\tpublic:\n")
		hdr.write("\t\tXmlException(QXmlStreamReader &reader, const QString &customError = {});\n")
		hdr.write("\t\tXmlException(QString path, qint64 line, qint64 column, QString error);\n\n")
		hdr.write("\t\tQString filePath() const;\n")
		hdr.write("\t\tqint64 line() const;\n")
		hdr.write("\t\tqint64 column() const;\n")
		hdr.write("\t\tQString errorMessage() const;\n\n")
		hdr.write("\tprotected:\n")
		hdr.write("\t\tQString createQWhat() const override;\n\n")
		hdr.write("\t\tconst QString _path;\n")
		hdr.write("\t\tconst qint64 _line;\n")
		hdr.write("\t\tconst qint64 _column;\n")
		hdr.write("\t\tconst QString _error;\n")
		hdr.write("\t};\n\n")

		hdr.write("\t{}();\n".format(self.config.className))
		hdr.write("\tvirtual ~{}();\n\n".format(self.config.className))

	def write_hdr__simple_types(self, hdr: TextIOBase, type_defs: list):
		for type_def in type_defs:
			type_def.write_typedef(hdr)


	def write_hdr_types(self, hdr: TextIOBase, type_defs: list):
		if self.config.visibility is QxgConfig.Visibility.Private:
			hdr.write("protected:\n")

		has_predefs = False
		for type_def in type_defs:
			if type_def.declare:
				has_predefs = True
				hdr.write("\tstruct {};\n".format(type_def.name))
		if has_predefs:
			hdr.write("\n")

		for type_def in type_defs:
			# write inherits
			hdr.write("\tstruct " + type_def.name)
			inh = type_def.inherits()
			if len(inh) > 0:
				hdr.write(" : public " + ", public ".join(inh))
			hdr.write("\n\t{\n")
			# write attribs
			for member in type_def.members:
				if not member.required and member.default is None:
					hdr.write("\t\toptional<{}> {};\n".format(member.cppType, member.member))
				else:
					hdr.write("\t\t{} {};\n".format(member.cppType, member.member))
			for member in type_def.member_groups:
				if not member.inherit:
					hdr.write("\t\t{} {};\n".format(member.type_key, member.member))
			# write content
			type_def.write_hdr_content(hdr)
			#write end
			hdr.write("\t};\n\n")

	def write_hdr_methods(self, hdr: TextIOBase, type_defs: list, root_elements: list):
		type_args = root_elements[0].generate_type() if len(root_elements) == 1 else "variant<{}>".format(", ".join(map(lambda t: t.generate_type(), root_elements)))
		hdr.write("\tvirtual {} readDocument(QIODevice *device);\n".format(type_args))
		hdr.write("\tvirtual {} readDocument(const QString &path);\n\n".format(type_args))

		if self.config.visibility is QxgConfig.Visibility.Protected:
			hdr.write("protected:\n")

		for method in self.methods:
			if method.as_group:
				hdr.write("\tvirtual bool ")
			else:
				hdr.write("\tvirtual void ")
			hdr.write("{}(QXmlStreamReader &reader, {} &data".format(method.name, method.type_key))
			if method.as_group:
				hdr.write(", bool hasNext")
			for param in method.params:
				hdr.write(", {} {}".format(param.type_key, param.name))
				if param.default != "":
					hdr.write(" = {}".format(param.default))
			hdr.write(") = 0;\n")
		if len(self.methods) > 0:
			hdr.write("\n")

		for type_def in type_defs:
			if isinstance(type_def, GroupTypeDef):
				hdr.write("\tvirtual bool read_{}(QXmlStreamReader &reader, {} &data, bool hasNext);\n".format(type_def.name, type_def.name))
			elif isinstance(type_def, ComplexTypeDef):
				hdr.write("\tvirtual void read_{}(QXmlStreamReader &reader, {} &data, bool keepElementOpen = false);\n".format(type_def.name, type_def.name))
			else:
				hdr.write("\tvirtual void read_{}(QXmlStreamReader &reader, {} &data);\n".format(type_def.name, type_def.name))

	def write_hdr_end(self, hdr: TextIOBase, simple_types: list):
		hdr.write("\n\ttemplate <typename T>\n")
		hdr.write("\tT convertData(QXmlStreamReader &reader, const QString &data) const;\n\n")

		hdr.write("\ttemplate <typename T>\n")
		hdr.write("\toptional<T> readOptionalAttrib(QXmlStreamReader &reader, const QString &key) const;\n")
		hdr.write("\ttemplate <typename T>\n")
		hdr.write("\tT readOptionalAttrib(QXmlStreamReader &reader, const QString &key, const QString &defaultValue) const;\n")
		hdr.write("\ttemplate <typename T>\n")
		hdr.write("\tT readRequiredAttrib(QXmlStreamReader &reader, const QString &key) const;\n\n")

		hdr.write("\ttemplate <typename T>\n")
		hdr.write("\tvoid readContent(QXmlStreamReader &reader, T &data) const;\n\n")

		hdr.write("\tvoid checkError(QXmlStreamReader &reader) const;\n")
		hdr.write("\tQ_NORETURN void throwChild(QXmlStreamReader &reader) const;\n")
		hdr.write("\tQ_NORETURN void throwNoChild(QXmlStreamReader &reader) const;\n")
		hdr.write("\tQ_NORETURN void throwInvalidSimple(QXmlStreamReader &reader) const;\n")
		hdr.write("\tQ_NORETURN void throwSizeError(QXmlStreamReader &reader, int minValue, int currentValue, bool exactSize = false) const;\n")
		hdr.write("\tQ_NORETURN void throwInvalidEnum(QXmlStreamReader &reader, const QString &text) const;\n")
		hdr.write("};\n\n")

		hdr.write("template <typename T>\n")
		hdr.write("T {}::convertData(QXmlStreamReader &reader, const QString &data) const\n".format(self.config.className))
		hdr.write("{\n")
		hdr.write("\tQ_UNUSED(reader)\n")
		hdr.write("\treturn QVariant{data}.template value<T>();\n")
		hdr.write("}\n\n")

		hdr.write("template <typename T>\n")
		hdr.write("{}::optional<T> {}::readOptionalAttrib(QXmlStreamReader &reader, const QString &key) const\n".format(self.config.className, self.config.className))
		hdr.write("{\n")
		hdr.write("\tif(reader.attributes().hasAttribute(key))\n")
		hdr.write("\t\treturn convertData<T>(reader, reader.attributes().value(key).toString());\n")
		hdr.write("\telse\n")
		hdr.write("\t\treturn optional<T>{};\n")
		hdr.write("}\n\n")

		hdr.write("template <typename T>\n")
		hdr.write("T {}::readOptionalAttrib(QXmlStreamReader &reader, const QString &key, const QString &defaultValue) const\n".format(self.config.className))
		hdr.write("{\n")
		hdr.write("\tif(reader.attributes().hasAttribute(key))\n")
		hdr.write("\t\treturn convertData<T>(reader, reader.attributes().value(key).toString());\n")
		hdr.write("\telse\n")
		hdr.write("\t\treturn convertData<T>(reader, defaultValue);\n")
		hdr.write("}\n\n")

		hdr.write("template <typename T>\n")
		hdr.write("T {}::readRequiredAttrib(QXmlStreamReader &reader, const QString &key) const\n".format(self.config.className))
		hdr.write("{\n")
		hdr.write("\tif(reader.attributes().hasAttribute(key))\n")
		hdr.write("\t\treturn convertData<T>(reader, reader.attributes().value(key).toString());\n")
		hdr.write("\telse\n")
		hdr.write("\t\tthrow XmlException{reader, QStringLiteral(\"Required attribute \\\"%1\\\" but was not set\").arg(key)};\n")
		hdr.write("}\n\n")

		hdr.write("template <typename T>\n")
		hdr.write("void {}::readContent(QXmlStreamReader &reader, T &data) const\n".format(self.config.className))
		hdr.write("{\n")
		hdr.write("\tauto content = reader.readElementText(QXmlStreamReader::ErrorOnUnexpectedElement);\n")
		hdr.write("\tcheckError(reader);\n")
		hdr.write("\tdata = convertData<T>(reader, content);\n")
		hdr.write("}\n\n")

		for type_def in simple_types:
			type_name = "{}::{}".format(self.config.className, type_def.name)
			hdr.write("template <>\n")
			hdr.write("{} {}::convertData<{}>(QXmlStreamReader &reader, const QString &data) const;\n\n".format(type_name, self.config.className, type_name))

		if self.config.ns != "":
			hdr.write("}\n\n")
		hdr.write("#endif\n")

	def write_src_begin(self, src: TextIOBase, hdr_path: str):
		src.write("#include \"{}\"\n".format(os.path.basename(hdr_path)))
		src.write("#include <QtCore/QFile>\n")
		src.write("#include <QtCore/QSet>\n")
		src.write("#if QT_CONFIG(regularexpression) == 1\n")
		src.write("#include <QtCore/QRegularExpression>\n")
		src.write("#define XML_CODE_GEN_REGEXP QRegularExpression\n")
		src.write("#else\n")
		src.write("#include <QtCore/QRegExp>\n")
		src.write("#define XML_CODE_GEN_REGEXP QRegExp\n")
		src.write("#endif\n")
		if self.config.schemaUrl != "":
			src.write("#ifdef QT_XMLPATTERNS_LIB\n")
			src.write("#include <QtCore/QDebug>\n")
			src.write("#include <QtCore/QBuffer>\n")
			src.write("#include <QtXmlPatterns/QXmlSchema>\n")
			src.write("#include <QtXmlPatterns/QXmlSchemaValidator>\n")
			src.write("#include <QtXmlPatterns/QXmlQuery>\n")
			src.write("#include <QtXmlPatterns/QAbstractMessageHandler>\n")
			src.write("#endif\n")
		if self.config.ns != "":
			src.write("using namespace {};\n".format(self.config.ns))

		if self.config.schemaUrl != "":
			src.write("\n#ifdef QT_XMLPATTERNS_LIB\n")
			src.write("namespace {\n\n")
			src.write("class ExceptionMessageHandler : public QAbstractMessageHandler\n")
			src.write("{\n")
			src.write("public:\n")
			src.write("\texplicit inline ExceptionMessageHandler(QObject *parent = nullptr) :\n")
			src.write("\t\tQAbstractMessageHandler{parent}\n")
			src.write("\t{}\n\n")
			src.write("protected:\n")
			src.write("\tvoid handleMessage(QtMsgType type, const QString &description, const QUrl &identifier, const QSourceLocation &sourceLocation) override\n")
			src.write("\t{\n")
			src.write("\t\tQ_UNUSED(identifier)\n")
			src.write("\t\tauto msg = description;\n")
			src.write("\t\tmsg.remove(XML_CODE_GEN_REGEXP{QStringLiteral(\"<[^>]*>\")});\n")
			src.write("\t\t{}::XmlException exception{{sourceLocation.uri().isLocalFile() ? sourceLocation.uri().toLocalFile() : sourceLocation.uri().toString(), sourceLocation.line(), sourceLocation.column(), msg}};\n".format(self.config.className))
			src.write("\t\tswitch(type) {\n")
			src.write("\t\tcase QtDebugMsg:\n")
			src.write("\t\t\tqDebug() << exception.what();\n")
			src.write("\t\t\tbreak;\n")
			src.write("\t\tcase QtInfoMsg:\n")
			src.write("\t\t\tqInfo() << exception.what();\n")
			src.write("\t\t\tbreak;\n")
			src.write("\t\tcase QtWarningMsg:\n")
			src.write("\t\t\tqWarning() << exception.what();\n")
			src.write("\t\t\tbreak;\n")
			src.write("\t\tdefault:\n")
			src.write("\t\t\tthrow exception;\n")
			src.write("\t\t}\n")
			src.write("\t}\n")
			src.write("};\n\n")
			src.write("}\n")
			src.write("#endif\n")

		src.write("\n{}::{}() = default;\n\n".format(self.config.className, self.config.className))
		src.write("{}::~{}() = default;\n\n".format(self.config.className, self.config.className))

	def write_src_root(self, src: TextIOBase, root_elements: list):
		if len(root_elements) == 1:
			type_args = root_elements[0].generate_type()
		else:
			type_args = "variant<{}::{}>".format(self.config.className, ", {}::".format(self.config.className).join(map(lambda t: t.generate_type(), root_elements)))

		# device method
		src.write("{}::{} {}::readDocument(QIODevice *device)\n".format(self.config.className, type_args, self.config.className))
		src.write("{\n")
		src.write("\tQ_ASSERT_X(device && device->isReadable(), Q_FUNC_INFO, \"Passed device must be open and readable\");\n")
		src.write("\tQXmlStreamReader reader{device};\n")
		src.write("\tif(!reader.readNextStartElement())\n")
		src.write("\t\tthrow XmlException{reader};\n\n")

		is_first = True
		for root in root_elements:
			if is_first:
				src.write("\t")
				is_first = False
			else:
				src.write(" else ")
			src.write("if(reader.name() == QStringLiteral(\"{}\")) {{\n".format(root.name))
			src.write("\t\t{} data;\n".format(root.generate_type()))
			src.write("\t\t{}(reader, data{});\n".format(root.read_method(), root.read_method_params()))
			src.write("\t\treturn data;\n")
			src.write("\t}")
		src.write(" else\n")
		src.write("\t\tthrowChild(reader);\n")
		src.write("}\n\n")

		# file method (the only one that can verify a pattern)
		src.write("{}::{} {}::readDocument(const QString &path)\n".format(self.config.className, type_args, self.config.className))
		src.write("{\n")

		if self.config.schemaUrl != "":
			src.write("#ifdef QT_XMLPATTERNS_LIB\n")
			src.write("\tQUrl schemaUrl{{QStringLiteral(\"{}\")}};\n".format(self.config.schemaUrl))
			src.write("\tExceptionMessageHandler errorHandler;\n")
			src.write("\tQBuffer xmlBuffer;\n")
			src.write("\txmlBuffer.open(QIODevice::ReadWrite);\n\n")

			src.write("\tQXmlQuery query(QXmlQuery::XSLT20);\n")
			src.write("\tquery.setMessageHandler(&errorHandler);\n")
			src.write("\tquery.setFocus(schemaUrl);\n")
			src.write("\tquery.setQuery(QStringLiteral(R\"___({})___\"));\n".format(xslt_qxg_remove_query))
			src.write("\tauto ok = query.evaluateTo(&xmlBuffer);\n")
			src.write("\tQ_ASSERT(ok);\n\n")

			src.write("\tQXmlSchema schema;\n")
			src.write("\tschema.setMessageHandler(&errorHandler);\n")
			src.write("\txmlBuffer.seek(0);\n")
			src.write("\tok = schema.load(&xmlBuffer, schemaUrl);\n")
			src.write("\tQ_ASSERT(ok);\n\n")

			src.write("\tQXmlSchemaValidator validator;\n")
			src.write("\tvalidator.setMessageHandler(&errorHandler);\n")
			src.write("\tvalidator.setSchema(schema);\n")
			src.write("\tok = validator.validate(QUrl::fromLocalFile(path));\n")
			src.write("\tQ_ASSERT(ok);\n")
			src.write("#endif\n\n")

		src.write("\tQFile xmlFile{path};\n")
		src.write("\tif(!xmlFile.open(QIODevice::ReadOnly | QIODevice::Text))\n")
		src.write("\t\tthrow FileException{xmlFile};\n")
		src.write("\treturn readDocument(&xmlFile);\n")
		src.write("}\n\n")

	def write_src_types(self, src: TextIOBase, type_defs: list):
		for type_def in type_defs:
			if isinstance(type_def, GroupTypeDef):
				src.write("bool {}::read_{}(QXmlStreamReader &reader, {} &data, bool hasNext)\n".format(self.config.className, type_def.name, type_def.name))
			elif isinstance(type_def, ComplexTypeDef):
				src.write("void {}::read_{}(QXmlStreamReader &reader, {} &data, bool keepElementOpen)\n".format(self.config.className, type_def.name, type_def.name))
			else:
				src.write("void {}::read_{}(QXmlStreamReader &reader, {} &data)\n".format(self.config.className, type_def.name, type_def.name))
			src.write("{\n")

			# write attribs
			need_newline = len(type_def.members) > 0
			for member in type_def.members:
				if member.required:
					src.write("\tdata.{} = readRequiredAttrib<{}>(reader, QStringLiteral(\"{}\"));\n".format(member.member, member.cppType, member.name))
				else:
					src.write("\tdata.{} = readOptionalAttrib<{}>(reader, QStringLiteral(\"{}\")".format(member.member, member.cppType, member.name))
					if member.default is not None:
						src.write(", QStringLiteral(\"{}\")".format(member.default))
					src.write(");\n")

			# write attrib grps
			if len(type_def.member_groups) > 0:
				if need_newline:
					src.write("\n")
				need_newline = True
			for member in type_def.member_groups:
				if member.inherit:
					src.write("\tread_{}(reader, data);\n".format(member.type_key))
				else:
					src.write("\tread_{}(reader, data.{});\n".format(member.type_key, member.member))

			# write content
			type_def.write_src_content(src, need_newline)

			src.write("}\n\n")

	def write_src_end(self, src: TextIOBase, simple_types: list):
		src.write("void {}::checkError(QXmlStreamReader &reader) const\n".format(self.config.className))
		src.write("{\n")
		src.write("\tif(reader.hasError())\n")
		src.write("\t\tthrow XmlException{reader};\n")
		src.write("}\n\n")

		src.write("void {}::throwChild(QXmlStreamReader &reader) const\n".format(self.config.className))
		src.write("{\n")
		src.write("\tthrow XmlException{reader, QStringLiteral(\"Unexpected child element: %1\").arg(reader.name())};\n")
		src.write("}\n\n")

		src.write("void {}::throwNoChild(QXmlStreamReader &reader) const\n".format(self.config.className))
		src.write("{\n")
		src.write("\tthrow XmlException{reader, QStringLiteral(\"Unexpected end of element \\\"%1\\\". Expected more child elements\").arg(reader.name())};\n")
		src.write("}\n\n")

		src.write("void {}::throwInvalidSimple(QXmlStreamReader &reader) const\n".format(self.config.className))
		src.write("{\n")
		src.write("\tthrow XmlException{reader, QStringLiteral(\"Mixed content elements with a base class cannot have the base read any content\")};\n")
		src.write("}\n\n")

		src.write("void {}::throwSizeError(QXmlStreamReader &reader, int minValue, int currentValue, bool exactSize) const\n".format(self.config.className))
		src.write("{\n")
		src.write("\tthrow XmlException{reader, QStringLiteral(\"Expected %1 %2 child elements, but found %3\")\n")
		src.write("\t\t.arg(exactSize ? QStringLiteral(\"exactly\") : QStringLiteral(\"at least\"))\n")
		src.write("\t\t.arg(minValue)\n")
		src.write("\t\t.arg(currentValue)\n")
		src.write("\t};\n")
		src.write("}\n\n")

		src.write("void {}::throwInvalidEnum(QXmlStreamReader &reader, const QString &text) const\n".format(self.config.className))
		src.write("{\n")
		src.write("\tthrow XmlException{reader, QStringLiteral(\"Found unexpected value \\\"%1\\\" for restricted enum\").arg(text)};\n")
		src.write("}\n\n")

		for type_def in simple_types:
			type_name = "{}::{}".format(self.config.className, type_def.name)
			src.write("template <>\n")
			src.write("{} {}::convertData<{}>(QXmlStreamReader &reader, const QString &data) const\n".format(type_name, self.config.className, type_name))
			src.write("{\n")
			type_def.write_converter(src)
			src.write("}\n\n")

		src.write("\n\n{}::Exception::Exception() = default;\n\n".format(self.config.className))

		src.write("QString {}::Exception::qWhat() const\n".format(self.config.className))
		src.write("{\n")
		src.write("\tif(_qWhat.isNull())\n")
		src.write("\t\t _qWhat = createQWhat().toUtf8();\n")
		src.write("\treturn QString::fromUtf8(_qWhat);\n")
		src.write("}\n\n")

		src.write("const char *{}::Exception::what() const noexcept\n".format(self.config.className))
		src.write("{\n")
		src.write("\tif(_qWhat.isNull())\n")
		src.write("\t\t _qWhat = createQWhat().toUtf8();\n")
		src.write("\treturn _qWhat.constData();\n")
		src.write("}\n\n\n\n")

		src.write("{}::FileException::FileException(QFileDevice &device) :\n".format(self.config.className))
		src.write("\tException{},\n")
		src.write("\t_path{device.fileName()},\n")
		src.write("\t_error{device.errorString()}\n")
		src.write("{}\n\n")

		src.write("QString {}::FileException::filePath() const\n".format(self.config.className))
		src.write("{\n")
		src.write("\treturn _path;\n")
		src.write("}\n\n")

		src.write("QString {}::FileException::errorMessage() const\n".format(self.config.className))
		src.write("{\n")
		src.write("\treturn _error;\n")
		src.write("}\n\n")

		src.write("QString {}::FileException::createQWhat() const\n".format(self.config.className))
		src.write("{\n")
		src.write("\treturn QStringLiteral(\"%1: %2\").arg(_path, _error);\n")
		src.write("}\n\n\n\n")

		src.write("{}::XmlException::XmlException(QXmlStreamReader &reader, const QString &customError) :\n".format(self.config.className))
		src.write("\tException{},\n")
		src.write("\t_path{dynamic_cast<QFileDevice*>(reader.device()) ? static_cast<QFileDevice*>(reader.device())->fileName() : QStringLiteral(\"<unknown>\")},\n")
		src.write("\t_line{reader.lineNumber()},\n")
		src.write("\t_column{reader.columnNumber()},\n")
		src.write("\t_error{customError.isNull() ? reader.errorString() : customError}\n")
		src.write("{}\n\n")

		src.write("{}::XmlException::XmlException(QString path, qint64 line, qint64 column, QString error) :\n".format(self.config.className))
		src.write("\tException{},\n")
		src.write("\t_path{std::move(path)},\n")
		src.write("\t_line{std::move(line)},\n")
		src.write("\t_column{std::move(column)},\n")
		src.write("\t_error{std::move(error)}\n")
		src.write("{}\n\n")

		src.write("QString {}::XmlException::filePath() const\n".format(self.config.className))
		src.write("{\n")
		src.write("\treturn _path;\n")
		src.write("}\n\n")

		src.write("qint64 {}::XmlException::line() const\n".format(self.config.className))
		src.write("{\n")
		src.write("\treturn _line;\n")
		src.write("}\n\n")

		src.write("qint64 {}::XmlException::column() const\n".format(self.config.className))
		src.write("{\n")
		src.write("\treturn _column;\n")
		src.write("}\n\n")

		src.write("QString {}::XmlException::errorMessage() const\n".format(self.config.className))
		src.write("{\n")
		src.write("\treturn _error;\n")
		src.write("}\n\n")

		src.write("QString {}::XmlException::createQWhat() const\n".format(self.config.className))
		src.write("{\n")
		src.write("\treturn QStringLiteral(\"%1:%2:%3: %4\").arg(_path).arg(_line).arg(_column).arg(_error);\n")
		src.write("}\n")

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

		# read type definitions
		type_defs = []
		simple_types = []
		root_elements = []
		for child in root:
			xtag = self.ns_replace(child.tag)
			if xtag == "xs:complexType":
				type_defs.append(self.read_type(child))
			elif xtag == "xs:element":
				root_elements.append(self.read_type_content(child))
			elif xtag == "xs:group":
				type_defs.append(self.read_group(child))
			elif xtag == "xs:attributeGroup":
				type_defs.append(self.read_attr_group(child))
			elif xtag == "xs:simpleType":
				s_type = self.read_simple_type(child)
				simple_types.append(s_type)
				self.xs_type_map[s_type.name] = s_type.name
			elif xtag == "qxg:method":
				self.methods.append(self.read_method(child))
			elif xtag[0:4] == "qxg:":
				pass
			else:
				raise Exception("XSD-Type {} is not supported as top level element".format(xtag))

		with open(hdr_path, "w") as hdr:
			self.write_hdr_begin(hdr, hdr_path)
			self.write_hdr__simple_types(hdr, simple_types)
			self.write_hdr_types(hdr, type_defs)
			self.write_hdr_methods(hdr, type_defs, root_elements)
			self.write_hdr_end(hdr, simple_types)

		with open(src_path, "w") as src:
			self.write_src_begin(src, hdr_path)
			self.write_src_root(src, root_elements)
			self.write_src_types(src, type_defs)
			self.write_src_end(src, simple_types)


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
