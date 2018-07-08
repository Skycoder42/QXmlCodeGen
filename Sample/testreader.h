#ifndef TESTREADER_H
#define TESTREADER_H

#include "testclass.h"

class TestReader : public TestNamespace::TestClass
{
protected:
	void read_test(QXmlStreamReader &reader, StringWrapper &data, bool transform) override;
	void read_test_another(QXmlStreamReader &reader, int &data) override;
	bool read_super(QXmlStreamReader &reader, Group5 &data, bool hasNext) override;
};

#endif // TESTREADER_H
