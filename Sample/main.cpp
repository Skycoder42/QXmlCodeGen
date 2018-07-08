#include <QCoreApplication>
#include <QDebug>
#include <QtTest>
#include "testreader.h"

class TestXmlCodeGen : public QObject
{
	Q_OBJECT

private Q_SLOTS:
	void testParser_data();
	void testParser();
};

void TestXmlCodeGen::testParser_data()
{
	QTest::addColumn<QString>("path");
	QTest::addColumn<bool>("success");
	QTest::addColumn<int>("resultIndex");

	QTest::newRow("RootString.valid") << QStringLiteral(SRCDIR "/test1.xml")
									  << true
									  << 0;
	QTest::newRow("RootString.invalid.root") << QStringLiteral(SRCDIR "/test2.xml")
											 << false
											 << -1;
	QTest::newRow("RootString.invalid.content.data") << QStringLiteral(SRCDIR "/test3.xml")
													 << false
													 << -1;
	QTest::newRow("Root1.valid") << QStringLiteral(SRCDIR "/test4.xml")
								 << true
								 << 0;
}

void TestXmlCodeGen::testParser()
{
	QFETCH(QString, path);
	QFETCH(bool, success);
	QFETCH(int, resultIndex);

	try {
		TestReader reader;
		if(success) {
			auto res = reader.readDocument(path);
			QCOMPARE(res.index(), static_cast<size_t>(resultIndex));
		} else
			QVERIFY_EXCEPTION_THROWN(reader.readDocument(path), TestNamespace::TestClass::Exception);
	} catch(std::exception &e) {
		if(success)
			QFAIL(e.what());
	}
}

QTEST_MAIN(TestXmlCodeGen)

#include "main.moc"
