"""Shape Concepts attributes and annotations for display.

An attribute is a Concepts ``AttributeSpecification``: a ``predicate`` with an
optional literal ``value`` (with ``unit``, ``range``, ``defined_by``, ``about``
and ``description``) and optional nested ``attributes``.

Nested attributes play two roles. Under a valued attribute, a short plain
value (no unit, description or children of its own) qualifies that value,
such as its property identifier, quantity kind or evidence status. Any other
nested attribute is a property in its own right and gets its own row.

Top-level attributes without a value, or with sub-properties, become groups.
Remaining top-level values are collected in a leading "General" group.
"""

import re
from urllib.parse import urlsplit

INDENT = 14  # pixels per nesting level

QUDT_UNIT = "qudt.org/vocab/unit/"
UNIT_PREFIXES = {
    "Pico": "p",
    "Nano": "n",
    "Micro": "µ",
    "Milli": "m",
    "Centi": "c",
    "Deci": "d",
    "Kilo": "k",
    "Mega": "M",
    "Giga": "G",
}
UNIT_SYMBOLS = {
    "SEC": "s",
    "MIN": "min",
    "HR": "h",
    "DAY": "d",
    "M": "m",
    "L": "L",
    "GM": "g",
    "MOL": "mol",
    "HZ": "Hz",
    "K": "K",
    "DEG_C": "°C",
    "DEG": "°",
    "RAD": "rad",
    "REV": "rev",
    "PIXEL": "px",
    "PIXEL_COUNT": "px",
    "BYTE": "B",
    "PERCENT": "%",
    "J": "J",
    "W": "W",
    "V": "V",
    "A": "A",
    "N": "N",
    "PA": "Pa",
    "BAR": "bar",
}
DIMENSIONLESS = {"UNITLESS", "NUM", "ONE"}
SUPERSCRIPTS = str.maketrans("0123456789-", "⁰¹²³⁴⁵⁶⁷⁸⁹⁻")


def _text(value):
    if isinstance(value, dict):
        return str(value.get("pid") or value.get("@id") or "")
    if isinstance(value, list):
        return ", ".join(filter(None, map(_text, value)))
    return "" if value is None else str(value)


def is_link(value):
    try:
        parts = urlsplit(value)
    except ValueError:
        return False
    return parts.scheme in ("http", "https") and bool(parts.netloc)


def _tail(iri):
    return re.split(r"[/#]", iri.rstrip("/#"))[-1]


def short_iri(iri):
    """Abbreviate well-known term IRIs; leave other text unchanged."""
    if not is_link(iri):
        return iri
    if match := re.search(r"purl\.obolibrary\.org/obo/([A-Za-z]+)_(\w+)$", iri):
        return f"{match[1]}:{match[2]}"
    if "qudt.org/vocab/" in iri or "w3.org/2001/XMLSchema#" in iri:
        return _tail(iri)
    return iri


def _humanise(name):
    """Turn a camelCase or snake_case predicate name into a readable label."""
    words = re.sub(r"(?<=[a-z])(?=[A-Z])", " ", name).replace("_", " ")
    words = words.replace("-", " ").strip()
    words = re.sub(r"^has ", "", words, flags=re.IGNORECASE).split()
    # Lower-case ordinary words but keep acronyms such as ID.
    words = [w if w.isupper() else w.lower() for w in words]
    text = " ".join(words)
    return text[:1].upper() + text[1:] if text else "Attribute"


def predicate_of(node):
    return _text(node.get("predicate"))


def label_of(node):
    """Prefer the declared display label, else the predicate's last segment."""
    if label := node.get("display_label") or node.get("title"):
        return str(label)
    return _humanise(re.split(r"[:/#]", predicate_of(node).rstrip("/:#"))[-1])


def unit_symbol(unit):
    """Show a QUDT unit IRI as its symbol. Other unit text is kept as given."""
    unit = _text(unit)
    if QUDT_UNIT not in unit:
        return unit
    code = _tail(unit)
    if code in DIMENSIONLESS:
        return ""
    parts = re.split(r"[-_]PER[-_]", code)

    def symbol(part):
        match = re.fullmatch(r"(?P<base>.*?)(?P<power>-?\d+)?", part)
        base, power = match["base"], match["power"] or ""
        prefix = next((p for p in UNIT_PREFIXES if base.startswith(p)), "")
        base = base.removeprefix(prefix)
        if base not in UNIT_SYMBOLS:
            return part
        return (
            UNIT_PREFIXES.get(prefix, "")
            + UNIT_SYMBOLS[base]
            + (power.translate(SUPERSCRIPTS))
        )

    return "/".join(map(symbol, parts))


def _children(node):
    nested = node.get("attributes")
    return (
        [n for n in nested if isinstance(n, dict)] if isinstance(nested, list) else []
    )


def _has_value(node):
    return node.get("value") not in (None, "", [])


def _is_qualifier(node):
    return (
        _has_value(node)
        and not node.get("unit")
        and not node.get("description")
        and not _children(node)
    )


