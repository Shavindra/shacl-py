# Implementation plan

1. Inspect the repository and its instructions. Require Python >=3.14 in
   pyproject.toml and use 3.14 for development and CI. Verify dependency
   installation before building the UI. No older-version compatibility code.
2. Build a standalone, read-only Streamlit viewer on localhost. Show each paper
   directly as a project, including papers in ordinary folders under one Git or
   DataLad repository. No authentication, database, editor or separate API.
3. Package `shacl-py init PAPER_PATH`, `shacl-py validate ROOT_PATH`, and
   `shacl-py serve ROOT_PATH --port PORT`. Init must never overwrite metadata;
   validation must report file-specific errors; serve binds to 127.0.0.1.
4. Reuse versioned DataLad Concepts/LinkML components, preserving provenance and
   licences. Define a small Paper profile with stable ID, title, description,
   DOI/source URL, review status and folder relative to metadata.yaml. Discover
   records recursively, including research/papers. Ship a validated example.
5. Build a black-and-white homepage with projects, descriptions, review status
   and search. Project pages show source links and metadata. List notebooks/,
   data/raw/ and data/output/ separately with filenames, relative paths and
   availability. Do not load datasets, retrieve annex content or modify the
   research repository when serving.
6. Keep README short. Credit shacl-vue and the Psychoinformatics team and link
   DataLad Concepts. Describe this as a separate Python implementation. Include
   installation with pip/requirements.txt and Conda, all commands and an example.
   Define dependencies once in pyproject.toml; requirements.txt installs it.
7. CI runs on pushes and PRs using Python 3.14. Install dependencies; check Ruff
   lint/format; test discovery, validation, CLI and unavailable annex files;
   smoke-test the example homepage; build and install the wheel; verify help.
8. Run checks, then deliver one conventional implementation commit:
   `feat: add minimal Python 3.14+ metadata viewer and initial checks`.
   Report its link, checks and limitations. A DataLad extension and general
   shacl-vue feature parity remain outside scope.
