"""Read the Methods attribute profile and the subjects declared on a record."""

import re
from collections import defaultdict
from dataclasses import dataclass, field

from shacl_py.attributes import (
    attribute_groups,
    is_link,
    is_method_group,
    label_of,
    predicate_of,
    short_iri,
)


def nodes(attributes):
    return [n for n in attributes or [] if isinstance(n, dict)]


def local_name(iri):
    return re.split(r"[/#:]", iri)[-1]


def file_attributes(entries):
    for entry in entries or []:
        extracted = entry.get("extracted_metadata")
        if isinstance(extracted, dict):
            yield from nodes(extracted.get("attributes"))


def annotations(node):
    notes = node.get("annotations") or {}
    if isinstance(notes, list):
        notes = {n.get("annotation_tag"): n for n in nodes(notes)}
    if not isinstance(notes, dict):
        return {}
    return {
        k: v.get("annotation_value") if isinstance(v, dict) else v
        for k, v in notes.items()
    }


def declared_file_records(owner):
    """Match catalogue hasPart statements to inline Things by their exact identifier."""
    related = owner.fields.get("relations") or {}
    records = {}
    for part in nodes(owner.fields.get("characterized_by")):
        ref = part.get("object")
        if local_name(predicate_of(part)) != "hasPart" or not isinstance(ref, str):
            continue
        thing = related.get(ref) or {}
        if isinstance(thing, dict):
            record = records.setdefault(
                ref,
                {**thing, "characterized_by": list(thing.get("characterized_by", []))},
            )
            record["characterized_by"].extend(part.get("characterized_by", []))
    return records


def local_file_id(owner, path):
    project = getattr(owner.source, "data", None)
    if not isinstance(project, dict):
        return None
    ns = annotations(project).get("identifier_namespace")
    if isinstance(ns, str) and path.is_relative_to(owner.source.folder):
        return f"{ns}:file:{path.relative_to(owner.source.folder).as_posix()}"
    return None


def techniques(attributes):
    for group in nodes(attributes):
        if is_method_group(group):
            for family in nodes(group.get("attributes")):
                for kind in nodes(family.get("attributes")):
                    for technique in nodes(kind.get("attributes")):
                        if (
                            isinstance(technique.get("defined_by"), str)
                            and isinstance(technique.get("value"), str)
                            and technique["defined_by"]
                            and technique["value"]
                        ):
                            yield family, kind, technique


@dataclass
class Facets:
    acquisition: set = field(default_factory=set)
    subjects: set = field(default_factory=set)

    def matches(self, technique, compartment):
        return (not technique or technique in self.acquisition) and (
            not compartment or compartment in self.subjects
        )


class MethodIndex:
    def __init__(self, collections, namespaces):
        self.labels = {}
        self.acquisition = {}
        self.compartments = {}
        self.aliases = {}
        for collection in collections:
            if collection.key != "compartments":
                continue
            for group in collection.groups:
                key = group.terms[0] if group.terms else group.entry
                refs = [
                    *group.terms,
                    *(
                        f"{ns}:{collection.key}:{member}"
                        for ns in namespaces
                        for member in group.members
                    ),
                ]
                for ref in refs:
                    self.aliases[ref] = (key, group.name)

    def facets(self, record):
        result = Facets()
        attrs = record.get("attributes", [])
        for _, kind, node in techniques(attrs):
            key = node["defined_by"]
            label = node.get("display_label")
            name = node["value"]
            if label and label.casefold() not in (
                "technique",
                "method",
                "imaging method",
                label_of(kind).casefold(),
            ):
                name = label
            name = node.get("title") or name
            self.labels.setdefault(key, name)
            if (
                local_name(predicate_of(kind)) == "image-acquisition"
                or label_of(kind) == "Image acquisition"
            ):
                self.acquisition[key] = self.labels[key]
                result.acquisition.add(key)

        def subject(ref, label=""):
            if not isinstance(ref, str) or not ref:
                return
            term = short_iri(ref)
            if term in self.aliases:
                term, label = self.aliases[term]
            elif not label and not re.fullmatch(r"GO:\d+", term):
                return
            result.subjects.add(term)
            if label or term not in self.compartments:
                self.compartments[term] = (
                    label[:1].upper() + label[1:] if label else term
                )

        def attribute_subjects(items):
            children = nodes(items)
            names = iter(
                n.get("value")
                for n in children
                if local_name(predicate_of(n)) == "structure"
            )
            for node in children:
                predicate = local_name(predicate_of(node))
                if predicate == "subject":
                    subject(node.get("value") or node.get("defined_by"))
                elif predicate == "structure-identifier":
                    subject(node.get("value"), next(names, "") or "")
                elif node.get("display_label") == "Compartment" and node.get(
                    "defined_by"
                ):
                    subject(node["defined_by"], node.get("value"))
                attribute_subjects(node.get("attributes"))

        for statement in nodes(record.get("characterized_by")):
            if local_name(predicate_of(statement)) == "subject":
                subject(statement.get("object"))
        attribute_subjects([node for node in nodes(attrs) if not is_method_group(node)])
        return result


def resources(value, resolve):
    if not value:
        return []
    entries = value if isinstance(value, list) else [value]
    result = []
    for entry in entries:
        label, ref = (
            (entry.get("label"), entry.get("ref"))
            if isinstance(entry, dict)
            else (entry, entry)
        )
        if isinstance(label, str) and label:
            result.append(
                {"label": label, "href": resolve(ref) if isinstance(ref, str) else None}
            )
    return result


def method_view(rows, labels, resolve):
    families = {}
    kinds = defaultdict(dict)
    for family, kind, node in rows:
        fk, tk = predicate_of(family), predicate_of(kind)
        group = families.setdefault(
            fk, {"label": label_of(family), "predicate": fk, "count": 0, "types": []}
        )
        if tk not in kinds[fk]:
            category = {"label": label_of(kind), "predicate": tk, "techniques": []}
            kinds[fk][tk] = category
            group["types"].append(category)
        props = annotations(node)
        key = node["defined_by"]
        summary = props.get("presentation") == "summary"
        kinds[fk][tk]["techniques"].append(
            {
                "name": node.get("title")
                or (node["value"] if summary else labels.get(key, node["value"])),
                "value": node["value"],
                "description": node.get("description"),
                "id": key,
                "href": key if is_link(key) else None,
                "summary": summary,
                "variant": props.get("variant"),
                "status": props.get("status"),
                "source": props.get("source")
                if is_link(props.get("source") or "")
                else None,
                "purpose": props.get("purpose"),
                "inputs": resources(props.get("inputs"), resolve),
                "outputs": resources(props.get("outputs"), resolve),
                "parameters": attribute_groups(node.get("attributes")),
            }
        )
        group["count"] += 1
    return list(families.values())
