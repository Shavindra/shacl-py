"""Command line entry points."""

import argparse
import os
import subprocess
import sys
from io import StringIO
from pathlib import Path
from tempfile import TemporaryDirectory

import yaml
from ruamel.yaml import YAML
from ruamel.yaml.error import YAMLError as RoundTripError

from shacl_py.records import (
    FILE_PATTERN_SLOTS,
    load_records,
    read_metadata,
    record_validator,
    validate_file_patterns,
)
from shacl_py.sources import initial_fields, source_url, stored_metadata


def generate_record(folder, stored=None, rules=None):
    from shacl_py.study import publication_info, read_study

    data = initial_fields(folder, stored)
    study = read_study(folder / ".studyminimeta.yaml")
    publication = publication_info(study, data.get("source_url"))
    label = (
        publication.get("title")
        or data.get("display_label")
        or study.get("study", {}).get("name")
        or study.get("dataset", {}).get("name")
    )
    data["display_label"] = label or data["pid"]
    if publication.get("doi"):
        data["source_url"] = source_url(publication["doi"])
    target = folder / "metadata.yaml"
    data.update(rules or {})
    try:
        validate_file_patterns(
            {slot: data[slot] for slot in FILE_PATTERN_SLOTS if slot in data}
        )
    except ValueError as error:
        raise ValueError(f"{target}: {error}") from error
    with target.open("x", encoding="utf-8") as stream:
        yaml.safe_dump(data, stream, sort_keys=False, allow_unicode=True)
    print(f"Created {target}")


def update_file_patterns(path, rules):
    """Change only explicitly supplied slots, preserving hand-edited YAML."""
    original = read_metadata(path)
    before = yaml.safe_load(original)
    if not isinstance(before, dict):
        raise TypeError("expected a project metadata mapping")
    if "catalogue" in before:
        raise ValueError("use shacl-py setup to change linked catalogue file groups")
    expected = before | rules
    if expected == before:
        return False
    problem = next(record_validator().iter_errors(expected), None)
    if problem:
        raise ValueError(problem.message)

    editor = YAML(typ="rt")
    editor.preserve_quotes = True
    document = editor.load(original)
    document.update(rules)
    output = StringIO()
    editor.dump(document, output)
    updated = output.getvalue()
    if yaml.safe_load(updated) != expected:
        raise ValueError("YAML round trip changed other metadata")
    with TemporaryDirectory(dir=path.parent, prefix=".shacl-py-") as staging:
        temporary = Path(staging, "pending.yaml")
        temporary.write_text(updated, encoding="utf-8")
        temporary.chmod(path.stat().st_mode)
        if read_metadata(path) != original:
            raise ValueError("metadata changed during generation; retry")
        temporary.replace(path)
    return True


