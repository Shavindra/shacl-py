"""Present source metadata without converting it into an authored catalogue."""

import json
from dataclasses import dataclass
from pathlib import Path

from shacl_py.files import read_metadata
from shacl_py.sources import stored_records
from shacl_py.study import read_study


def declared_title(fields):
    for key in ("title", "headline", "display_label", "name"):
        value = fields.get(key)
        if isinstance(value, str) and value.strip():
            return value
    return ""


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
            yield str(value.get("@type") or value.get("schema_type") or kind), value


@dataclass
class MetadataSource:
    reference: str
    content: dict | list
    entries: list[tuple[str, dict]]

    @property
    def label(self):
        if len(self.entries) == 1:
            return declared_title(self.entries[0][1]) or "Title unavailable"
        return self.reference

    def matches(self, query):
        words = [self.reference]
        for kind, fields in self.entries:
            words.extend(
                (kind, declared_title(fields), str(fields.get("description", "")))
            )
        return query.strip().casefold() in " ".join(words).casefold()


def read_source(path, root):
    reference = path.relative_to(root).as_posix()
    if path.name == ".studyminimeta.yaml":
        data = read_study(path)
        entries = [
            (kind.capitalize(), data[kind])
            for kind in ("study", "dataset")
            if data.get(kind)
        ]
        entries.extend(("Publication", item) for item in data.get("publication", []))
        return MetadataSource(reference, data, entries)
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
    kind = {"paper.json": "Publication", "project.json": "Project"}.get(
        path.name, "Record"
    )
    return MetadataSource(reference, data, list(entities(data, kind)))


def read_store(root: Path):
    by_folder = {}
    for folder, row in stored_records(root):
        by_folder.setdefault(folder, []).append(row)
    return [
        MetadataSource(
            f"MetaLad · {folder.relative_to(root).as_posix()}",
            rows,
            list(entities(rows, "Record")),
        )
        for folder, rows in sorted(by_folder.items())
    ]
