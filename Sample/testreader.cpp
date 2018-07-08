#include "testreader.h"

void TestReader::read_test(QXmlStreamReader &reader, TestNamespace::TestClass::StringWrapper &data, bool transform)
{
	if(transform) {
		SimpleType type;
		read_SimpleType(reader, type);
		data.stringWrapper = QString::number(type.simpleType + type.faction) + type.unit;
	} else {
		Type1 type;
		read_Type1(reader, type);
		QStringList strings;
		for(const auto &simple : type.content)
			strings.append(QString::number(simple.simpleType + simple.faction) + simple.unit);
		data.stringWrapper = QStringLiteral("[%1]").arg(strings.join(QStringLiteral(", ")));
	}
}

void TestReader::read_test_another(QXmlStreamReader &reader, int &data)
{
	AnotherSimpleType type;
	read_AnotherSimpleType(reader, type);
	data = type.value.toInt();
}

bool TestReader::read_super(QXmlStreamReader &reader, TestNamespace::TestClass::Group5 &data, bool hasNext)
{
	hasNext = read_Group5(reader, data, hasNext);
	data.type2.clear();
	return hasNext;
}
