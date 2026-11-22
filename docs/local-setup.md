# Local setup

## Install into the active environment

Use Python 3.14 or later, pip, Git and internet access for installation. In Conda,
activate your existing environment if needed and install there:

~~~sh
conda activate YOUR_EXISTING_ENVIRONMENT
python -m pip install --upgrade -r https://raw.githubusercontent.com/Shavindra/shacl-py/main/requirements.txt
~~~

In an active Python virtual environment the same pip command works. Conda manages
the environment and pip installs the package from GitHub. Alternatively install
the package directly with `python -m pip install --upgrade 'git+https://github.com/Shavindra/shacl-py.git'`.

On macOS, Git is available through the Apple Command Line Tools
(`xcode-select --install`). To check the active environment and install in one go:

~~~sh
curl -fsSL https://raw.githubusercontent.com/Shavindra/shacl-py/main/setup.sh -o /tmp/shacl-py-setup.sh
bash /tmp/shacl-py-setup.sh
~~~

## View the source metadata

`shacl-py serve ROOT` lists records from `metadata.yaml`, `.studyminimeta.yaml`,
`paper.json`, `project.json`, `metalad.json`, `metalad.jsonl` and the
enclosing DataLad metadata store. Adjacent sources retain their own fields.
A single record opens directly. Use **All metadata** to return to the index.

- **Metadata** shows the selected record, its related records and a link to
  the full source document, including extractor fields.
- **Datasets** lists declared links and identifies datasets described in
  the same source or folder. A linked project also lists its publications.
- **Files** shows the configured file groups or lets you browse the local
  folder one level at a time. A MetaLad source lists its recorded files,
  including unavailable ones. Select a file to see its metadata. For an
  available regular file, **Preview text** reads up to 8 KiB on request.

To select one source, pass a metadata file or use `shacl-py serve ROOT
--metalad` for the store alone. Use `--port` to change the port.

## Optional metadata setup

`shacl-py setup [PROJECT]` prepares both metadata files. You can override the
project title and description, specify repeated literal `--data-folder` paths
and pass `--no-input` for scripts. The same command can be rerun as a project
grows. Empty answers accept the displayed defaults.

- `metadata.yaml` holds the project's `catalogue`. Its Project, Publication and
  Dataset profiles inherit versioned Concepts types. Stable IDs connect records
  within the project. `reviews` holds project-specific status, notes and outputs.
  Each publication's `dataset_links` distinguishes `describes`, `reuses` and a
  general `related` link for imported data. An `output` link identifies a local
  analysis output associated with work on a publication. A derived dataset can identify
  `source_datasets` and a project-relative `notebook_path`.
- `file_groups` names literal files or whole directories. Paths are relative to
  the entity's `local_folder`, which is relative to the project metadata.
  Add any group label or choose the `documentation` section for dataset
  descriptors. The viewer skips hidden directories, caches and placeholder files.
- `.studyminimeta.yaml` describes the enclosing DataLad dataset. Setup writes it
  at that dataset's root, or at the project root for an ordinary folder. It
  preserves existing people, keywords and publications, and checks the result
  with MetaLad's StudyMiniMeta converter. A paper folder remains an ordinary
  directory. A record for a reviewed or derived dataset requires no Git submodule.
- Project details can come from StudyMiniMeta, MetaLad, `project.json` or
  explicit setup input. For a paper, the template reads a matching
  `publication[].title` in the paper folder's `.studyminimeta.yaml`, a declared
  publication record or the title you enter. A README is a documentation file.
  If the title is missing, a linked record can be displayed by source URL or ID.
- Existing flat metadata at the project root is retained alongside the new
  `catalogue` section. The paper-review helper can import a collection's
  immediate folders, reuse their flat IDs and read their local
  `.studyminimeta.yaml`. A paper's DOI and its dataset's source stay separate.
  Imported per-paper files remain in place. Subsequent setup keeps existing
  linked records as the editable source.

