# QXmlCodeGen
A simple python script to generate C++ bindings from an XML Schema definition, with support for bootstrapped Qt

## Features
- Generates a Qt-based XML parser and data structures from XSD-Files
- Only depends on QXmlStreamReader (which is part of QtCore)
- Can automatically integrate QXmlSchema to validate files before parsing

## Installation
The package is provided via qdep, as `Skycoder42/QXmlCodeGen`. To use it simply:

1. Install and enable qdep (See [qdep - Installing](https://github.com/Skycoder42/qdep#installation))
2. Add the following to your pro file:
```qmake
QDEP_DEPENDS += Skycoder42/QXmlCodeGen
!load(qdep):error("Failed to load qdep feature! Run 'qdep prfgen --qmake $$QMAKE_QMAKE' to create it.")
```

## Usage
Simply create an XSD file and add it to your project as:
```qmake
XML_SCHEMA_DEFINITIONS += myschema.xsd
```

This will generate `myschema.h` and `myschema.cpp` and automatically include them into your project. To use the generated parser to actually parse XML data, you can use it as follows:

```cpp
MySchema parser;
auto data = parser.readDocument("/path/to/data.xml");
```