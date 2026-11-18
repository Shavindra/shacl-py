# Linked project metadata and local viewer

1. Keep the standalone Python 3.14+ package installable into an active Python or
   Conda environment. Use Python 3.14 for development and CI.
2. Reuse the versioned DataLad Concepts Project, Publication and Dataset
   schemas. Link items by persistent ID and keep each review's status and notes
   within its project. Preserve support for earlier flat records.
3. Provide an interactive setup command that can also use flags without prompts.
   Generate and validate the project catalogue and the enclosing dataset's
   StudyMiniMeta before saving. Preserve curated fields, comments and stable IDs.
4. Ship the paper-review workflow as an optional template with a customisable
   example. Select or import ordinary paper folders. Link source datasets, and
   register a derived dataset only when requested. Record the source datasets
   and analysis notebook where supplied.
5. List selected folders recursively without file-type rules. The example
   groups review notes, notebooks, raw data and analysis outputs per paper.
   Shared files belong to the project. Dataset pages have separate data and
   documentation sections. List paths and availability without retrieving data.
6. Keep the Streamlit viewer read-only and bound to localhost. Index metadata from
   files and MetaLad together. Let readers follow publications to datasets and
   files, inspect the original fields and see local availability.
7. Test the installed viewer with a metadata file, a MetaLad store and the
   example project. Check setup, validation, localhost serving and the display
   of unavailable files. Run Ruff and verify the installed CLI opens its help.
