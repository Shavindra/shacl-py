"""Navigation over authored Concepts records and native metadata sources."""

import json
import re
from collections import defaultdict
from dataclasses import dataclass

from shacl_py.catalogue import Catalogue
from shacl_py.files import (
    _file_row,
    folder_listing,
    grouped_files,
    in_git_tree,
    scoped_path,
)
from shacl_py.native import MetadataSource, declared_title
from shacl_py.records import Paper, project_files


def searchable(value):
    return json.dumps(value, ensure_ascii=False, default=str).casefold()


def identifiers(fields):
    return {
        value
        for key in ("pid", "@id", "identifier")
        if isinstance(value := fields.get(key), str)
    }


def references(fields):
    """Read identifier-valued relationships and nested JSON-LD node references."""
    found = set()
    relation_keys = {
        "about",
        "part_of",
        "hasPart",
        "isPartOf",
        "citation",
        "subjectOf",
        "isBasedOn",
        "dataset",
        "source_datasets",
        "object",
        "author",
        "contributor",
    }

    def visit(node):
        if isinstance(node, dict):
            for name, value in node.items():
                if name == "relations" and isinstance(value, dict):
                    found.update(value)
                if name in relation_keys:
                    for token in value if isinstance(value, list) else [value]:
                        if isinstance(token, str):
                            found.add(token)
                if isinstance(value, dict):
                    found.update(identifiers(value))
                visit(value)
        elif isinstance(node, list):
            for child in node:
                if isinstance(child, dict):
                    found.update(identifiers(child))
                visit(child)

    visit(fields)
    return found


@dataclass(eq=False)
class Item:
    source: Catalogue | Paper | MetadataSource
    ref: str
    key: str
    kind: str
    fields: dict

    @property
    def label(self):
        return (
            declared_title(self.fields)
            or self.fields.get("pid")
            or self.fields.get("@id")
            or self.fields.get("source_url")
            or self.ref
        )

    @property
    def route(self):
        return {"record": self.ref, "entry": self.key}

    @property
    def folder(self):
        if isinstance(self.source, (Paper, MetadataSource)):
            return self.source.folder
        return scoped_path(self.source.folder, self.fields.get("local_folder", "."))

    @property
    def has_folder(self):
        return (
            not isinstance(self.source, Catalogue)
            or self.is_project
            or "local_folder" in self.fields
        )

    def has_type(self, *names):
        return any(
            kind.rsplit("/", 1)[-1].rsplit("#", 1)[-1].rsplit(":", 1)[-1].casefold()
            in names
            for kind in self.kind.split(", ")
        )

    @property
    def is_dataset(self):
        return self.has_type("dataset", "localdataset")

    @property
    def is_publication(self):
        return self.has_type(
            "publication", "localpublication", "scholarlyarticle", "article"
        )

    @property
    def is_project(self):
        return isinstance(self.source, Catalogue) and self.fields is self.source.data


def source_content(source):
    if isinstance(source, Catalogue):
        return source.document
    if isinstance(source, Paper):
        return source.data
    return source.content


def items_from(records, root):
    for source in records:
        if isinstance(source, MetadataSource):
            for i, (kind, fields) in enumerate(source.entries):
                yield Item(source, source.reference, str(i), kind, fields)
            if not source.entries:
                yield Item(source, source.reference, "", "Metadata source", {})
            continue
        ref = source.metadata.relative_to(root).as_posix()
        if isinstance(source, Catalogue):
            yield Item(source, ref, source.data["pid"], "Project", source.data)
            for slot, kind in (
                ("publications", "Publication"),
                ("datasets", "Dataset"),
            ):
                for fields in source.graph.get(slot, []):
                    yield Item(source, ref, fields["pid"], kind, fields)
        else:
            yield Item(
                source,
                ref,
                source.data["pid"],
                source.data.get("schema_type") or "Record",
                source.data,
            )


def publication_key(item):
    """Use a declared DOI or global PID. Unidentified entries stay source-specific."""
    if item.is_publication:
        for field in ("doi", "source_url", "sameAs", "pid", "@id", "identifier"):
            value = item.fields.get(field)
            if isinstance(value, str) and (
                match := re.fullmatch(
                    r"(?:(?:https?://(?:dx\.)?doi\.org/|doi:\s*))?(10\.\d{4,9}/\S+)",
                    value.strip(),
                    re.IGNORECASE,
                )
            ):
                return ("doi", match[1].casefold())
        for field in ("pid", "@id", "identifier"):
            value = item.fields.get(field)
            if isinstance(value, str) and value.startswith(
                ("urn:", "https://", "http://")
            ):
                return ("pid", value)
    return item


