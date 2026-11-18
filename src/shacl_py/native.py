"""Read native metadata with its original fields and local file subjects."""

import json
from dataclasses import dataclass, field
from pathlib import Path

from shacl_py.files import read_metadata, scoped_path
from shacl_py.sources import stored_records
from shacl_py.study import read_study


def declared_title(fields):
    for key in ("title", "headline", "display_label", "name"):
        value = fields.get(key)
        if isinstance(value, str) and value.strip():
            return value
    return " ".join(
        name
        for key in ("given_name", "last_name")
        if isinstance(name := fields.get(key), str)
    )


def entities(value, kind):
    """Walk only the containers defined by MetaLad and JSON-LD."""
    if isinstance(value, list):
        for item in value:
            yield from entities(item, kind)
    elif isinstance(value, dict):
        if "extracted_metadata" in value:
            yield from entities(value["extracted_metadata"], kind)
        elif "@graph" in value:
            yield from entities(value["@graph"], kind)
        elif "@list" in value:
            yield from entities(value["@list"], kind)
        else:
            types = value.get("@type") or value.get("schema_type") or kind
            yield ", ".join(types) if isinstance(types, list) else str(types), value
            # Concepts serialises inline relations as a mapping keyed by PID.
            relations = value.get("relations")
            if isinstance(relations, dict):
                for pid, fields in relations.items():
                    if isinstance(fields, dict):
                        yield from entities({"pid": pid, **fields}, "Concepts record")
            # JSON-LD permits typed nodes inline as well as in a top-level graph.
            for key, children in value.items():
                if key.startswith("@") or key == "relations":
                    continue
                for child in children if isinstance(children, list) else [children]:
                    if isinstance(child, dict) and "@type" in child:
                        yield from entities(child, "Record")


@dataclass
class MetadataSource:
    reference: str
    folder: Path
    content: dict | list
    entries: list[tuple[str, dict]]
    file_records: dict[str, list[dict]] = field(default_factory=dict)


def metalad_sources(subjects, root, reference):
    """Group extractor results by dataset and keep file records under their paths."""
    groups = {}
    for owner, row in subjects:
        base = owner if owner.is_relative_to(root) else root
        if base not in groups:
            groups[base] = MetadataSource(reference(base), base, [], [])
        source = groups[base]
        source.content.append(row)
        if row.get("type") == "file":
            path = scoped_path(owner, row.get("path")).relative_to(base).as_posix()
            source.file_records.setdefault(path, []).append(row)
        else:
            source.entries.extend(entities(row, "Dataset"))
    return list(groups.values())


def read_sources(path, root):
    reference = path.relative_to(root).as_posix()
    if path.name == ".studyminimeta.yaml":
        data = read_study(path)
        entries = [
            (kind.capitalize(), data[kind])
            for kind in ("study", "dataset")
            if data.get(kind)
        ]
        entries.extend(("Publication", item) for item in data.get("publication", []))
        entries.extend(
            ("Person", {"identifier": key, **fields})
            for key, fields in data.get("person", {}).items()
            if isinstance(fields, dict)
        )
        return [MetadataSource(reference, path.parent, data, entries)]
    text = read_metadata(path)
    try:
        data = json.loads(text)
    except json.JSONDecodeError:
        if not text.strip() or (
            path.name != "metalad.json" and path.suffix != ".jsonl"
        ):
            raise
        data = [json.loads(line) for line in text.splitlines() if line.strip()]
    if not isinstance(data, (dict, list)) or (
        isinstance(data, list) and not all(isinstance(item, dict) for item in data)
    ):
        raise ValueError("expected a metadata object or list of objects")
    rows = data if isinstance(data, list) else [data]
    if rows and all(
        "extracted_metadata" in row and row.get("type") in ("file", "dataset")
        for row in rows
    ):

        def source_name(folder):
            return (
                reference
                if folder == path.parent
                else f"{reference} · {folder.relative_to(path.parent)}"
            )

        sources = metalad_sources(
            (
                (scoped_path(path.parent, row.get("dataset_path") or "."), row)
                for row in rows
            ),
            path.parent,
            source_name,
        )
        for source in sources:
            source.content = data
        return sources
    kind = {"paper.json": "Publication", "project.json": "Project"}.get(
        path.name, "Record"
    )
    return [MetadataSource(reference, path.parent, data, list(entities(data, kind)))]


def read_store(root: Path):
    return metalad_sources(
        stored_records(root),
        root,
        lambda folder: f"MetaLad · {folder.relative_to(root).as_posix()}",
    )