def _term(value, href=None):
    """One displayed value: its text and, for IRIs, where it links."""
    text = _text(value)
    target = href or text
    if match := re.fullmatch(r"https?://purl\.obolibrary\.org/obo/GO_(\d+)", target):
        term = "GO:" + match[1]
        return {
            "text": term if text == target else text,
            "href": "https://www.ebi.ac.uk/QuickGO/term/" + term,
        }
    if href:
        return {"text": text, "href": href}
    if is_link(text):
        return {"text": short_iri(text), "href": text}
    return {"text": text, "href": None}


def _qualifiers(node, children):
    quals = [
        {
            "label": label_of(q),
            "predicate": predicate_of(q),
            "terms": [_term(q["value"])],
        }
        for q in children
    ]
    about = node.get("about")
    about = about if isinstance(about, list) else [about] if about else []
    if about:
        quals.append(
            {"label": "About", "predicate": "", "terms": list(map(_term, about))}
        )
    return quals


def _property(node, pad, subprops=None):
    """A valued attribute with its unit, notes and qualifiers."""
    kids = _children(node)
    if subprops is None:
        subprops = [k for k in kids if not _is_qualifier(k)]
    quals = [k for k in kids if k not in subprops]
    defined_by = _text(node.get("defined_by"))
    unit_iri = _text(node.get("unit"))
    return {
        "kind": "property",
        "label": label_of(node),
        "predicate": predicate_of(node),
        "value": _term(node.get("value"), defined_by if is_link(defined_by) else None),
        "unit": unit_symbol(unit_iri),
        "unit_iri": unit_iri,
        "unit_href": unit_iri if is_link(unit_iri) else None,
        "description": _text(node.get("description")),
        "qualifiers": _qualifiers(node, quals),
        "pad": pad,
    }


def _rows(nodes, depth=0):
    for node in nodes:
        pad = depth * INDENT
        kids = _children(node)
        if _has_value(node):
            row = _property(node, pad)
            yield row
            subprops = [k for k in kids if not _is_qualifier(k)]
            yield from _rows(subprops, depth + 1)
        elif (
            len(kids) == 1
            and not kids[0].get("display_label")
            and _is_qualifier(kids[0])
        ):
            # A label naming a single unlabelled value, such as an identifier.
            row = _property({**kids[0], "display_label": label_of(node)}, pad)
            row["description"] = _text(node.get("description"))
            row["qualifiers"] += _qualifiers(node, [])
            yield row
        elif kids:
            yield {
                "kind": "heading",
                "label": label_of(node),
                "predicate": predicate_of(node),
                "description": _text(node.get("description")),
                "qualifiers": _qualifiers(node, []),
                "pad": pad,
            }
            yield from _rows(kids, depth + 1)


def _count(rows):
    return sum(row["kind"] == "property" for row in rows)


def is_method_group(node):
    # A group's name alone can also describe ordinary free-form attributes.
    if (
        re.split(r"[/#:]", predicate_of(node))[-1] != "methods"
        and node.get("display_label") != "Methods"
    ):
        return False
    return any(
        q.get("defined_by") and q.get("value")
        for family in _children(node)
        for kind in _children(family)
        for q in _children(kind)
    )


def attribute_groups(nodes, source="Dataset"):
    """Group attribute specifications under their top-level parents."""
    nodes = [n for n in nodes or [] if isinstance(n, dict) and not is_method_group(n)]
    general, groups = [], []
    for node in nodes:
        kids = _children(node)
        subprops = [k for k in kids if not _is_qualifier(k)]
        if _has_value(node) and not subprops:
            general.append(node)
            continue
        if not kids and not _has_value(node):
            continue
        lead = _property(node, 0, subprops) if _has_value(node) else None
        members = subprops if lead else kids
        rows = list(_rows(members))
        groups.append(
            {
                "label": label_of(node),
                "predicate": predicate_of(node),
                "lead": lead,
                "description": "" if lead else _text(node.get("description")),
                "qualifiers": [] if lead else _qualifiers(node, []),
                "rows": rows,
                "count": _count(rows) + bool(lead),
                "source": source,
            }
        )
    if general:
        rows = list(_rows(general))
        groups.insert(
            0,
            {
                "label": "General",
                "predicate": "",
                "lead": None,
                "description": "",
                "qualifiers": [],
                "rows": rows,
                "count": _count(rows),
                "source": source,
            },
        )
    return groups


def attribute_value(fields, *names):
    """Read a top-level attribute value by the last segment of its predicate."""
    for node in (fields or {}).get("attributes") or []:
        if (
            isinstance(node, dict)
            and _has_value(node)
            and _tail(predicate_of(node)) in names
        ):
            return _text(node["value"])
    return ""


def count_leaves(nodes):
    """Count the recorded values, not counting qualifiers of other values."""
    return sum(group["count"] for group in attribute_groups(nodes))


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
