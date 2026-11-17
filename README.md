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

Add this line to your own requirements.txt:

```text
shacl-py @ git+https://github.com/Shavindra/shacl-py.git
```

Then run `python -m pip install -r requirements.txt` in your active environment.
To update an existing installation:

```sh
python -m pip install --upgrade "git+https://github.com/Shavindra/shacl-py.git"
```

## Use

```sh
shacl-py init research/papers/my-paper
# Edit the generated metadata.yaml, including its placeholder source URL.
shacl-py validate research
shacl-py serve research --port 8501
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
Python 3.14+ viewer environment. Installing shacl-py installs only the viewer
and its Python dependencies, not DataLad or git-annex.

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

For contributors working from a source checkout, requirements.txt and
environment.yml remain available. The bundled examples are in that checkout.

Development from a checkout: `python -m pip install -e '.[dev]'`, then `ruff check .`,
`ruff format --check .`, `pytest`, and `python -m build`.
