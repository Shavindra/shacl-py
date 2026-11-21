"""A graph of the relationships declared between loaded metadata records."""

import json
import textwrap
from collections import defaultdict
from dataclasses import dataclass

from shacl_py.browser import (
    Item,
    dataset_roles,
    direct_references,
    doi_identifier,
    identifiers,
)
from shacl_py.catalogue import Catalogue
from shacl_py.navigation import url


def global_id(identifier):
    return identifier.startswith(("https://", "http://", "urn:", "doi:"))


def reference_id(value):
    doi = doi_identifier(value)
    return f"doi:{doi}" if doi else value


@dataclass
class RecordGraph:
    nodes: list[Item]
    edges: list[tuple[Item, str, Item]]
    focus: Item | None

    def with_relationship(self, predicate):
        edges = [edge for edge in self.edges if edge[1] == predicate]
        visible = {node for source, _, target in edges for node in (source, target)}
        return RecordGraph(
            [n for n in self.nodes if n in visible or n is self.focus],
            edges,
            self.focus,
        )

    def dot(self):
        """Use internal node names and quote metadata as literal DOT strings."""

        def quote(value):
            return json.dumps(value, ensure_ascii=False)

        names = {node: f"n{i}" for i, node in enumerate(self.nodes)}
        lines = [
            "digraph records {",
            'graph [rankdir=LR, bgcolor="transparent", pad=0.25, nodesep=0.32, ranksep=0.55]',
            (
                'node [shape=box, style="rounded,filled", fillcolor="white", '
                'color="#888888", fontname="Arial", fontsize=12, margin="0.14,0.10"]'
            ),
            (
                'edge [color="#777777", fontcolor="#454545", fontname="Arial", '
                "fontsize=10, arrowsize=0.7]"
            ),
        ]
        for node, name in names.items():
            title = str(node.label)
            wrapped = textwrap.wrap(title, width=34, max_lines=3, placeholder="…")
            label = "\n".join([node.kind, *wrapped])
            style = (
                ', fillcolor="#222222", fontcolor="white"' if node is self.focus else ""
            )
            lines.append(
                f"{name} [label={quote(label)}, tooltip={quote(title)}, "
                f'URL={quote(url(node.route))}, target="_self"{style}]'
            )
        for source, predicate, target in self.edges:
            lines.append(
                f"{names[source]} -> {names[target]} [label={quote(predicate)}]"
            )
        return "\n".join([*lines, "}"])


def record_graph(items, key_for, *, selected=None, query=""):
    """Resolve local identifiers in their source and combine links across aliases."""
    representatives = {}
    node_for = {}
    local = defaultdict(set)
    shared = defaultdict(set)
    inline = {}
    matches = set()
    query = query.strip().casefold()
    for item in items:
        key = key_for(item)
        ids = identifiers(item.fields)
        # Native records can repeat the same JSON-LD node inline or in @graph.
        if key is item and ids:
            identity = next(
                item.fields[k]
                for k in ("@id", "pid", "identifier")
                if isinstance(item.fields.get(k), str)
            )
            key = ("record", None if global_id(identity) else item.ref, identity)
        node = representatives.setdefault(key, item)
        node_for[item] = inline[id(item.fields)] = node
        if isinstance(key, tuple) and key[0] in ("dataset", "doi"):
            ids.add(
                key[1]
            )  # The same URL or DOI that groups these records in the browser.
        for identifier in map(reference_id, ids):
            local[item.ref, identifier].add(node)
            if global_id(identifier):
                shared[identifier].add(node)
        if query and any(
            query in str(value).casefold()
            for value in (
                item.label,
                item.kind,
                item.fields.get("doi", ""),
                *ids,
            )
        ):
            matches.add(node)

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

    edges = {}
    for item in items:
        node = node_for[item]
        links = list(direct_references(item.fields))
        if item.is_project:
            for slot in ("publications", "datasets"):
                links.extend(
                    ("Lists", row["pid"]) for row in item.source.graph.get(slot, [])
                )
        if isinstance(item.source, Catalogue) and item.is_publication:
            links.extend((role, target) for target, role in dataset_roles(item))
        for predicate, reference in links:
            if (target := resolve(item, reference)) is not None:
                label = "Derived from" if predicate == "source_datasets" else predicate
                edges[node, label, target] = None
        reverse = item.fields.get("@reverse")
        if isinstance(reverse, dict):
            for predicate, reference in direct_references(reverse):
                if (source := resolve(item, reference)) is not None:
                    edges[source, predicate, node] = None

    nodes = list(representatives.values())
    focus = node_for.get(selected)
    if focus or query:
        centres = {focus} if focus else matches
        visible = set(centres)
        selected_edges = []
        for source, predicate, target in edges:
            if source in centres or target in centres:
                visible.update((source, target))
                selected_edges.append((source, predicate, target))
        return RecordGraph([n for n in nodes if n in visible], selected_edges, focus)
    return RecordGraph(nodes, list(edges), None)
