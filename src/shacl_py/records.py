"""Offline schema validation and filesystem-only discovery."""

import glob
import os
import re
from dataclasses import dataclass
from pathlib import Path, PurePosixPath

import yaml

from shacl_py.catalogue import SCHEMAS, Catalogue, record_validator, validate_catalogue
from shacl_py.collection import CONFIG, Collection, load_collections
from shacl_py.files import (
    FILE_PATTERN_SLOTS,
    IGNORED,
    _file_row,
    _paths_below,
    in_git_tree,
    read_metadata,
)
from shacl_py.native import MetadataSource, entities, read_sources, read_store
from shacl_py.sources import METADATA_FILES

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


@dataclass
class Paper:
    metadata: Path
    folder: Path
    data: dict


def discover(root: Path, names=("metadata.yaml",)) -> list[Path]:
    if not root.is_dir():
        raise ValueError(f"{root}: not a directory")
    found = []
    for directory, dirs, files in os.walk(root, followlinks=False):
        dirs[:] = sorted(
            d
            for d in dirs
            if d not in IGNORED
            and d != ".shacl-py"
            and not Path(directory, d).is_symlink()
        )
        found.extend(Path(directory, name) for name in set(names).intersection(files))
    return sorted(found)


def validate_file_patterns(rules: dict):
    validator = record_validator()
    for slot, value in rules.items():
        for error in validator.descend(value, validator.schema["properties"][slot]):
            raise ValueError(f"{slot}: {error.message}")


def load_records(
    root: Path, *, metalad=False
) -> tuple[list[Paper | Catalogue | MetadataSource | Collection], list[str]]:
    single_file = root.is_file() or (root.is_symlink() and not root.is_dir())
    if single_file:
        if metalad:
            raise ValueError("--metalad requires a dataset directory")
        path = root.parent.resolve() / root.name
        project = next((p for p in path.parents if (p / CONFIG).is_file()), None)
        if project is not None:
            collections, errors, claimed = load_collections(project, only=path)
            if path in claimed:
                return collections, errors
        if path.name not in METADATA_FILES and path.suffix not in (".json", ".jsonl"):
            raise ValueError(f"{path}: expected a metadata file")
        paths, root = [path], path.parent
    else:
        root = root.resolve()
        if not root.is_dir():
            raise ValueError(f"{root}: not a directory")
        paths = [] if metalad else discover(root, METADATA_FILES)
    records, errors = [], []
    if not single_file:
        if not metalad:
            collections, errors, claimed = load_collections(root)
            records.extend(collections)
            paths = [path for path in paths if path not in claimed]
        try:
            records.extend(read_store(root))
        except (OSError, TypeError, ValueError, RuntimeError) as error:
            errors.append(f"{root}: could not read MetaLad metadata: {error}")
        if metalad and not records and not errors:
            errors.append(f"{root}: no stored MetaLad metadata found")
    validator = record_validator()
    for path in (p for p in paths if p.name == "metadata.yaml"):
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
                records.append(Catalogue(path, graph, data))
                continue
            if (
                isinstance(data, dict)
                and "pid" in data
                and not any(
                    slot in data
                    for slot in ("local_folder", "review_status", *FILE_PATTERN_SLOTS)
                )
            ):
                concepts = record_validator("catalogue")
                for kind in ("Thing", "Project", "Publication", "Dataset"):
                    if not list(concepts.descend(data, concepts.schema["$defs"][kind])):
                        break
                else:
                    raise ValueError("record does not match a bundled Concepts type")
                records.append(
                    MetadataSource(
                        path.relative_to(root).as_posix(),
                        path.parent,
                        data,
                        list(entities(data, "Concepts record")),
                    )
                )
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
            records.append(Paper(path, folder, data))
        except (OSError, ValueError, yaml.YAMLError) as error:
            errors.append(f"{path}: {error}")
    for path in paths:
        if path.name != "metadata.yaml":
            try:
                records.extend(read_sources(path, root))
            except (OSError, ValueError, TypeError, yaml.YAMLError) as error:
                errors.append(f"{path}: {error}")
    return records, errors


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
