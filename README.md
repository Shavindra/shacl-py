# shacl-py

Minimal Python UI / viewer for metadata described with the DataLad Concepts Toolkit.

Inspired by [shacl-vue](https://github.com/psychoinformatics-de/shacl-vue), developed by the Psychoinformatics team. Uses schemas from the [DataLad Concepts Toolkit](https://concepts.datalad.org/).
A separate Python implementation, requiring **Python 3.14 or later**.

## Prerequisites

- macOS/Linux terminal (or WSL on Windows), with Bash for setup.sh.
- Git to clone this repository.
- Python **3.14 or later**, including pip and venv, **or Conda**.
- Internet access for the initial dependency installation.

For research data management, we recommend **DataLad with git-annex**. Both
are required for the DataLad/annex workflow described below, but are not required
to run the viewer on ordinary folders. No Node.js or database is required.

## Install

First clone the application (keep it separate from your research dataset):

```sh
git clone https://github.com/Shavindra/shacl-py.git
cd shacl-py
```

Quick setup (checks Python, creates .venv, installs and verifies the example):

```sh
bash setup.sh
source .venv/bin/activate
shacl-py serve examples
```

Or run `bash setup.sh --conda`, then `conda activate shacl-py`.
The script does not install system prerequisites. The Conda route creates a new
`shacl-py` environment; if it already exists, activate it and run
`python -m pip install -r requirements.txt` instead.

Manual setup using pip with Python 3.14 or later:

```sh
python3.14 -m venv .venv
source .venv/bin/activate
python -m pip install -r requirements.txt
```

Or using Conda:

```sh
conda env create -f environment.yml
conda activate shacl-py
```

Check the installation and try the included example:

```sh
shacl-py --help
shacl-py validate examples
shacl-py serve examples
```

Open http://127.0.0.1:8501. Stop the server with Ctrl+C. In a new terminal,
reactivate the environment with `source /path/to/shacl-py/.venv/bin/activate`
or `conda activate shacl-py` before running the commands.

## Use

```sh
shacl-py init research/papers/my-paper
# Edit the generated metadata.yaml, including its placeholder source URL.
shacl-py validate research
shacl-py serve research --port 8501
# Working example
shacl-py serve examples
```

Open http://127.0.0.1:8501. Each paper appears directly on the homepage.
Metadata uses Concepts `pid`, `display_label` (title), and `description`, plus
`source_url` (DOI resolver or source URL), `review_status`, and `local_folder`.
The folder resolves relative to metadata.yaml and must stay within the served root.
See [example metadata](examples/research/papers/example/metadata.yaml).

The bundled LinkML Paper schema extends Concepts Things v2; generated JSON Schema
validates records offline. Upstream schema provenance and licence are retained in
[src/shacl_py/schemas](src/shacl_py/schemas). This is a local Paper profile, not a
general SHACL/RDF browser or a replacement for every shacl-vue feature.

Ordinary folders work; DataLad is optional. The viewer lists notebooks/, data/raw/
and data/output/ without reading dataset contents. Missing annex symlink targets
appear as unavailable; it never runs `datalad get`. Unlocked annex pointer files
are listed as locally available files without inspecting their contents.
Metadata creation and editing remain in files/CLI. Serving writes nothing to the
research repository. Symlink directories are not traversed.

## Recommended data management

Use **DataLad + git-annex** to manage research datasets, record changes and
retrieve file content. Use **shacl-py** to browse paper metadata and local file
availability. DataLad Concepts defines the metadata structure; it does not manage
your data. Neither Concepts nor this viewer replaces DataLad or git-annex.

Install Git, git-annex and DataLad using the
[official DataLad installation guide](https://handbook.datalad.org/en/latest/intro/installation.html).
Keep an existing working DataLad environment; it can be separate from the
Python 3.14+ viewer environment. `setup.sh` installs only the viewer and its
Python dependencies, not DataLad or git-annex.

From your data-management environment, check the prerequisites with:

```sh
git --version
git annex version
datalad --version
```

Continue using DataLad CLI commands for dataset creation, saving changes and
retrieving missing content. The viewer never downloads data automatically.
DataLad Catalog is not required for this viewer; existing Catalog metadata must
be converted to the supported metadata.yaml format before it can be displayed.

## Use with an existing DataLad dataset

Activate the shacl-py environment, then point it at your research repository:

```sh
cd /absolute/path/to/your/research-repository
shacl-py init research/papers/my-paper
# Edit research/papers/my-paper/metadata.yaml with the actual paper details.
shacl-py validate .
shacl-py serve .
```

Use `init` once for each paper. It refuses to overwrite existing metadata.
Create notebooks/, data/raw/ and data/output/ inside each paper folder as needed.
Papers can be ordinary folders; they do not need to be DataLad subdatasets.
For an existing compatible metadata.yaml, skip `init`.

Keep metadata.yaml in Git rather than annex storage. From the dataset root,
using your existing Git installation:

```sh
git -c annex.largefiles=nothing add research/papers/my-paper/metadata.yaml
git commit --only -m "docs: add paper metadata" -- research/papers/my-paper/metadata.yaml
```

This saves only the named metadata file. Continue managing datasets with your
existing DataLad installation; shacl-py does not require DataLad in its own environment.

## DataLad extension status

This version is standalone. No extension registration is needed to view a
DataLad dataset, and `datalad shacl-py` is not implemented yet. Installing this
package does not add a DataLad command. See [extension integration](docs/local-setup.md#adding-a-datalad-extension)
for the implementation required to support that command.

Development: `python -m pip install -e '.[dev]'`, then `ruff check .`,
`ruff format --check .`, `pytest`, and `python -m build`.
