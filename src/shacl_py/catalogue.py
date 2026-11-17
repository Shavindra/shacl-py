"""Linked Concepts records within a project, validated offline."""

import json
import re
from dataclasses import dataclass
from functools import cache
from graphlib import CycleError, TopologicalSorter
from pathlib import Path

from jsonschema.validators import validator_for

from shacl_py.files import local_path

SCHEMAS = Path(__file__).parent / "schemas"


@cache
def record_validator(name="paper"):
    schema = json.loads((SCHEMAS / f"{name}.schema.json").read_text(encoding="utf-8"))
    return validator_for(schema)(schema)


def title(entity):
    return entity.get("title") or entity.get("display_label") or entity["pid"]


@dataclass
class Catalogue:
    metadata: Path
    graph: dict

    @property
    def folder(self):
        return self.metadata.parent

    @property
    def data(self):
        return self.graph["project"]


def validate_structure(graph):
    problems = [
        f"{error.json_path}: {error.message}"
        for error in record_validator("catalogue").iter_errors(graph)
    ]
    if problems:
        raise ValueError("\n".join(problems))


def validate_catalogue(graph, root):
    validate_structure(graph)
    publications = graph.get("publications", [])
    datasets = graph.get("datasets", [])
    paper_ids = {paper["pid"] for paper in publications}
    dataset_ids = {dataset["pid"] for dataset in datasets}
    seen = set()
    for entity in [graph["project"], *publications, *datasets]:
        pid = entity["pid"]
        if not re.fullmatch(r"[A-Za-z][A-Za-z0-9+.-]*:\S+", pid):
            raise ValueError(f"pid: expected an identifier with a scheme, got {pid!r}")
        if pid in seen:
            raise ValueError(f"duplicate pid {pid}")
        seen.add(pid)
        if not (entity.get("title") or entity.get("display_label") or "").strip():
            raise ValueError(f"{pid}: supply a title or display_label")
        try:
            base = local_path(root, entity.get("local_folder", "."), directory=True)
            for group in entity.get("file_groups", []):
                for selection in group["paths"]:
                    local_path(base, selection)
            if "notebook_path" in entity:
                path = local_path(root, entity["notebook_path"])
                if path.is_dir():
                    raise ValueError("notebook_path must identify a file")
        except ValueError as error:
            raise ValueError(f"{pid}: {error}") from error
    for paper in publications:
        for link in paper.get("dataset_links", []):
            if link["dataset"] not in dataset_ids:
                raise ValueError(f"{paper['pid']}: unknown dataset {link['dataset']}")
    parents = {}
    for dataset in datasets:
        sources = dataset.get("source_datasets", [])
        for source in sources:
            if source not in dataset_ids:
                raise ValueError(f"{dataset['pid']}: unknown source dataset {source}")
        parents[dataset["pid"]] = sources
    try:
        TopologicalSorter(parents).prepare()
    except CycleError as error:
        raise ValueError(f"cyclic source_datasets: {error.args[1]}") from error
    reviewed = set()
    for review in graph.get("reviews", []):
        paper = review["publication"]
        if paper not in paper_ids or paper in reviewed:
            raise ValueError(f"unknown or duplicate review publication {paper}")
        reviewed.add(paper)
        for output in review.get("outputs", []):
            if output not in dataset_ids:
                raise ValueError(f"review {paper}: unknown output dataset {output}")
