"""Offline schema validation and filesystem-only discovery."""

import glob
import os
import re
from dataclasses import dataclass
from pathlib import Path, PurePosixPath

import yaml

from shacl_py.catalogue import SCHEMAS, Catalogue, record_validator, validate_catalogue
from shacl_py.files import IGNORED, _file_row, _paths_below, in_git_tree, read_metadata

__all__ = [
    "FILE_PATTERN_SLOTS",
    "SCHEMAS",
    "Paper",
    "discover",
    "list_files",
    "load_records",
    "project_files",
    "read_metadata",
    "record_validator",
    "validate_file_patterns",
]

DATA_PATTERNS = tuple(
    f"**/*.{suffix}"
    for suffix in (
        "csv",
        "csv.gz",
        "tsv",
        "tsv.gz",
        "xls",
        "xlsx",
        "xlsm",
        "ods",
        "parquet",
        "feather",
        "arrow",
        "h5",
        "hdf5",
        "npy",
        "npz",
        "tif",
        "tiff",
    )
)
DATASET_PATTERNS = (
    "**/README",
    "**/README.*",
    "**/LICENSE",
    "**/LICENSE.*",
    "**/CITATION.cff",
    "**/.studyminimeta.yaml",
    "**/dataset_description.json",
    "**/datapackage.json",
    "metadata.yaml",
    "project.json",
    "paper.json",
    "metalad.json",
)
FILE_PATTERN_SLOTS = ("data_file_patterns", "dataset_file_patterns")


@dataclass
class Paper:
    metadata: Path
    folder: Path
    data: dict


def discover(root: Path) -> list[Path]:
    if not root.is_dir():
        raise ValueError(f"{root}: not a directory")
    found = []
    for directory, dirs, files in os.walk(root, followlinks=False):
        dirs[:] = sorted(
            d for d in dirs if d not in IGNORED and not Path(directory, d).is_symlink()
        )
        if "metadata.yaml" in files:
            found.append(Path(directory, "metadata.yaml"))
    return sorted(found)


def validate_file_patterns(rules: dict):
    validator = record_validator()
    for slot, value in rules.items():
        for error in validator.descend(value, validator.schema["properties"][slot]):
            raise ValueError(f"{slot}: {error.message}")


def load_records(root: Path) -> tuple[list[Paper | Catalogue], list[str]]:
    root = root.resolve()
    validator = record_validator()
    records, errors, ids = [], [], set()
    for path in discover(root):
        try:
            data = yaml.safe_load(read_metadata(path))
            if isinstance(data, dict) and "catalogue" in data:
                graph = data["catalogue"]
                validate_catalogue(graph, path.parent)
                legacy = {
                    key: value for key, value in data.items() if key != "catalogue"
                }
                if legacy:
                    problem = next(validator.iter_errors(legacy), None)
                    if problem:
                        raise ValueError(f"legacy record: {problem.message}")
                pid = graph["project"]["pid"]
                if pid in ids:
                    raise ValueError(f"duplicate pid {pid}")
                ids.add(pid)
                records.append(Catalogue(path, graph))
                continue
            problems = list(validator.iter_errors(data))
            if problems:
                for error in problems:
                    field = ".".join(map(str, error.absolute_path)) or "record"
                    errors.append(f"{path}: {field}: {error.message}")
                continue
            folder_value = Path(data["local_folder"])
            if folder_value.is_absolute():
                raise ValueError("local_folder must be relative to metadata.yaml")
            folder = (path.parent / folder_value).resolve()
            if not folder.is_relative_to(root):
                raise ValueError("local_folder escapes the supplied root")
            if not folder.is_dir():
                raise ValueError("local_folder does not exist or is not a directory")
            if data["pid"] in ids:
                raise ValueError(f"duplicate pid {data['pid']}")
            ids.add(data["pid"])
            records.append(Paper(path, folder, data))
        except (OSError, ValueError, yaml.YAMLError) as error:
            errors.append(f"{path}: {error}")
    # Imported per-paper records stay on disk. Their linked entry is displayed once.
    imported = {
        (item["pid"], (record.folder / item["local_folder"]).resolve())
        for record in records
        if isinstance(record, Catalogue)
        for item in record.graph.get("publications", [])
        if "local_folder" in item
    }
    return [
        r
        for r in records
        if isinstance(r, Catalogue) or (r.data["pid"], r.folder) not in imported
    ], errors


def _compile_patterns(patterns):
    return [
        re.compile(
            glob.translate(str(PurePosixPath(p)), recursive=True, seps="/"),
            re.IGNORECASE,
        )
        for p in patterns
    ]


def list_files(folder: Path, section: str) -> list[dict]:
    """List a directory without applying the viewer's display rules."""
    return [
        _file_row(path, str(path.relative_to(folder)))
        for path in _paths_below(folder / section, skip_hidden_dirs=False)
    ]


def project_files(record: Paper) -> tuple[list[dict], list[dict]]:
    """Classify paths relative to local_folder, without opening file contents."""
    data = record.data.get("data_file_patterns")
    dataset = record.data.get("dataset_file_patterns")
    data_rules = _compile_patterns(DATA_PATTERNS if data is None else data)
    dataset_rules = _compile_patterns(DATASET_PATTERNS if dataset is None else dataset)
    check_pointers = in_git_tree(record.folder)
    data_rows, dataset_rows = [], []
    for path in _paths_below(record.folder, skip_hidden_dirs=True):
        if path.name.casefold() in {".git", ".gitkeep", ".keep", ".ds_store"}:
            continue
        relative = path.relative_to(record.folder).as_posix()
        if any(rule.fullmatch(relative) for rule in dataset_rules):
            dataset_rows.append(_file_row(path, relative, check_pointers))
        elif any(rule.fullmatch(relative) for rule in data_rules):
            data_rows.append(_file_row(path, relative, check_pointers))
    return data_rows, dataset_rows
