# Schema sources

The schemas come from the [DataLad Concepts Toolkit](https://github.com/psychoinformatics-de/datalad-concepts/tree/cb6c791aec4c5309775437df4bd58e94e1bfcc3c/src),
copyright DataLad Team and contributors. The upstream repository licence is
retained in CONCEPTS-LICENSE. The schemas also carry their own licence fields.

| Bundled file | Upstream path | Declared licence |
|---|---|---|
| things-v2.yaml | src/things/v2.yaml | MIT |
| things-properties-v1.yaml | src/things-properties/v1.yaml | MIT |
| things-social-v1.yaml | src/things-social/v1.yaml | CC BY 4.0 |
| things-publications-v1.yaml | src/things-publications/v1.yaml | CC BY 4.0 |
| things-data-v1.yaml | src/things-data/v1.yaml | CC BY 4.0 |

The v1 add-on files use local import paths so validation works offline. Their
classes, mappings and licence notices are retained. See the
[Creative Commons Attribution 4.0 licence](https://creativecommons.org/licenses/by/4.0/).

paper.yaml is the legacy Thing profile. catalogue.yaml imports the types above
and adds local slots for file selection, reviews and links. The wrapper key in
metadata.yaml is `catalogue`. The bundled JSON Schemas are generated with LinkML:

~~~sh
gen-json-schema src/shacl_py/schemas/paper.yaml > src/shacl_py/schemas/paper.schema.json
gen-json-schema --no-include-null --indent 2 src/shacl_py/schemas/catalogue.yaml | sed '/^$/d' > src/shacl_py/schemas/catalogue.schema.json
~~~