def dataset_keys(papers, datasets):
    """Match StudyMiniMeta datasets to their unambiguous paper-review imports."""
    keys = {}
    imported = defaultdict(set)
    for paper in papers:
        if not isinstance(paper.source, Catalogue) or not paper.has_folder:
            continue
        links = dataset_links(paper)
        for dataset in datasets:
            if dataset.source is paper.source and dataset.key in links:
                imported[paper.folder, dataset.label].add(dataset)
    for dataset in datasets:
        location = dataset.fields.get("source_url") or dataset.fields.get("location")
        keys[dataset] = dataset
        if isinstance(location, str) and location.startswith(("https://", "http://")):
            keys[dataset] = ("dataset", location)
        else:
            for field in ("pid", "@id", "identifier"):
                value = dataset.fields.get(field)
                if isinstance(value, str) and value.startswith(
                    ("urn:", "https://", "http://")
                ):
                    keys[dataset] = ("dataset-id", value)
                    break
    for dataset in datasets:
        if dataset.ref.rsplit("/", 1)[-1] != ".studyminimeta.yaml":
            continue
        matches = imported[dataset.folder, dataset.label]
        if len(matches) == 1 and keys[dataset] is dataset:
            keys[dataset] = keys[next(iter(matches))]
    return keys


def dataset_links(item):
    links = {
        row["dataset"]: row["role"].capitalize()
        for row in item.fields.get("dataset_links", [])
    }
    for review in item.source.graph.get("reviews", []):
        if review["publication"] == item.key:
            for output in review.get("outputs", []):
                links.setdefault(output, "Output")
    return links


def neighbours(item, items):
    """Keep declared relationships distinct from records sharing a metadata location."""
    result = {}
    if isinstance(item.source, Catalogue):
        siblings = [
            other
            for other in items
            if other.source is item.source and other is not item
        ]
        links = dataset_links(item)
        for other in siblings:
            if item.is_project:
                result[other] = ""
            elif other.key in links:
                result[other] = links[other.key]
            elif other.key in item.fields.get("source_datasets", []):
                result[other] = "Derived from"
            elif item.key in other.fields.get("source_datasets", []):
                result[other] = "Derived dataset"
            elif other.kind == "Publication" and item.key in (
                incoming := dataset_links(other)
            ):
                result[other] = incoming[item.key]
    own_ids = identifiers(item.fields)
    own_values = references(item.fields)
    for other in items:
        if (
            other is item
            or other in result
            or (other.source is item.source and isinstance(item.source, Catalogue))
        ):
            continue
        ids = identifiers(other.fields)
        if ids & own_ids:
            result[other] = "Same identifier"
        elif ids & own_values or (
            own_ids and own_ids.intersection(references(other.fields))
        ):
            result[other] = "Linked in metadata"
        elif other.source is item.source:
            result[other] = "In this metadata source"
        elif item.has_folder and other.has_folder and other.folder == item.folder:
            result[other] = "In this folder"
    return result


def file_metadata(records):
    result = defaultdict(list)
    for record in records:
        if isinstance(record, MetadataSource):
            for path, rows in record.file_records.items():
                result[record.folder / path].extend(rows)
    return result


def file_selection(item, directory, *, folder_mode=False):
    """Return the selected groups or one level of a local folder."""
    source = item.source
    if isinstance(source, Catalogue) and item.fields.get("file_groups"):
        groups = grouped_files(source.folder, item.fields)
        if item.is_dataset:
            docs = {
                r["Relative path"]
                for g, rows in groups
                if g.get("section") == "documentation"
                for r in rows
            }
            groups = [
                (
                    g,
                    rows
                    if g.get("section") == "documentation"
                    else [r for r in rows if r["Relative path"] not in docs],
                )
                for g, rows in groups
            ]
        return [], [(g["label"], rows) for g, rows in groups]
    if isinstance(source, Paper) and any(
        k in item.fields for k in ("data_file_patterns", "dataset_file_patterns")
    ):
        data, docs = project_files(source)
        return [], [("Data files", data), ("Documentation and metadata", docs)]
    if not item.has_folder:
        return [], []
    base = item.folder
    if isinstance(source, MetadataSource) and source.file_records and not folder_mode:
        check_pointers = in_git_tree(base)
        rows = [
            _file_row(base / name, name, check_pointers)
            for name in sorted(source.file_records)
        ]
        return [], [("Recorded files", rows)]
    if not base.is_dir():
        return [], []
    folders, rows = folder_listing(base, directory)
    return folders, [
        ("Source folder" if isinstance(source, MetadataSource) else "Folder", rows)
    ]
