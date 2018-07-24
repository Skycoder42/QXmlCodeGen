TEMPLATE = app

QT = core testlib

CONFIG += c++1z console skip_xsd_verify
CONFIG -= app_bundle

!include(../qxmlcodegen.pri):error(qxmlcodegen.pri missing)

DEFINES += QT_DEPRECATED_WARNINGS
DEFINES += SRCDIR=\\\"$$_PRO_FILE_PWD_\\\"

SOURCES += \
		main.cpp \
	testreader.cpp

XML_SCHEMA_DEFINITIONS += \
	testclass.xsd

HEADERS += \
	mytype.h \
	testreader.h

DISTFILES += \
    test1.xml \
    test2.xml \
    test3.xml \
    test4.xml \
    test5.xml \
    test6.xml \
    test7.xml \
    test8.xml \
    test9.xml
