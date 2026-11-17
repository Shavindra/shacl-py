# shacl-py

Minimal Python UI / viewer for metadata described with the DataLad Concepts Toolkit.

Inspired by [shacl-vue](https://github.com/psychoinformatics-de/shacl-vue), developed by the Psychoinformatics team. Uses schemas from the [DataLad Concepts Toolkit](https://concepts.datalad.org/).
A separate Python implementation, requiring **Python 3.14 or later**.

## Prerequisites

- Python **3.14 or later** with pip, or Conda.
- Git for pip's GitHub installation.
- Internet access during installation.

For research data management, we recommend **DataLad with git-annex**. Both
are required for that workflow, but not for viewing ordinary folders.
No Node.js or database is required.

## Install

Use an **already active Conda or Python virtual environment** with Python 3.14+.
No repository checkout or new environment is required.

```sh
python --version
python -m pip install "git+https://github.com/Shavindra/shacl-py.git"
shacl-py --help
```

For Conda, activate your existing environment first if needed:

```sh
conda activate YOUR_EXISTING_ENVIRONMENT
python -m pip install "git+https://github.com/Shavindra/shacl-py.git"
```

Conda manages the environment; pip installs shacl-py. This project has not
published a Conda or PyPI release, so use the GitHub URL above.

### Mac setup script

With your environment already activated, download and run the script:

```sh
curl -fsSL https://raw.githubusercontent.com/Shavindra/shacl-py/main/setup.sh -o /tmp/shacl-py-setup.sh
bash /tmp/shacl-py-setup.sh
```

The script checks the active environment, Python 3.14+, pip and Git, then
installs or updates shacl-py there. It does not create or switch environments,
upgrade Python, or install system tools. It stops if the prerequisites are
missing. Package dependencies may be installed or updated in that environment.
On macOS, Git is available through Apple's Command Line Tools
(`xcode-select --install`) if you do not already have it.

### requirements.txt

Install the bundled requirements directly into the active environment:

```sh
python -m pip install -r https://raw.githubusercontent.com/Shavindra/shacl-py/main/requirements.txt
```

To update an existing installation:

```sh
python -m pip install --upgrade "git+https://github.com/Shavindra/shacl-py.git"
```

## Use

Choose the directory containing your projects. Each immediate visible directory
becomes one project, regardless of its name or internal layout.

```sh
shacl-py generate /path/to/collection
shacl-py validate /path/to/collection
shacl-py serve /path/to/collection
```

Open http://127.0.0.1:8501. For a single project at any location, run
`shacl-py init /path/to/project` and serve that directory. The viewer searches
for metadata.yaml recursively.

### Choose which files appear

**Data files** opens first. By default it shows spreadsheets, CSV/TSV tables
(including gzip), Parquet, Arrow, Feather, HDF5, NumPy and TIFF files anywhere in
the project. **Dataset** shows descriptive files such as README, metadata.yaml,
.studyminimeta.yaml, dataset_description.json and licences, plus the project
metadata. Existing records get these defaults as soon as you restart the viewer.

To show only spreadsheets from a particular folder, save a project-relative
pattern when generating metadata. Quote patterns so your shell passes them through.

```sh
shacl-py generate /path/to/collection --data-glob 'data/raw/**/*.xlsx'
```

For a single project with a different layout, you can set both tabs:

```sh
shacl-py generate /path/to/project --single \
  --data-glob 'measurements/**' \
  --dataset-glob 'README.md' --dataset-glob 'descriptors/**'
```

Each flag is repeatable and replaces the selection for its own tab. On existing
records, generation with flags updates only those fields. The same flags work
with `init` when creating one record. Run `serve` as usual.

The patterns are stored in `metadata.yaml` as `data_file_patterns` and
`dataset_file_patterns`. These optional fields belong to the viewer's LinkML
profile of the [Concepts Thing](https://concepts.datalad.org/s/things/v2/Thing/).
You can edit them or supply them in project.json or a MetaLad payload.
An omitted field uses its defaults. An empty list selects no files for that
tab. Paths start at `local_folder` and match case-insensitively. `*` matches
within one path component and `**` spans directories. Dataset takes priority
if both tabs match. Unmatched files, hidden directories and placeholders such
as .gitkeep stay out of the lists.

## Metadata and data management

In a DataLad dataset, generation queries the stored MetaLad metadata with
`datalad meta-dump -r`. It maps dataset records by project path and file
records by project descriptor (project.json, README.md or metadata.yaml).
The legacy paper.json descriptor is also supported. It reads flat title,
display_label, description, source_url, url and doi fields. Metadata extraction
into the MetaLad store is a separate operation.

For missing values, generation uses local project.json (or legacy paper.json),
a local metalad.json export, README.md and the folder name. Each new record
gets a persistent ID and an initial review status. You can edit metadata.yaml
and add supported Concepts fields. Generation without file-selection flags
preserves existing records. Ordinary folders work without a DataLad dataset.

Use DataLad and git-annex to manage research data, record changes and retrieve
file content. Keep metadata.yaml in Git. The viewer lists local availability
without fetching content. Unlocked annex pointers appear as available files.
The Concepts schema and its licence are bundled for offline validation.
See the [DataLad installation guide](https://handbook.datalad.org/en/latest/intro/installation.html)
for system prerequisites, including git-annex.

## DataLad extension status

This version is standalone. No extension registration is needed to view a
DataLad dataset, and `datalad shacl-py` is not implemented yet. Installing this
package does not add a DataLad command. See [extension integration](docs/local-setup.md#adding-a-datalad-extension)
for the implementation required to support that command.

For contributors working from a source checkout, requirements.txt and
environment.yml remain available. The bundled examples are in that checkout.

Development from a checkout: `python -m pip install -e '.[dev]'`, then `ruff check .`,
`ruff format --check .`, `pytest`, and `python -m build`.
