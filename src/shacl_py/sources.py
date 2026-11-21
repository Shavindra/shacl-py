"""Read local metadata and optional DataLad MetaLad records."""

import json
import re
from pathlib import Path
from uuid import uuid4

from shacl_py.files import FILE_PATTERN_SLOTS, read_metadata, scoped_path

METADATA_FILES = frozenset(
    {
        "metadata.yaml",
        ".studyminimeta.yaml",
        "metalad.json",
        "metalad.jsonl",
        "project.json",
        "paper.json",
    }
)


def source_url(value):
    if not value:
        return None
    value = value.strip()
    if re.fullmatch(r"10\.\d{4,9}/\S+", value, re.IGNORECASE):
        value = f"https://doi.org/{value}"
    if not re.fullmatch(r"https?://[^\s/]+(?:[/?#]\S*)?", value):
        raise ValueError(f"expected a DOI or HTTP(S) URL, got {value!r}")
    return value


def apply_fields(data, record, allow_pid=False, *, graph_type="Dataset"):
    types = record.get("@type")
    if types is not None and graph_type not in (
        types if isinstance(types, list) else [types]
    ):
        return
    candidates = [
        entity
        for node in record.get("@graph", [])
        if isinstance(node, dict)
        for entity in node.get("@list", [node])
        if isinstance(entity, dict) and entity.get("@type") == graph_type
    ]
    if "@graph" in record:
        if len(candidates) == 1:
            apply_fields(data, candidates[0], graph_type=graph_type)
        return
    for slot in FILE_PATTERN_SLOTS:
        if slot in record:
            data[slot] = record[slot]
    if isinstance(record.get("highlighted"), bool):
        data["highlighted"] = record["highlighted"]
    keys = {
        "display_label": ("display_label", "title", "name", "headline"),
        "description": ("description",),
        "source_url": ("source_url", "url", "doi", "sameAs"),
    }
    if allow_pid:
        keys["pid"] = ("pid",)
    for field, aliases in keys.items():
        for key in aliases:
            value = record.get(key)
            if not isinstance(value, str) or not value.strip():
                continue
            value = value.strip()
            if field == "source_url":
                if re.fullmatch(r"10\.\d{4,9}/\S+", value):
                    value = "https://doi.org/" + value
                if not re.match(r"https?://[^\s/]+", value):
                    continue
            if field == "pid" and not re.fullmatch(r"\S+:\S+", value):
                continue
            data[field] = value
            break


def initial_fields(
    folder,
    stored=None,
    *,
    graph_type="Dataset",
    descriptors=("paper.json", "project.json"),
):
    data = {"pid": f"urn:uuid:{uuid4()}", "local_folder": "."}
    # Later sources take precedence when creating a project record.
    for name in ("metalad.json", *descriptors):
        path = folder / name
        if path.is_symlink() or not path.is_file():
            continue
        try:
            record = json.loads(read_metadata(path))
        except ValueError as error:
            raise ValueError(f"{path}: {error}") from error
        if name == "metalad.json" and isinstance(record, dict):
            if (
                record.get("type") == "file"
                and Path(record.get("path", "")).name not in METADATA_FILES
            ):
                continue
            record = record.get("extracted_metadata", record)
        if not isinstance(record, dict):
            raise TypeError(f"{path}: expected a single project metadata object")
        apply_fields(
            data,
            record,
            allow_pid=name in {"project.json", "paper.json"},
            graph_type=graph_type,
        )
    apply_fields(data, stored or {})
    return data


def stored_records(root):
    """Yield dataset and file records with their owning dataset directory."""
    root = root.resolve()
    dataset = next(
        (p for p in (root, *root.parents) if (p / ".datalad/config").is_file()),
        None,
    )
    if dataset is None:
        return
    from datalad.api import meta_dump
    from datalad_metalad.exceptions import NoMetadataStoreFound

    try:
        results = meta_dump(
            dataset=str(dataset),
            recursive=True,
            return_type="generator",
            result_renderer="disabled",
        )
        for result in results:
            record = result["metadata"]
            folder = scoped_path(dataset, record.get("dataset_path") or ".")
            if folder.is_symlink():
                continue
            if record.get("type") == "file":
                subject = scoped_path(folder, record.get("path"))
            else:
                subject = folder
            if subject.is_relative_to(root):
                yield folder, record
    except NoMetadataStoreFound:
        return
    except RuntimeError as error:
        raise ValueError(f"MetaLad could not read {dataset}: {error}") from error


def stored_metadata(
    collection, *, single=False, graph_type="Dataset", descriptors=METADATA_FILES
):
    collection = collection.resolve()
    by_folder = {}
    for folder, record in stored_records(collection):
        if record.get("type") == "file":
            path = folder / record["path"]
            if path.name not in descriptors:
                continue
            folder = path.parent
        matches = folder == collection if single else folder.parent == collection
        payload = record.get("extracted_metadata")
        if matches and isinstance(payload, dict):
            apply_fields(
                by_folder.setdefault(folder, {}), payload, graph_type=graph_type
            )
    return by_folder
