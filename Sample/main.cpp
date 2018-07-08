#include <QCoreApplication>
#include <QDebug>
#include "testreader.h"

int main(int argc, char *argv[])
{
	QCoreApplication a(argc, argv);

	try {
		TestReader reader;
		reader.readDocument("stuff");
		return 0;
	} catch(TestNamespace::TestClass::Exception &e) {
		qCritical() << e.what();
		return EXIT_FAILURE;
	}
}