def main(argv=None, *, review_layout=None):
    parser = argparse.ArgumentParser(prog="shacl-py")
    commands = parser.add_subparsers(dest="command", required=True)
    init = commands.add_parser(
        "init", help="Create project metadata without overwriting"
    )
    init.add_argument("path", type=Path)
    generate = commands.add_parser(
        "generate", help="Generate project records or update their file-selection rules"
    )
    generate.add_argument(
        "path", type=Path, help="Folder containing one directory per project"
    )
    generate.add_argument(
        "--single", action="store_true", help="Use PATH as a single project"
    )
    for command in (generate, init):
        command.add_argument(
            "--data-glob",
            action="append",
            dest="data_file_patterns",
            metavar="PATTERN",
            help="Project-relative glob for Data files (repeatable)",
        )
        command.add_argument(
            "--dataset-glob",
            action="append",
            dest="dataset_file_patterns",
            metavar="PATTERN",
            help="Project-relative glob for Dataset files (repeatable)",
        )
    setup = commands.add_parser(
        "setup", help="Set up and validate linked project metadata"
    )
    setup.add_argument("path", nargs="?", type=Path, default=Path("."))
    setup.add_argument(
        "--template", choices=("project", "paper-review"), default="project"
    )
    setup.add_argument("--title", help="Project title")
    setup.add_argument("--description", help="Project description")
    setup.add_argument(
        "--data-folder",
        action="append",
        metavar="DIR",
        help="Select a project data folder, including all file types (repeatable)",
    )
    setup.add_argument(
        "--papers-folder",
        metavar="DIR",
        help="Import the immediate paper directories in this project-relative folder",
    )
    setup.add_argument(
        "--no-input", action="store_true", help="Use available metadata without prompts"
    )
    add = commands.add_parser(
        "add-datasets",
        help="Link local datasets to a catalogued paper",
        description="Link one or more local datasets to an existing paper in the project catalogue.",
        epilog='Example: shacl-py add-datasets --paper papers/survey --dataset "Station readings" papers/survey/data/raw',
    )
    add.add_argument(
        "--project",
        type=Path,
        default=Path("."),
        help="Project root (default: current directory)",
    )
    add.add_argument(
        "--paper",
        required=True,
        help="Paper folder relative to project, PID, title or DOI",
    )
    add.add_argument(
        "--dataset",
        nargs=2,
        action="append",
        required=True,
        metavar=("NAME", "PATH_OR_URL"),
        help="Dataset name and project-relative file, directory or external HTTP(S) URL (repeatable)",
    )
    add.add_argument(
        "--linked-file",
        nargs=3,
        action="append",
        default=[],
        metavar=("DATASET_URL", "FILENAME", "FILE_URL"),
        help="List a remote file on the named dataset (repeatable)",
    )
    validate = commands.add_parser(
        "validate", help="Validate all metadata beneath a root"
    )
    validate.add_argument("path", type=Path, help="Project directory or metadata file")
    serve = commands.add_parser("serve", help="Start the read-only local viewer")
    serve.add_argument("path", type=Path, help="Project directory or metadata file")
    serve.add_argument("--port", type=int, default=8501)
    for command in (serve, validate):
        command.add_argument(
            "--metalad",
            action="store_true",
            help="Read the existing MetaLad store directly",
        )
    args = parser.parse_args(argv)
    try:
        if args.command == "add-datasets":
            from shacl_py.paper_review import add_datasets

            add_datasets(
                args.project.resolve(), args.paper, args.dataset, args.linked_file
            )
            return 0
        if args.command == "setup":
            from shacl_py.setup import setup_project

            setup_project(args, review_layout)
            return 0
        if args.command in {"init", "generate"}:
            rules = {
                slot: getattr(args, slot)
                for slot in FILE_PATTERN_SLOTS
                if getattr(args, slot) is not None
            }
            validate_file_patterns(rules)
        if args.command == "init":
            args.path.mkdir(parents=True, exist_ok=True)
            generate_record(
                args.path,
                stored_metadata(args.path, single=True).get(args.path.resolve()),
                rules,
            )
            return 0
        if args.command == "generate":
            if not args.path.is_dir():
                raise ValueError(f"{args.path}: not a directory")
            folders = (
                [args.path]
                if args.single
                else sorted(
                    folder
                    for folder in args.path.iterdir()
                    if not folder.name.startswith(".")
                    and not folder.is_symlink()
                    and folder.is_dir()
                )
            )
            stored = None
            for folder in folders:
                target = folder / "metadata.yaml"
                try:
                    if os.path.lexists(target):
                        changed = rules and update_file_patterns(target, rules)
                        print(
                            f"{'Updated file rules in' if changed else 'Kept'} {target}"
                        )
                        continue
                    if stored is None:
                        stored = stored_metadata(args.path, single=args.single)
                    generate_record(folder, stored.get(folder.resolve()), rules)
                except FileExistsError:
                    raise ValueError(
                        f"{target} appeared during generation; retry"
                    ) from None
                except (TypeError, ValueError, yaml.YAMLError, RoundTripError) as error:
                    raise ValueError(f"{target}: {error}") from error
            return 0
        root = args.path.absolute()
        records, errors = load_records(root, metalad=args.metalad)
        if errors and (args.command == "validate" or not records):
            print("\n".join(errors), file=sys.stderr)
            return 1
        if args.command == "validate":
            from shacl_py.catalogue import Catalogue
            from shacl_py.metadata_io import MetadataFile
            from shacl_py.study import dataset_root, validate_study

            sidecars = {
                dataset_root(r.folder) / ".studyminimeta.yaml"
                for r in records
                if isinstance(r, Catalogue)
            }
            for path in sorted(sidecars):
                if os.path.lexists(path):
                    validate_study(MetadataFile.read(path).data, path)
            print(f"Checked {len(records)} metadata record(s).")
            return 0
        if not 1 <= args.port <= 65535:
            parser.error("--port must be between 1 and 65535")
        env = os.environ.copy()
        env["SHACL_PY_ROOT"] = str(root)
        env["SHACL_PY_METALAD"] = "1" if args.metalad else "0"
        env["PYTHONDONTWRITEBYTECODE"] = "1"
        return subprocess.call(
            [
                sys.executable,
                "-m",
                "streamlit",
                "run",
                str(Path(__file__).with_name("app.py")),
                "--server.address=127.0.0.1",
                f"--server.port={args.port}",
                "--server.headless=true",
                "--client.toolbarMode=minimal",
                "--browser.gatherUsageStats=false",
                "--server.fileWatcherType=none",
                "--theme.base=light",
                "--theme.primaryColor=#000000",
                "--theme.backgroundColor=#FFFFFF",
                "--theme.secondaryBackgroundColor=#F0F0F0",
                "--theme.textColor=#000000",
            ],
            env=env,
            cwd=Path(__file__).parent,
        )
    except EOFError, KeyboardInterrupt:
        print("Cancelled.", file=sys.stderr)
        return 1
    except (OSError, TypeError, ValueError, yaml.YAMLError, RoundTripError) as error:
        print(str(error), file=sys.stderr)
        return 1
