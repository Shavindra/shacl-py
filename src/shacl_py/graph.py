"""Network of papers, datasets and labels declared by their metadata."""

import re
from collections import defaultdict
from dataclasses import dataclass

from shacl_py.browser import (
    dataset_roles,
    direct_references,
    doi_identifier,
    identifiers,
)
from shacl_py.catalogue import Catalogue
from shacl_py.navigation import url

KEYWORD_FIELDS = {
    "keyword",
    "keywords",
    "schema:keywords",
    "dcat:keyword",
    "http://schema.org/keywords",
    "https://schema.org/keywords",
    "http://www.w3.org/ns/dcat#keyword",
}
SUBJECT_FIELDS = {
    "dc:subject",
    "dcterms:subject",
    "http://purl.org/dc/terms/subject",
    "http://purl.org/dc/elements/1.1/subject",
}
LABEL_FIELDS = KEYWORD_FIELDS | SUBJECT_FIELDS | {"labels"}


def global_id(identifier):
    return identifier.startswith(("https://", "http://", "urn:", "doi:"))


def reference_id(value):
    doi = doi_identifier(value)
    return f"doi:{doi}" if doi else value


def label_values(value):
    if isinstance(value, str) and value.strip():
        yield value.strip()
    elif isinstance(value, list):
        for entry in value:
            yield from label_values(entry)
    elif isinstance(value, dict):
        for key in ("@value", "@list", "@set"):
            if key in value:
                yield from label_values(value[key])
                break


def metadata_labels(fields, predicates=LABEL_FIELDS):
    for name, value in fields.items():
        if name in predicates:
            yield from label_values(value)

    def attribute_labels(attributes):
        for attribute in attributes if isinstance(attributes, list) else ():
            if not isinstance(attribute, dict):
                continue
            predicate = attribute.get("predicate")
            if isinstance(predicate, str) and predicate in predicates:
                yield from label_values(attribute.get("value"))
            yield from attribute_labels(attribute.get("attributes"))

    yield from attribute_labels(fields.get("attributes"))


@dataclass(eq=False)
class GraphNode:
    kind: str
    label: str
    route: dict


@dataclass
class RecordGraph:
    nodes: list[GraphNode]
    edges: list[tuple[GraphNode, str, GraphNode]]
    focus: GraphNode | None

    def with_relationship(self, predicate):
        edges = [edge for edge in self.edges if edge[1] == predicate]
        visible = {node for source, _, target in edges for node in (source, target)}
        return RecordGraph(
            [n for n in self.nodes if n in visible or n is self.focus],
            edges,
            self.focus,
        )

    def network_data(self):
        routes = {node: url(node.route) for node in self.nodes}
        return {
            "nodes": [
                {
                    "id": routes[node],
                    "kind": node.kind,
                    "label": node.label,
                    "focused": node is self.focus,
                }
                for node in self.nodes
            ],
            "edges": [
                {
                    "source": routes[source],
                    "predicate": predicate,
                    "target": routes[target],
                }
                for source, predicate, target in self.edges
            ],
        }


def record_graph(items, key_for, *, selected=None, label=None, query=""):
    """Merge record aliases and resolve identifiers within their metadata source."""
    records = {}
    labels = {}
    node_for = {}
    local = defaultdict(set)
    shared = defaultdict(set)
    inline = {}
    matches = set()
    edges = {}
    query = query.strip().casefold()
    for item in items:
        if not (item.is_publication or item.is_dataset):
            continue
        kind = "Paper" if item.is_publication else "Dataset"
        key = key_for(item)
        ids = identifiers(item.fields)
        if key is item and ids:
            identity = next(
                item.fields[k]
                for k in ("@id", "pid", "identifier")
                if isinstance(item.fields.get(k), str)
            )
            key = ("record", None if global_id(identity) else item.ref, identity)
        node = records.setdefault(
            (kind, key), GraphNode(kind, str(item.label), item.route)
        )
        node_for[item] = inline[id(item.fields)] = node
        if isinstance(key, tuple) and key[0] in ("dataset", "doi"):
            ids.add(key[1])
        for identifier in map(reference_id, ids):
            local[item.ref, identifier].add(node)
            if global_id(identifier):
                shared[identifier].add(node)
        if query and any(
            query in str(value).casefold()
            for value in (item.label, kind, item.kind, item.fields.get("doi", ""), *ids)
        ):
            matches.add(node)
        for text in metadata_labels(item.fields):
            tag = labels.setdefault(
                text, GraphNode("Label", text, {"section": "graph", "label": text})
            )
            edges[node, "Labelled", tag] = None
            if query and (query in text.casefold() or query in "label"):
                matches.add(tag)

    def resolve(owner, reference):
        if isinstance(reference, dict):
            if (node := inline.get(id(reference))) is not None:
                return node
            ids = identifiers(reference)
        elif isinstance(reference, str):
            ids = {reference}
        else:
            return None
        candidates = set()
        for identifier in map(reference_id, ids):
            candidates.update(
                local.get((owner.ref, identifier)) or shared.get(identifier, ())
            )
        return next(iter(candidates)) if len(candidates) == 1 else None

    def linked_records(item, links):
        for predicate, reference in links:
            term = re.split(r"[/#:]", predicate)[-1].casefold()
            if (
                term in {"author", "creator", "contributor", "primary_author"}
                or predicate in LABEL_FIELDS
            ):
                continue
            if (target := resolve(item, reference)) is not None:
                yield (
                    "Derived from" if predicate == "source_datasets" else predicate,
                    target,
                )

    for item, node in node_for.items():
        links = list(direct_references(item.fields))
        if isinstance(item.source, Catalogue) and item.is_publication:
            links.extend((role, target) for target, role in dataset_roles(item))
        for predicate, target in linked_records(item, links):
            edges[node, predicate, target] = None
        reverse = item.fields.get("@reverse")
        if isinstance(reverse, dict):
            for predicate, source in linked_records(item, direct_references(reverse)):
                edges[source, predicate, node] = None

    nodes = [*records.values(), *labels.values()]
    focus = labels.get(label) if label is not None else node_for.get(selected)
    if selected is not None or label is not None or query:
        centres = {focus} if focus else matches
        visible = set(centres)
        selected_edges = []
        for source, predicate, target in edges:
            if source in centres or target in centres:
                visible.update((source, target))
                selected_edges.append((source, predicate, target))
        return RecordGraph([n for n in nodes if n in visible], selected_edges, focus)
    return RecordGraph(nodes, list(edges), None)
