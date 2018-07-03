DISTFILES += \
	$$PWD/qxmlcodegen.py

isEmpty(XMLCODEGEN_DIR):XMLCODEGEN_DIR = .
isEmpty(MOC_DIR):MOC_DIR = .

debug_and_release {
	CONFIG(debug, debug|release):SUFFIX = /debug
	CONFIG(release, debug|release):SUFFIX = /release
}

XMLCODEGEN_DIR = $$XMLCODEGEN_DIR$$SUFFIX

xmlcodegen_c.name = qxmlcodegen.py ${QMAKE_FILE_IN}
xmlcodegen_c.input = XML_SCHEMA_DEFINITIONS
xmlcodegen_c.variable_out = XMLCODEGEN_HEADERS
win32: xmlcodegen_c.commands = python $$PWD/qxmlcodegen.py ${QMAKE_FILE_IN} ${QMAKE_FILE_OUT} $$XMLCODEGEN_DIR/${QMAKE_FILE_BASE}$${first(QMAKE_EXT_CPP)}
else: xmlcodegen_c.commands = $$PWD/qxmlcodegen.py ${QMAKE_FILE_IN} ${QMAKE_FILE_OUT} $$XMLCODEGEN_DIR/${QMAKE_FILE_BASE}$${first(QMAKE_EXT_CPP)}
xmlcodegen_c.output = $$XMLCODEGEN_DIR/${QMAKE_FILE_BASE}$${first(QMAKE_EXT_H)}
xmlcodegen_c.CONFIG += target_predeps
xmlcodegen_c.depends += $$PWD/qxmlcodegen.py

QMAKE_EXTRA_COMPILERS += xmlcodegen_c

xmlcodegen_m.name = qxmlcodegen.py moc ${QMAKE_FILE_IN}
xmlcodegen_m.input = XMLCODEGEN_HEADERS
xmlcodegen_m.variable_out = GENERATED_SOURCES
xmlcodegen_m.commands = ${QMAKE_FUNC_mocCmdBase} ${QMAKE_FILE_IN} -o ${QMAKE_FILE_OUT}
xmlcodegen_m.output = $$MOC_DIR/$${QMAKE_H_MOD_MOC}${QMAKE_FILE_BASE}$${first(QMAKE_EXT_CPP)}
xmlcodegen_m.CONFIG += target_predeps
xmlcodegen_m.depends += $$WIN_INCLUDETEMP $$moc_predefs.output
xmlcodegen_m.dependency_type = TYPE_C

QMAKE_EXTRA_COMPILERS += xmlcodegen_m

xmlcodegen_s.name = qxmlcodegen.py cpp ${QMAKE_FILE_IN}
xmlcodegen_s.input = XMLCODEGEN_HEADERS
xmlcodegen_s.variable_out = GENERATED_SOURCES
xmlcodegen_s.commands = $$escape_expand(\\n) # force creation of rule
xmlcodegen_s.output = $$XMLCODEGEN_DIR/${QMAKE_FILE_BASE}$${first(QMAKE_EXT_CPP)}
xmlcodegen_s.CONFIG += target_predeps

QMAKE_EXTRA_COMPILERS += xmlcodegen_s
