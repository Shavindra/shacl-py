"""Assemble a catalogue from an index and optional project-relative YAML files."""

from pathlib import Path

import yaml

from shacl_py.files import read_metadata, scoped_path

RECORD_LISTS = ("publications", "datasets", "reviews")


def read_part(path):
    return yaml.safe_load(read_metadata(path))


def catalogue_parts(index, path, read=read_part):
    """Return each declared file once. Paths in its records stay relative to the index."""
    includes = index.get("includes", [])
    if not isinstance(includes, list):
        raise TypeError(f"{path}: catalogue.includes must be a list of relative paths")
    parts = {}
    for name in includes:
        if not isinstance(name, str) or Path(name).suffix.lower() not in (
            ".yaml",
            ".yml",
        ):
            raise ValueError(
                f"{path}: expected a relative YAML file in catalogue.includes"
            )
        target = scoped_path(path.parent, name)
        if target == path or target in parts:
            raise ValueError(f"{path}: repeated or self-referencing include {name!r}")
        try:
            part = read(target)
            if (
                not isinstance(part, dict)
                or not part
                or part.keys() - set(RECORD_LISTS)
            ):
                raise ValueError("expected publications, datasets or reviews")
            for key, records in part.items():
                if not isinstance(records, list):
                    raise TypeError(f"{key} must be a list")
        except (TypeError, ValueError, OSError, yaml.YAMLError) as error:
            raise ValueError(f"{target}: {error}") from error
        parts[target] = part
    return parts


def merged_catalogue(index, parts):
    if "includes" not in index:
        return index
    graph = {key: value for key, value in index.items() if key != "includes"}
    for key in RECORD_LISTS:
        if key in index and not isinstance(index[key], list):
            raise ValueError(f"catalogue.{key} must be a list")
        if key in index or any(key in part for part in parts.values()):
            graph[key] = [
                row for part in (index, *parts.values()) for row in part.get(key, [])
            ]
    return graph
