TEMPLATE = app

QT -= gui

CONFIG += c++11 console
CONFIG -= app_bundle

!include(../qxmlcodegen.pri):error(qxmlcodegen.pri missing)

DEFINES += QT_DEPRECATED_WARNINGS

SOURCES += \
		main.cpp

XML_SCHEMA_DEFINITIONS += \
	testclass.xsd
