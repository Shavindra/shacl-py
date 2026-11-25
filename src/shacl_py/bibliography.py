"""Import Zotero CSL JSON and BibTeX into a project catalogue."""

import datetime
import json
import re
from collections import defaultdict
from pathlib import Path
from uuid import NAMESPACE_URL, uuid5

from pybtex.database import parse_string
from pybtex.exceptions import PybtexError
from pybtex.richtext import Text

from shacl_py.catalogue import validate_catalogue
from shacl_py.files import scoped_path
from shacl_py.metadata_io import CatalogueEditor, MetadataFile, save_metadata
from shacl_py.prompts import new_entity
from shacl_py.sources import doi_identifier

YEAR = "https://schema.org/datePublished"
JOURNAL = "https://schema.org/isPartOf"
YEAR_NAMES = ("datePublished", "issued")
JOURNAL_NAMES = ("isPartOf",)


def _text(value):
    return " ".join(str(value or "").split())


def _csl_name(person):
    if not isinstance(person, dict):
        raise TypeError("expected a CSL author with a family or literal name")
    if person.get("literal"):
        return _text(person["literal"])
    name = " ".join(
        str(person[k])
        for k in ("given", "dropping-particle", "non-dropping-particle", "family")
        if person.get(k)
    )
    return _text(", ".join(filter(None, (name, person.get("suffix")))))


def _csl_year(issued):
    if not isinstance(issued, dict):
        return ""
    parts = issued.get("date-parts") or [[]]
    if parts and parts[0] and str(parts[0][0]).isdigit():
        return str(parts[0][0])
    match = re.search(r"\b(\d{4})\b", str(issued.get("raw", "")))
    return match.group(1) if match else ""


def _keywords(value):
    words = value if isinstance(value, list) else re.split(r"[,;]", str(value or ""))
    return [word for item in words if (word := _text(item))]


def from_csl(entry):
    return {
        "key": _text(entry.get("citation-key") or entry.get("id")),
        "title": _text(entry.get("title")),
        "authors": [n for n in map(_csl_name, entry.get("author") or []) if n],
        "year": _csl_year(entry.get("issued")),
        "journal": _text(entry.get("container-title")),
        "doi": doi_identifier(entry.get("DOI")) or doi_identifier(entry.get("URL")),
        "keywords": _keywords(entry.get("keyword")),
    }


def _bib_text(value):
    return _text(Text.from_latex(value or "").render_as("text"))


def from_bibtex(key, entry):
    fields = entry.fields
    year = re.search(r"\d{4}", fields.get("year") or fields.get("date") or "")
    authors = []
    for person in entry.persons.get("author", []):
        name = " ".join(
            [
                *person.first_names,
                *person.middle_names,
                *person.prelast_names,
                *person.last_names,
            ]
        )
        authors.append(
            _bib_text(", ".join(filter(None, (name, " ".join(person.lineage_names)))))
        )
    return {
        "key": key,
        "title": _bib_text(fields.get("title")),
        "authors": authors,
        "year": year.group(0) if year else "",
        "journal": _bib_text(fields.get("journal") or fields.get("journaltitle")),
        "doi": doi_identifier(fields.get("doi")) or doi_identifier(fields.get("url")),
        "keywords": _keywords(_bib_text(fields.get("keywords"))),
    }


def read_export(path):
    """Read a complete export. Report malformed input before changing the catalogue."""
    if path.is_symlink() or not path.is_file():
        raise ValueError(f"{path}: expected a regular export file")
    text = path.read_text(encoding="utf-8-sig")
    if path.suffix.casefold() == ".bib":
        try:
            entries = parse_string(text, "bibtex").entries
            return [from_bibtex(key, entry) for key, entry in entries.items()]
        except PybtexError as error:
            raise ValueError(f"{path}: {error}") from error
    if path.suffix.casefold() != ".json":
        raise ValueError(f"{path}: expected a .json or .bib export")
    data = json.loads(text)
    if isinstance(data, dict):
        data = data.get("items", [data] if "title" in data else None)
    if not isinstance(data, list) or not all(isinstance(item, dict) for item in data):
        raise ValueError(f"{path}: expected a CSL-JSON list of references")
    return [from_csl(entry) for entry in data]


def record_doi(record):
    return doi_identifier(record.get("pid")) or doi_identifier(record.get("source_url"))


def _tail(predicate):
    return re.split(r"[/#:]", str(predicate or ""))[-1]