Keep the YAML in Git. Use DataLad and git-annex to save, transfer or retrieve
research data. The viewer lists annex symlinks without fetching their contents.
Availability refers to the working tree. The viewer recognises missing symlink
targets and small [git-annex pointer files](https://git-annex.branchable.com/internals/pointer_file/).
See the [DataLad installation guide](https://handbook.datalad.org/en/latest/intro/installation.html).

## Paper-review example

Run `shacl-py setup --template paper-review` in the project. Choose the paper
collection, add or select publications, and record review decisions. You can
link a dataset even when the files are only available online. Registering a
derived dataset is a separate, optional prompt. Select a file or directory,
then its source datasets and the notebook used. A dataset reused in a second
paper keeps its original ID.

The template suggests paths that exist, including a README for review notes,
`notebooks/`, `data/raw/` and `data/output/`. You can change the suggestions at
the prompts or adapt [the example helper](../examples/paper-review.py). Other
projects can use their own folder names and file group labels. Run
`shacl-py serve examples/coastal-survey` in a source checkout to browse the
complete worked example.

## Add datasets to an existing paper

Run from the project root, or set `--project DIR`. Supply the paper’s folder,
PID, title or DOI. Each `--dataset` takes a name and a project-relative path
to an existing file or folder. Repeat the option to link several datasets.

~~~sh
shacl-py add-datasets --paper papers/field-survey \
  --dataset "Station readings" papers/field-survey/data/raw \
  --dataset "Station means file" papers/field-survey/data/output/station-means.csv
~~~

The command updates the root catalogue in `metadata.yaml`. Running the same
command again reuses the dataset records and links. If any path is invalid,
the command exits before saving. Use `shacl-py serve .` to browse the result.

## Earlier flat records

`init` and `generate` can create a flat record. **Files** browses its local
folder. To select files by glob instead, set one or both lists explicitly:

~~~sh
shacl-py generate /path/to/project --single --data-glob 'measurements/**' --dataset-glob 'descriptors/**'
~~~

These flags set `data_file_patterns` and `dataset_file_patterns`. The viewer
shows the matches under **Data files** and **Documentation and metadata**.
Use `setup` to register a dataset and link it to other records.

## Adding a DataLad extension

The installed entry point is `shacl-py`. A future `datalad shacl-py` command
would need a DataLad Interface adapter, a command suite registered under
`datalad.extensions` in pyproject.toml and tests for discovery in the DataLad
environment. See the [DataLad extension template](https://github.com/datalad/datalad-extension-template).

## Development

~~~sh
python -m pip install -e '.[dev]'
ruff check .
ruff format --check .
pytest
python -m build
~~~

### Paper list author

In a publication in `.studyminimeta.yaml`, set the optional `primary_author`
to one of the person identifiers in its `author` list. For example, with
`author: [a, b]`, use `primary_author: b` to show the second person's name.
This is a shacl-py extension for the source YAML. MetaLad's standard
StudyMiniMeta extractor omits this field from its exported metadata.

In a flat paper record or a catalogue publication in `metadata.yaml`, use
the display name directly, for example `primary_author: Alex Smith`.
Without a primary author the left-hand paper list uses the full byline in source order.
Long bylines show an ellipsis. Open the paper to read its full byline.

### Viewer title and logo

Create `.shacl-py/config.yaml` in the folder passed to `shacl-py serve`.
When serving a single metadata file, use its parent folder.

```yaml
app_name: Cell sim
page_title: Cell sim catalogue
app_theme:
  logo: logo.svg
```

Place the image beside the config file, use a relative path such as
`assets/logo.png`, or supply an HTTP(S) image URL. Each setting is optional.
The header defaults to **shaclpy** and a solid white circle. The browser
tab uses `page_title`, falling back to `app_name`.
These keys follow the [shacl-vue configuration](https://shacl-vue.psychoinformatics.de/app-configuration.html).

### Link an external dataset

Use the archive landing page as the dataset location. Add a linked file for each
filename you want to show in the viewer. Both links open at the provider. The
viewer reads the catalogue offline and does not download the data.

```bash
shacl-py add-datasets --paper papers/survey \
  --dataset "Survey images" https://example.org/survey \
  --linked-file https://example.org/survey field-01.tif https://example.org/files/field-01.tif
```

Omit `--linked-file` for a dataset landing page alone. Repeat it for more files.

After the download URL, optionally supply a preview URL and a provider page URL.
The viewer shows each supplied link as a separate action. Opening a catalogue
entry never fetches the linked file.

Put shared scientific properties in the dataset's `attributes`. Put properties
of an individual file in that `linked_files` entry's `attributes`. Both accept
the Concepts `AttributeSpecification` fields, including nested attributes.
The file list also shows the size when the file declares a byte count with
`http://www.w3.org/ns/dcat#byteSize`.
This example records a shared compartment and the width of one image.

```yaml
# Within one catalogue.datasets entry
attributes:
  - predicate: http://purl.org/dc/terms/subject
    display_label: Compartment
    value: vacuole
    defined_by: http://purl.obolibrary.org/obo/GO_0005773
linked_files:
  - name: field-01.tif
    url: https://example.org/files/field-01.tif
    preview_url: https://example.org/preview/field-01
    attributes:
      - predicate: http://www.w3.org/2003/12/exif/ns#imageWidth
        display_label: Image width
        value: '1024'
        unit: http://qudt.org/vocab/unit/PIXEL_COUNT
```

In the file inspector, **File** identifies the image width and **Dataset**
identifies the compartment. The side panel and full file page show the
same groups. Files with only a URL and name also inherit the dataset groups.

### Show methods on a record

The Methods tab reads a Concepts attribute group named **Methods**. Its children
are method families, then method types, then techniques. Give each technique a
text `value` and a stable `defined_by` identifier. Use the same identifier on
each record that uses the technique. The Technique filter lists those under
**Image acquisition**.

This technique links its input images and output measurements.

```yaml
annotations:
  purpose: Measure the projected area of each outline.
  inputs:
    - label: Source images
      ref: urn:example:cell-images
  outputs:
    - label: Measurements
      ref: measurements.tsv
```

A label without a reference displays as text. Use a dataset PID or a unique
file path for a link. The viewer looks for files in the current dataset first,
then in other datasets linked to the paper.

Put a linked file’s Methods group in its own `attributes`. For a local file,
the catalogue can describe a `hasPart` target under the dataset’s `relations`.
Use the same file identifier in both places, in the form
`<identifier_namespace>:file:<project-relative path>`. The project supplies
`identifier_namespace` in its annotations. The file drawer and full page also
read Methods groups from stored MetaLad file attributes.
