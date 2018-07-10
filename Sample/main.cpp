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
								 << 1;
	QTest::newRow("Root2.valid") << QStringLiteral(SRCDIR "/test5.xml")
								 << true
								 << 2;
	QTest::newRow("Root3.valid") << QStringLiteral(SRCDIR "/test6.xml")
								 << true
								 << 3;
	QTest::newRow("Root4.text") << QStringLiteral(SRCDIR "/test7.xml")
								<< true
								<< 4;
	QTest::newRow("Root4.content") << QStringLiteral(SRCDIR "/test8.xml")
								   << true
								   << 4;
	QTest::newRow("Root5.text") << QStringLiteral(SRCDIR "/test9.xml")
								<< true
								<< 5;
	QTest::newRow("Root5.content") << QStringLiteral(SRCDIR "/test10.xml")
								   << true
								   << 5;
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
