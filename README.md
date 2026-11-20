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

Record headers show the fields supplied by the metadata. A record can select and order its header fields with `display_fields: [pid, description, local_folder]`. An empty list hides the header fields. Raw metadata always contains the original record.

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

## Other commands

- `shacl-py validate ROOT` checks records again after you edit them.
- `shacl-py init DIR` creates one flat record, preserving existing metadata.
- `shacl-py generate ROOT` generates flat records for the immediate project
  folders. Existing flat records and their file-selection rules remain readable.

Use ordinary folders or use DataLad with git-annex for versioning and content
retrieval. Serving lists local availability and leaves research files untouched.
The CLI runs directly from the installed package. See [metadata, file selection and local setup](docs/local-setup.md)
and the [schema attribution](src/shacl_py/schemas/PROVENANCE.md).
