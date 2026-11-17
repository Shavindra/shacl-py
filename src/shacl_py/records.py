"""Offline schema validation and filesystem-only discovery."""

import json
import os
from dataclasses import dataclass
from pathlib import Path

import yaml
from jsonschema import Draft7Validator

SCHEMAS = Path(__file__).parent / "schemas"
IGNORED = {".git", ".datalad", ".venv", "venv", "__pycache__", ".pytest_cache"}


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


def load_records(root: Path) -> tuple[list[Paper], list[str]]:
    root = root.resolve()
    validator = Draft7Validator(json.loads((SCHEMAS / "paper.schema.json").read_text()))
    records, errors, ids = [], [], set()
    for path in discover(root):
        try:
            if path.is_symlink():
                raise ValueError("metadata must be a regular local file")
            if path.stat().st_size > 1_000_000:
                raise ValueError("metadata exceeds 1 MB")
            data = yaml.safe_load(path.read_text())
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


def list_files(folder: Path, section: str) -> list[dict]:
    base = folder / section
    if base.is_symlink() or not base.is_dir():
        return []
    rows = []
    for directory, dirs, files in os.walk(base, followlinks=False):
        dirs[:] = sorted(
            d for d in dirs if d not in IGNORED and not Path(directory, d).is_symlink()
        )
        for name in sorted(files):
            path = Path(directory, name)
            rows.append(
                {
                    "Filename": name,
                    "Relative path": str(path.relative_to(folder)),
                    "Availability": "Available" if path.is_file() else "Unavailable",
                }
            )
    return rows
