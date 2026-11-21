# shacl-py

Minimal Python UI / viewer for metadata described with the DataLad Concepts Toolkit.
This standalone, read-only Streamlit app is a separate Python implementation
inspired by [shacl-vue](https://github.com/psychoinformatics-de/shacl-vue),
developed by the Psychoinformatics team. It uses versioned schemas from the
[DataLad Concepts Toolkit](https://concepts.datalad.org/).

## Install

Use pip and Git in an **already active Python 3.14+ environment**, including
Conda. This installs or updates the package directly from GitHub.

~~~sh
python --version
python -m pip install --upgrade -r https://raw.githubusercontent.com/Shavindra/shacl-py/main/requirements.txt
shacl-py --help
~~~

On macOS the optional installer checks the prerequisites and uses the active
environment. See [Mac and Conda setup](docs/local-setup.md).

## View existing metadata

From the project directory:

~~~sh
shacl-py serve .
~~~

Open **http://127.0.0.1:8501**. Choose a paper to see its linked datasets,
abstract, notes, other files and raw metadata. Choose **Datasets** in the
top bar to browse datasets across papers. Select a filename to inspect its
availability and any file metadata. **Records** lists other metadata types
when present.

Datasets with files or folders open on **Files**. A dataset that holds only
attributes opens on **Attributes**, where each value appears with its unit
and any nested details, such as a measurement method or source.
In the left panel, expand **Attributes** under the selected paper or dataset
to read its measurements and sources. External datasets list the files
declared in `linked_files`. Select a filename to see its own attributes and
the groups inherited from its dataset, in the side panel or the full file
page. Preview and download open at the provider.

Choose **Graph** to explore the network of papers, datasets and shared labels.
Labels come from declared labels, keywords and Dublin Core subjects. Click a
label to see which records share it, or click a paper or dataset to open it.
Drag the background to pan, drag a node to move it and scroll to zoom at the
pointer. **Fit** brings the whole network back into view. Search by title,
type or identifier, filter by relationship, or expand **List relationships**.
The viewer bundles D3.js 7.9.0 for the force layout and mouse controls.

Each view has a bookmarkable URL. Links, filters and searches update the open
viewer, and the browser's Back and Forward buttons restore previous views.
Refresh the page to read changes to the project's metadata.

The viewer reads existing metadata files and MetaLad records together.
Use `shacl-py serve . --metalad` for the store alone, or
`shacl-py serve .studyminimeta.yaml` for one file. You can browse directly
after installation.

## Optional metadata setup

Run `shacl-py setup` to create or edit a linked project catalogue. This helper
asks for project details, datasets and folders, then validates and saves
`metadata.yaml` and `.studyminimeta.yaml`.

### Example: reviewing papers and their data

~~~sh
shacl-py setup --template paper-review
shacl-py serve .
~~~

Choose an existing collection of paper folders or add papers by title, DOI or
URL. Each paper can have review notes, notebooks, raw data and analysis outputs.
Pick folders once to list their contents recursively, including extensionless
files. Several papers can link to the same dataset. Outputs stay under **Files**
unless you register one as a derived dataset and link its sources and notebook.

The example ships with the CLI. The [worked project](examples/coastal-survey)
and [customisable Python helper](examples/paper-review.py) show the metadata
and folder conventions. To import an existing collection without prompts, use
`shacl-py setup . --template paper-review --papers-folder research/papers --no-input`.

To link more datasets to an existing paper, run from the project root and repeat
`--dataset NAME PATH` for each local file or directory:

~~~sh
shacl-py add-datasets --paper papers/field-survey \
  --dataset "Station readings" papers/field-survey/data/raw \
  --dataset "Station means file" papers/field-survey/data/output/station-means.csv
~~~

For an external dataset, pass its HTTP(S) landing page in place of the path. Add individual file links with `--linked-file DATASET_URL FILENAME FILE_URL`. [External dataset example](docs/local-setup.md#link-an-external-dataset)

Repeating the command reuses the dataset.

### Project-selected collections

Register a YAML or JSON catalogue and its JSON Schema under `collections` in
`.shacl-py/config.yaml`. Each collection gets a named tab, a searchable list
and a detail page for each record. Record IDs keep bookmarks stable when the
list order changes. The same schema can serve several collections.

~~~yaml
collections:
  stations:
    title: Survey stations
    data: research/stations.yaml
    schema: schemas/stations.schema.json
    records: stations
    id_field: code
    label_field: name
    field_labels:
      code: Station ID
      depth_m: Depth (m)
~~~

Paths are relative to the project root. `records` names the top-level list
in the catalogue. Omit it when the whole file is a list. The ID and label
fields default to `id` and `name`. IDs may be strings or integers and must
be unique within a collection. Labels must be text. The viewer displays
nested fields and keeps catalogue-level fields under **Catalogue metadata**.
`shacl-py validate .` checks the whole document against the selected
schema and reports field paths for invalid values.

### Reuse a collection template

~~~sh
shacl-py setup . --template /path/to/stations-template --data research/stations.yaml
shacl-py validate .
shacl-py serve .
~~~

A station template contains this `template.yaml` manifest and the files it names.

~~~yaml
id: stations
title: Survey stations
schema: stations.schema.json
linkml: stations.linkml.yaml
example: example.yaml
records: stations
id_field: code
label_field: name
field_labels:
  code: Station ID
~~~

The template's paths are relative to the manifest. `linkml` is an optional
source file for schema authors. The viewer uses the supplied JSON Schema
offline. Bundle its references in that file, as in LinkML's
`gen-json-schema` output.

Setup uses existing catalogue data or copies the example when the file is
missing. Omitting `--data` creates `collections/<id>.<extension>` using the
example's extension. Setup copies an external template's declared files into
the project and registers a template already in the project in place.
The following configuration uses one template for two catalogues.

~~~yaml
collections:
  coastal:
    template: templates/stations/template.yaml
    data: research/coastal.yaml
  inland:
    template: templates/stations/template.yaml
    data: research/inland.yaml
    title: Inland stations
~~~

## Other commands

- `shacl-py validate ROOT` checks records again after you edit them.
- `shacl-py init DIR` creates one flat record, preserving existing metadata.
- `shacl-py generate ROOT` generates flat records for the immediate project
  folders. Existing flat records and their file-selection rules remain readable.

Use ordinary folders or use DataLad with git-annex for versioning and content
retrieval. Serving lists local availability and leaves research files untouched.
The CLI runs directly from the installed package. See [metadata, file selection and local setup](docs/local-setup.md)
and the [schema attribution](src/shacl_py/schemas/PROVENANCE.md).
