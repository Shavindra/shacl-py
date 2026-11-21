"""Shape Concepts attributes and annotations for display.

An attribute is a Concepts ``AttributeSpecification``: a ``predicate`` with
either a literal ``value`` (and optional ``unit``) or nested ``attributes``.
Top-level attributes with children become groups; loose top-level values are
collected in a leading "General" group.
"""

import re
from urllib.parse import urlsplit

INDENT = 14  # pixels per nesting level


def _text(value):
    if isinstance(value, dict):
        return str(value.get("pid") or value.get("@id") or "")
    return "" if value is None else str(value)


def predicate_of(node):
    return _text(node.get("predicate"))


def label_of(node):
    """Prefer the declared display label, else the predicate's last segment."""
    if label := node.get("display_label") or node.get("title"):
        return str(label)
    tail = re.split(r"[:/#]", predicate_of(node).rstrip("/:#"))[-1]
    return tail.replace("-", " ").replace("_", " ") or "Attribute"


def is_link(value):
    parts = urlsplit(value)
    return parts.scheme in ("http", "https") and bool(parts.netloc)


def _children(node):
    nested = node.get("attributes")
    return nested if isinstance(nested, list) and nested else None


def count_leaves(nodes):
    return sum(
        count_leaves(kids) if (kids := _children(n)) else 1
        for n in nodes
        if isinstance(n, dict)
    )


def _rows(nodes, depth=0):
    for node in nodes:
        if not isinstance(node, dict):
            continue
        pad = depth * INDENT
        if kids := _children(node):
            yield {"header": True, "label": label_of(node), "pad": pad}
            yield from _rows(kids, depth + 1)
        else:
            value = node.get("value")
            if isinstance(value, list):
                value = ", ".join(map(_text, value))
            value = _text(value)
            yield {
                "header": False,
                "label": label_of(node),
                "predicate": predicate_of(node),
                "value": value,
                "unit": _text(node.get("unit")),
                "link": is_link(value),
                "pad": pad,
            }


def attribute_groups(nodes, source="Dataset"):
    """Group attribute specifications by their top-level parent."""
    nodes = [n for n in nodes or [] if isinstance(n, dict)]
    loose = [n for n in nodes if not _children(n)]
    groups = [("General", "", loose)] if loose else []
    groups += [
        (label_of(n), predicate_of(n), _children(n)) for n in nodes if _children(n)
    ]
    return [
        {
            "label": label,
            "predicate": predicate,
            "count": count_leaves(members),
            "rows": list(_rows(members)),
            "source": source,
        }
        for label, predicate, members in groups
    ]


def _as_attributes(value, label=None):
    """Turn plain extracted metadata into attribute specifications."""
    if isinstance(value, dict):
        nested = [
            _as_attributes(v, str(k).removeprefix("@").replace("_", " "))
            for k, v in value.items()
        ]
        return {"display_label": label, "attributes": nested} if label else nested
    if isinstance(value, list) and any(isinstance(v, (dict, list)) for v in value):
        nested = [_as_attributes(v, f"{label} {i + 1}") for i, v in enumerate(value)]
        return {"display_label": label, "attributes": nested}
    if isinstance(value, list):
        value = ", ".join(map(_text, value))
    return {"display_label": label, "value": _text(value)}


def metadata_groups(entries):
    """Describe MetaLad file records as file-level attribute groups."""
    groups = []
    for entry in entries or []:
        extracted = entry.get("extracted_metadata")
        if isinstance(extracted, dict) and isinstance(
            extracted.get("attributes"), list
        ):
            groups += attribute_groups(extracted["attributes"], "File")
        elif extracted not in (None, {}, []):
            label = str(entry.get("extractor_name") or "File metadata")
            groups += attribute_groups([_as_attributes(extracted, label)], "File")
    return groups


def annotation_values(fields):
    """Read Concepts annotations given as a tag map or a list of tag/value pairs."""
    value = (fields or {}).get("annotations")
    if isinstance(value, dict):
        found = [
            v.get("annotation_value") if isinstance(v, dict) else v
            for v in value.values()
        ]
    elif isinstance(value, list):
        found = [v.get("annotation_value") for v in value if isinstance(v, dict)]
    else:
        found = []
    return [str(v).replace("_", " ") for v in found if v not in (None, "")]
