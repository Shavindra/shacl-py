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

Set `highlighted: true` on an entry in `catalogue.publications` or
`catalogue.datasets` in `metadata.yaml` to star it. Starred records appear
first, including datasets listed under a paper. Choose **Starred** to see
only those entries. Type in the left-hand filter to narrow the list.

The **Methods** tab groups a record’s techniques by family and method type.
The **Technique** and **Compartment** filters apply together in Papers and
Datasets. A paper can match through a linked dataset. Each method can
include its purpose, inputs and outputs.
A technique with `annotations.presentation: summary` shows its name and
expandable parameters. Use `annotations.variant` for a short variant label.
A dataset PID or an unambiguous file reference opens the corresponding
record. Files show their own methods in the drawer and full-page view.
The [interactive wireframe](docs/wireframes/README.md) includes a worked example.

Open **Terms** to find papers and datasets by subject, property or keyword.
Each term has its own link. Select a subject and a property together to
find records that explicitly connect them. A broader property includes
its narrower properties.

Define each term once in `catalogue.project.term_vocabulary`. Its `role`
can be `subject` or `property`. Use `category` for a more specific display
label such as Compartment or Sampling site. A record's `index_terms` can
name a single term or link a property to a subject with an evidence note.

~~~yaml
catalogue:
  project:
    pid: urn:example:survey
    term_vocabulary:
      - {id: 'urn:example:station', label: Station, role: subject, category: Sampling site, aliases: [stations]}
      - {id: 'urn:example:reading', label: Reading, role: property}
      - {id: 'urn:example:mean', label: Mean reading, role: property, broader: 'urn:example:reading'}
  datasets:
    - pid: urn:example:means
      title: Mean reading per station
      index_terms:
        - {subject: 'urn:example:station', property: 'urn:example:mean', note: Mean of the readings at each station.}
~~~

Use `{term: 'urn:example:station'}` for a standalone term. Narrower terms
can inherit their role and category from a broader term. The viewer also
recognises direct Dublin Core subject statements for vocabulary terms
with the subject role. Existing assignments
using `subject` and `term` together remain readable. For general topics, use
a plain list such as `keywords: [Coastal monitoring]`. Use `or` to search
alternative properties for the same subject.

Datasets with files or folders open on **Files**. A dataset that holds only
attributes opens on **Attributes**, where each value appears with its unit
and any nested details, such as a measurement method or source.
In the left panel, expand **Attributes** under the selected paper or dataset
to read its measurements and sources. External datasets list the files
declared in `linked_files`. Select a filename to see its own attributes and
the groups inherited from its dataset, in the side panel or the full file
page. Preview and download open at the provider.

The dataset overview and file list show the modality and dimensions declared in
a top-level Dublin Core `http://purl.org/dc/terms/type` attribute labelled
**Data modality**. A catalogue may also use its own `data-modality` predicate.
Use `archive-contents` in the catalogue namespace on a ZIP or other archive to
list its member types in one comma-separated value. Put file attributes on a
linked file or on the local file's `hasPart` record.

Group related external files by giving their `name` a relative path, such as
`sample_01/image.ome.tif` and `sample_01/segmentation.ome.tif`. The viewer shows
one `sample_01/` folder and keeps each file's download URL, preview and attributes.
Use `/` between folders. Flat names still appear at the root. Absolute paths,
backslashes and empty, `.` or `..` path components remain literal root labels
for compatibility; they never access local folders. Local `file_groups` retain
their recursive file selection.

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

The [editable wireframes](docs/wireframes/) show the current viewer design and earlier layouts.

The viewer reads existing metadata files and MetaLad records together.
Use `shacl-py serve . --metalad` for the store alone, or
`shacl-py serve .studyminimeta.yaml` for one file. You can browse directly
after installation.

## Reference list and bibliography import

