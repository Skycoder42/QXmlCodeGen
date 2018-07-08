TEMPLATE = app

QT -= gui

CONFIG += c++1z console skip_xsd_verify
CONFIG -= app_bundle

!include(../qxmlcodegen.pri):error(qxmlcodegen.pri missing)

DEFINES += QT_DEPRECATED_WARNINGS

SOURCES += \
		main.cpp \
    testreader.cpp

XML_SCHEMA_DEFINITIONS += \
	testclass.xsd

HEADERS += \
	mytype.h \
    testreader.h
