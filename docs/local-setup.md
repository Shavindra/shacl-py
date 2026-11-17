# Local setup and DataLad integration

Follow the pip or Conda steps in the [README](../README.md). Both install the
application from the local checkout. Python 3.14 or later is required.
The viewer can use a different environment from your existing DataLad installation.
Do not replace an existing research environment just to run this viewer.

## Adding a DataLad extension

**Future implementation, not an available installation option.**
The current package provides only the standalone `shacl-py` command.
A DataLad extension needs code and package registration; configuration alone
cannot turn the existing CLI into `datalad shacl-py`.

1. Add an optional DataLad dependency and verify it on Python 3.14, including
   the Git/git-annex prerequisites for the selected DataLad version.
2. Implement a DataLad `Interface` adapter for the existing init, validate and
   serve operations. Keep the standalone command available.
3. Export a command suite and register it in pyproject.toml under the
   `datalad.extensions` entry-point group. Map the adapter to the CLI name
   `shacl-py`, following the official extension template.
4. Test command discovery, help, arguments, validation errors, exit codes and
   the localhost server through DataLad on Python 3.14.
5. Once implemented, document installation into the same Python environment
   as DataLad. DataLad discovers installed extension entry points automatically;
   users do not need to edit a central extensions list.

The proposed `datalad shacl-py serve ROOT_PATH` spelling is a future interface.
For the current version, use `shacl-py serve ROOT_PATH`.

References:

- [DataLad extension documentation](https://docs.datalad.org/en/maint/customization.html)
- [DataLad extension template](https://github.com/datalad/datalad-extension-template)