**Reference list** in the top bar shows the publications from your bibliography with their
authors, year, journal and number of linked datasets. Select a row to open
its details in a side panel. A paper with datasets links to its page in
**Papers**. The panel also links to a paper with a review folder. For a paper without datasets it shows the `add-datasets` command.

Papers can come from a reference manager. Export a collection as CSL-JSON or
BibTeX, for example with a Better BibTeX auto-export from Zotero, and import
it from the project root:

~~~sh
shacl-py import-bib research/references/library.json --into research/references/catalogue.yaml
~~~

- The importer matches papers by DOI. A citation key identifies a paper within the same export when its DOI is missing. Adding a DOI later preserves the paper’s catalogue ID.
- Only the title, authors, publication year and journal are written. Year
  and journal are top-level `datePublished` and `isPartOf` attributes.
  Keywords are filled in only when a paper has none.
- Curated fields, comments and dataset links are kept.
- A reference with no matching paper is added to the `--into` file, which
  must already be listed in `catalogue.includes`. Without `--into`, it goes
  to `metadata.yaml`.
- Each reference needs a title and either a DOI or a citation key. The command lists entries missing those fields.
- Each imported paper records its export in `bibliography`, shown only in
  Raw metadata. Running the import again with an unchanged export changes
  nothing.
- Use `--dry-run` to see the changes without saving them.

An imported paper with no datasets and no `local_folder` appears only in the
Reference list. Curated papers and papers with linked datasets appear in **Papers**.

## Optional metadata setup

Run `shacl-py setup` to create or edit a linked project catalogue. This helper
asks for project details, datasets and folders, then validates and saves
`metadata.yaml` and `.studyminimeta.yaml`.

To keep paper records in their own folders, list their YAML files under
`catalogue.includes` in the project’s `metadata.yaml`.

```yaml
catalogue:
  project:
    pid: urn:example:project
    title: Field survey
  includes:
  - papers/coastal-survey/catalogue.yaml
```

Each included file can hold `publications`, `datasets` and `reviews` lists.
Use project-relative paths for files and notebooks, and link records by PID
across files. Serve or validate the project root. Setup and dataset edits
write existing records back to the file that contains them.

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

A collection can also declare a `presentation` in its settings or template.
For example, this configuration lists each station once and opens a tab for
each survey record.

~~~yaml
presentation:
  starred: featured
  variants: {field: surveys, id_field: id, group_field: campaign_id, label_field: campaign_name, label: Campaign, plural: campaigns}
  overview: [description, depth, method]
  images: images
  references: references
  unassigned_references: unassigned_references
~~~

`terms` can link catalogue identifiers to an external vocabulary and show a
stored definition. Records with the same set of mapped terms share a sidebar
entry. `sections` can display additional fields or look up shared notes by ID.
When several records share a group such as a survey campaign, the viewer
numbers their tabs in catalogue order. Each tab links to its record ID.
**Raw metadata** shows the complete source record. [Presentation settings](src/shacl_py/schemas/collection-view.schema.json)

A template can show shared text above the record tabs with
`notes: {field: overviews, fields: [overview_composition, overview_structure, overview_shape]}`
under `presentation`. The viewer collects these fields from the concept's
overview entries and uses `field_labels` for their headings. **Notes** appears
when at least one field contains text.

### Bundled collection templates

shacl-py ships a **compartments** template for catalogues of cellular
compartments. Expand **Notes** beneath the GO definition to read the general
overview of composition, structure and shape. Choose an organism tab for its
description, references, images and measurements. Install the template by
name and point it at existing data.

~~~sh
shacl-py setup . --template compartments --data research/compartments/compartments.yaml
shacl-py validate .
~~~

Its source is in [src/shacl_py/collection_templates/compartments](src/shacl_py/collection_templates/compartments).
After editing the LinkML definition, regenerate the JSON Schema from that
directory. Optional fields accept `null`.

~~~sh
gen-json-schema --indent 2 compartments.linkml.yaml | sed '/^$/d' > compartments.schema.json
~~~

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
