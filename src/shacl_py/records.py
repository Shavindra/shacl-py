"""Offline schema validation and filesystem-only discovery."""

import glob
import json
import os
import re
from dataclasses import dataclass
from functools import cache
from pathlib import Path, PurePosixPath

import yaml
from jsonschema.validators import validator_for

SCHEMAS = Path(__file__).parent / "schemas"
IGNORED = {".git", ".datalad", ".venv", "venv", "__pycache__", ".pytest_cache"}
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


@cache
def record_validator():
    schema = json.loads((SCHEMAS / "paper.schema.json").read_text())
    return validator_for(schema)(schema)


def validate_file_patterns(rules: dict):
    validator = record_validator()
    for slot, value in rules.items():
        for error in validator.descend(value, validator.schema["properties"][slot]):
            raise ValueError(f"{slot}: {error.message}")


def read_metadata(path: Path) -> str:
    if path.is_symlink() or not path.is_file():
        raise ValueError("metadata must be a regular local file")
    if path.stat().st_size > 1_000_000:
        raise ValueError("metadata exceeds 1 MB")
    return path.read_text(encoding="utf-8")


def load_records(root: Path) -> tuple[list[Paper], list[str]]:
    root = root.resolve()
    validator = record_validator()
    records, errors, ids = [], [], set()
    for path in discover(root):
        try:
            data = yaml.safe_load(read_metadata(path))
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
    return records, errors


def _compile_patterns(patterns):
    return [
        re.compile(
            glob.translate(str(PurePosixPath(p)), recursive=True, seps="/"),
            re.IGNORECASE,
        )
        for p in patterns
    ]


def _paths_below(base: Path, *, skip_hidden_dirs: bool):
    if base.is_symlink() or not base.is_dir():
        return
    for directory, dirs, files in os.walk(base, followlinks=False):
        dirs[:] = sorted(
            d
            for d in dirs
            if d not in IGNORED
            and not (skip_hidden_dirs and d.startswith("."))
            and not Path(directory, d).is_symlink()
        )
        for name in sorted(files):
            yield Path(directory, name)


def _file_row(path, relative):
    return {
        "Filename": path.name,
        "Relative path": relative,
        "Availability": "Available" if path.is_file() else "Unavailable",
    }


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
    data_rows, dataset_rows = [], []
    for path in _paths_below(record.folder, skip_hidden_dirs=True):
        if path.name.casefold() in {".git", ".gitkeep", ".keep", ".ds_store"}:
            continue
        relative = path.relative_to(record.folder).as_posix()
        if any(rule.fullmatch(relative) for rule in dataset_rules):
            dataset_rows.append(_file_row(path, relative))
        elif any(rule.fullmatch(relative) for rule in data_rules):
            data_rows.append(_file_row(path, relative))
    return data_rows, dataset_rows
