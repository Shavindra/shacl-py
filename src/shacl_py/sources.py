"""Read local metadata and optional DataLad MetaLad records."""

import json
import re
import subprocess
import sys
import sysconfig
from pathlib import Path
from uuid import uuid4

from shacl_py.records import FILE_PATTERN_SLOTS


def apply_fields(data, record, allow_pid=False, *, graph_type="Dataset"):
    for node in record.get("@graph", []):
        if not isinstance(node, dict):
            continue
        for entity in node.get("@list", [node]):
            if isinstance(entity, dict) and entity.get("@type") == graph_type:
                apply_fields(data, entity)
    for slot in FILE_PATTERN_SLOTS:
        if slot in record:
            data[slot] = record[slot]
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


def initial_fields(folder, stored=None, *, graph_type="Dataset"):
    title = (
        folder.resolve().name.replace("_", " ").replace("-", " ").strip() or folder.name
    )
    data = {
        "pid": f"urn:uuid:{uuid4()}",
        "display_label": title,
        "review_status": "unreviewed",
        "local_folder": ".",
    }
    readme = folder / "README.md"
    if readme.is_file() and not readme.is_symlink():
        with readme.open("rb") as stream:
            lines = stream.read(65536).decode("utf-8", errors="replace").splitlines()
        for line in lines:
            if line.startswith("# ") and line[2:].strip():
                data["display_label"] = line[2:].strip()
                break
        for line in lines:
            if (
                line.strip()
                and line[0].isalnum()
                and not line.startswith(("http", "DOI:"))
            ):
                data["description"] = line.strip()
                break
        for line in lines:
            source = re.fullmatch(
                r"(?:DOI|Source):\s*(https?://\S+|10\.\d{4,9}/\S+)",
                line.strip(),
                re.IGNORECASE,
            )
            if source:
                url = source.group(1)
                data["source_url"] = (
                    "https://doi.org/" + url if url.startswith("10.") else url
                )
                break
    # Later sources take precedence when creating a project record.
    for name in ("metalad.json", "paper.json", "project.json"):
        path = folder / name
        if path.is_symlink() or not path.is_file():
            continue
        if path.stat().st_size > 1_000_000:
            raise ValueError(f"{path}: exceeds 1 MB")
        try:
            record = json.loads(path.read_text(encoding="utf-8"))
        except ValueError as error:
            raise ValueError(f"{path}: {error}") from error
        if name == "metalad.json" and isinstance(record, dict):
            record = record.get("extracted_metadata")
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


def stored_metadata(collection, *, single=False, graph_type="Dataset"):
    collection = collection.resolve()
    dataset = next(
        (
            p
            for p in (collection, *collection.parents)
            if (p / ".datalad/config").is_file()
        ),
        None,
    )
    if dataset is None:
        return {}
    result = subprocess.run(
        [
            str(Path(sysconfig.get_path("scripts")) / "datalad"),
            "-f",
            "tailored",
            "meta-dump",
            "-d",
            str(dataset),
            "-r",
        ],
        check=False,
        capture_output=True,
        text=True,
    )
    if result.returncode and "NoMetadataStoreFound" in result.stderr:
        print("No MetaLad store found. Using local project metadata.", file=sys.stderr)
        return {}
    if result.returncode:
        raise ValueError(f"MetaLad could not read {dataset}: {result.stderr.strip()}")
    by_folder = {}
    for line in result.stdout.splitlines():
        if not line.strip():
            continue
        record = json.loads(line)
        base = dataset / record.get("dataset_path", "")
        if record.get("type") == "file":
            source = base / record["path"]
            if source.name not in {
                "project.json",
                "paper.json",
                "README.md",
                "metadata.yaml",
            }:
                continue
            base = source.parent
        folder = base.resolve()
        payload = record.get("extracted_metadata")
        matches = folder == collection if single else folder.parent == collection
        if matches and isinstance(payload, dict):
            fields = by_folder.setdefault(folder, {})
            apply_fields(fields, payload, graph_type=graph_type)
    return by_folder
