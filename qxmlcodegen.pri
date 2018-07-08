DISTFILES += \
	$$PWD/qxmlcodegen.py

isEmpty(XMLCODEGEN_DIR):XMLCODEGEN_DIR = .
isEmpty(MOC_DIR):MOC_DIR = .

debug_and_release {
	CONFIG(debug, debug|release):SUFFIX = /debug
	CONFIG(release, debug|release):SUFFIX = /release
}

XMLCODEGEN_DIR = $$XMLCODEGEN_DIR$$SUFFIX
skip_xsd_verify: XMLCODEGEN_ARGS = --skip-verify

xmlcodegen_c.name = qxmlcodegen.py ${QMAKE_FILE_IN}
xmlcodegen_c.input = XML_SCHEMA_DEFINITIONS
xmlcodegen_c.variable_out = XMLCODEGEN_HEADERS
win32: xmlcodegen_c.commands = python $$XMLCODEGEN_ARGS $$PWD/qxmlcodegen.py ${QMAKE_FILE_IN} ${QMAKE_FILE_OUT} $$XMLCODEGEN_DIR/${QMAKE_FILE_BASE}$${first(QMAKE_EXT_CPP)}
else: xmlcodegen_c.commands = $$PWD/qxmlcodegen.py $$XMLCODEGEN_ARGS ${QMAKE_FILE_IN} ${QMAKE_FILE_OUT} $$XMLCODEGEN_DIR/${QMAKE_FILE_BASE}$${first(QMAKE_EXT_CPP)}
xmlcodegen_c.output = $$XMLCODEGEN_DIR/${QMAKE_FILE_BASE}$${first(QMAKE_EXT_H)}
xmlcodegen_c.CONFIG += target_predeps
xmlcodegen_c.depends += $$PWD/qxmlcodegen.py

QMAKE_EXTRA_COMPILERS += xmlcodegen_c

xmlcodegen_s.name = qxmlcodegen.py cpp ${QMAKE_FILE_IN}
xmlcodegen_s.input = XMLCODEGEN_HEADERS
xmlcodegen_s.variable_out = GENERATED_SOURCES
xmlcodegen_s.commands = $$escape_expand(\\n) # force creation of rule
xmlcodegen_s.output = $$XMLCODEGEN_DIR/${QMAKE_FILE_BASE}$${first(QMAKE_EXT_CPP)}
xmlcodegen_s.CONFIG += target_predeps

QMAKE_EXTRA_COMPILERS += xmlcodegen_s
