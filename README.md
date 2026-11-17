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

## Set up a project and view it

From your research project directory, run:

~~~sh
shacl-py setup
shacl-py serve .
~~~

Setup prompts for project details, datasets and the files or folders to show.
It validates and saves the linked Concepts records in `metadata.yaml` and the
StudyMiniMeta description in `.studyminimeta.yaml`. Existing values supply the
defaults. The viewer opens at **http://127.0.0.1:8501**. Use `--port` to choose
another port.

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