def _set_attribute(record, names, predicate, label, value, value_range=None):
    """Update the first top-level attribute with a matching predicate, or add one."""
    if not value:
        return False
    attributes = record.setdefault("attributes", [])
    for node in attributes:
        if isinstance(node, dict) and _tail(node.get("predicate")) in names:
            if "value" in node and str(node["value"]) == value:
                return False
            node["value"] = value
            return True
    node = {"predicate": predicate, "display_label": label, "value": value}
    if value_range:
        node["range"] = value_range
    attributes.append(node)
    return True


def apply_entry(record, entry):
    """Write the bibliographic fields. Return True when something changed."""
    changed = False
    if entry["title"] and record.get("title") != entry["title"]:
        record["title"] = entry["title"]
        changed = True
    if entry["authors"] and list(record.get("author_names") or []) != entry["authors"]:
        record["author_names"] = entry["authors"]
        changed = True
    if entry["keywords"] and not record.get("keywords"):
        record["keywords"] = entry["keywords"]
        changed = True
    changed |= _set_attribute(
        record,
        YEAR_NAMES,
        YEAR,
        "Publication year",
        entry["year"],
        "http://www.w3.org/2001/XMLSchema#gYear",
    )
    changed |= _set_attribute(
        record, JOURNAL_NAMES, JOURNAL, "Journal", entry["journal"]
    )
    return changed


def import_bibliography(root, export, into=None, today=None, dry_run=False):
    """Merge an export into the project catalogue and report what changed."""
    root = Path(root).resolve()
    export_path = scoped_path(root, str(export))
    relative = export_path.relative_to(root).as_posix()
    entries = read_export(export_path)
    document = MetadataFile.read(root / "metadata.yaml")
    if not document.data.get("catalogue"):
        raise ValueError(
            "No project catalogue found. Run shacl-py setup --template paper-review first."
        )
    editor = CatalogueEditor(document)
    graph = editor.graph
    validate_catalogue(graph, root)
    target = None
    if into is not None:
        target = scoped_path(root, str(into))
        if target not in editor.sections:
            raise ValueError(
                f"{into}: not listed in catalogue.includes. Add it there first."
            )
    publications = graph.setdefault("publications", [])
    by_doi = defaultdict(dict)
    by_key = defaultdict(dict)
    for record in publications:
        if doi := record_doi(record):
            by_doi[doi][record["pid"]] = record
        previous = record.get("bibliography", {})
        if previous.get("file") == relative and previous.get("key"):
            by_key[previous["key"]][record["pid"]] = record

    stamp = (today or datetime.date.today()).isoformat()
    report = {"updated": [], "added": [], "unchanged": [], "skipped": []}
    for entry in entries:
        doi, key = entry["doi"], entry["key"]
        if not entry["title"] or not (doi or key):
            report["skipped"].append(key or entry["title"] or "(untitled)")
            continue
        matches = by_doi.get(doi, {}) | by_key.get(key, {})
        if len(matches) > 1:
            raise ValueError(
                f"Ambiguous bibliography match for {key or doi}: {', '.join(matches)}"
            )
        record = next(iter(matches.values()), None)
        url = f"https://doi.org/{doi}" if doi else None
        if record is None:
            identity = json.dumps([graph["project"]["pid"], relative, key])
            pid = url or f"urn:uuid:{uuid5(NAMESPACE_URL, identity)}"
            record = new_entity(entry["title"], url, pid=pid)
            publications.append(record)
            if target is not None:
                editor.owners[("publications", pid)] = target
            kind = "added"
        else:
            if doi and (previous_doi := record_doi(record)) and previous_doi != doi:
                raise ValueError(
                    f"Citation key {key!r} matches two DOIs: {previous_doi} and {doi}"
                )
            kind = "unchanged"
        changed = apply_entry(record, entry)
        if url and not record.get("source_url"):
            record["source_url"] = url
            changed = True
        if changed and kind == "unchanged":
            kind = "updated"
        if doi:
            by_doi[doi][record["pid"]] = record
        if key:
            by_key[key][record["pid"]] = record
        source = {"file": relative}
        if entry["key"]:
            source["key"] = entry["key"]
        previous = record.get("bibliography") or {}
        if kind != "unchanged" or source != {
            k: v for k, v in previous.items() if k != "imported"
        }:
            record["bibliography"] = {**source, "imported": stamp}
            if kind == "unchanged":
                kind = "updated"
        report[kind].append(record["pid"])
    validate_catalogue(graph, root)
    if not dry_run:
        report["files"] = sorted(save_metadata(*editor.documents()))
    return report
