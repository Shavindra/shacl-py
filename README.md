# shacl-py

Minimal Python UI / viewer for metadata described with the DataLad Concepts Toolkit.

Inspired by [shacl-vue](https://github.com/psychoinformatics-de/shacl-vue), developed by the Psychoinformatics team. Uses schemas from the [DataLad Concepts Toolkit](https://concepts.datalad.org/).
A separate Python implementation, requiring **Python 3.14 or later**.

## Install

From a checkout, using pip:

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

Development: `python -m pip install -e '.[dev]'`, then `ruff check .`,
`ruff format --check .`, `pytest`, and `python -m build`.
