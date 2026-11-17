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

`shacl-py serve ROOT` opens the local viewer. A linked project catalogue in
`metadata.yaml` takes precedence over adjacent descriptors. The viewer also discovers
`.studyminimeta.yaml`, `paper.json`, `project.json` and `metalad.json` in
folders without a catalogue entry. It consults the enclosing DataLad store
when the root contains no recognised metadata files.

Pass a particular file to view that source directly. To select the store even
when a catalogue exists, run `shacl-py serve ROOT --metalad`. The viewer reads
stored dataset records and records for recognised metadata files using
`meta-dump`. It shows the supplied fields and the original source metadata.
Use `--port` to change the port.

## Optional metadata setup

`shacl-py setup [PROJECT]` prepares both metadata files. You can override the
project title and description, specify repeated literal `--data-folder` paths
and pass `--no-input` for scripts. The same command can be rerun as a project
grows. Empty answers accept the displayed defaults.

- `metadata.yaml` holds the project's `catalogue`. Its Project, Publication and
  Dataset profiles inherit versioned Concepts types. Stable IDs connect records
  within the project. `reviews` holds project-specific status, notes and outputs.
  Each publication's `dataset_links` distinguishes `describes`, `reuses` and a
  general `related` link for imported data. A derived dataset can identify
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

## Earlier flat records

`init` and `generate` still work with the original one-record format. Linked
projects use `setup`. To adjust one flat record's two tabs, use:

~~~sh
shacl-py generate /path/to/project --single --data-glob 'measurements/**' --dataset-glob 'descriptors/**'
~~~

Each flag replaces just its own tab's list and may be repeated. The flat
defaults include tabular and image data under **Data files**, and metadata,
READMEs and licences under **Dataset**. The optional glob lists in
`metadata.yaml` are `data_file_patterns` and `dataset_file_patterns`.

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
