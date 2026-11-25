"""Import Zotero CSL JSON and BibTeX into a project catalogue."""

import datetime
import json
import re
from collections import defaultdict
from copy import deepcopy
from pathlib import Path
from uuid import NAMESPACE_URL, uuid5

from pybtex.database import parse_string
from pybtex.exceptions import PybtexError
from pybtex.richtext import Text

from shacl_py.catalogue import validate_catalogue
from shacl_py.files import scoped_path
from shacl_py.metadata_io import CatalogueEditor, MetadataFile, save_metadata
from shacl_py.prompts import new_entity
from shacl_py.sources import doi_identifier, zotero_item_id

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
    result = {
        "key": _text(entry.get("citation-key") or entry.get("id")),
        "title": _text(entry.get("title")),
        "authors": [n for n in map(_csl_name, entry.get("author") or []) if n],
        "year": _csl_year(entry.get("issued")),
        "journal": _text(entry.get("container-title")),
        "doi": doi_identifier(entry.get("DOI")) or doi_identifier(entry.get("URL")),
        "keywords": _keywords(entry.get("keyword")),
    }
    if item := zotero_item_id(entry.get("id")):
        result["zotero_item"] = item
    return result


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
    return merge_bibliography(
        root,
        read_export(export_path),
        export_file=relative,
        into=into,
        today=today,
        dry_run=dry_run,
    )


def _identifiers(doi, source):
    if doi:
        yield ("doi", doi)
    if source.get("file") and source.get("key"):
        yield ("export", source["file"], source["key"])
        # Older CSL imports can already contain the Zotero URI as the citation key.
        if item := zotero_item_id(source["key"]):
            yield ("zotero", item)
    for item in source.get("zotero_items", []):
        yield ("zotero", item)


def merge_bibliography(
    root, entries, *, export_file=None, into=None, today=None, dry_run=False
):
    """Apply a complete bibliography in one validated catalogue transaction."""
    root = Path(root).resolve()
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
    publications = graph.get("publications", [])
    by_id = defaultdict(dict)
    for record in publications:
        for ident in _identifiers(record_doi(record), record.get("bibliography", {})):
            by_id[ident][record["pid"]] = record

    stamp = (today or datetime.date.today()).isoformat()
    report = {"updated": [], "added": [], "unchanged": [], "skipped": []}
    touched = {}
    for entry in entries:
        doi, key = entry["doi"], entry["key"]
        item = entry.get("zotero_item")
        if not entry["title"] or not (doi or key or item):
            report["skipped"].append(key or entry["title"] or "(untitled)")
            continue
        source = {"file": export_file} if export_file else {}
        if export_file and key:
            source["key"] = key
        if item:
            source["zotero_items"] = [item]
        identifiers = list(_identifiers(doi, source))
        matches = {
            pid: rec for ident in identifiers for pid, rec in by_id[ident].items()
        }
        if len(matches) > 1:
            raise ValueError(
                f"Ambiguous bibliography match for {item or key or doi}: {', '.join(matches)}"
            )
        record = next(iter(matches.values()), None)
        url = f"https://doi.org/{doi}" if doi else None
        if record is None:
            identity = json.dumps(
                [graph["project"]["pid"], export_file, key]
                if not item
                else [graph["project"]["pid"], "zotero", item]
            )
            pid = url or f"urn:uuid:{uuid5(NAMESPACE_URL, identity)}"
            record = new_entity(entry["title"], url, pid=pid)
            publications.append(record)
            if target is not None:
                editor.owners[("publications", pid)] = target
            touched[pid] = (record, None)
        else:
            if doi and (previous_doi := record_doi(record)) and previous_doi != doi:
                raise ValueError(
                    f"Bibliography identifier {item or key!r} matches two DOIs: {previous_doi} and {doi}"
                )
            pid = record["pid"]
            if pid not in touched:
                touched[pid] = (record, deepcopy(record))
        apply_entry(record, entry)
        if url and not record.get("source_url"):
            record["source_url"] = url
        for ident in identifiers:
            by_id[ident][record["pid"]] = record
        previous = record.get("bibliography") or {}
        if not export_file:
            source.update({k: previous[k] for k in ("file", "key") if k in previous})
        items = list(previous.get("zotero_items", []))
        if item and item not in items:
            items.append(item)
        if items:
            source["zotero_items"] = items
        if "imported" in previous:
            source["imported"] = previous["imported"]
        if source != previous:
            record["bibliography"] = source

    if publications:
        graph["publications"] = publications
    for pid, (record, original) in touched.items():
        if original == record:
            report["unchanged"].append(pid)
        else:
            record["bibliography"]["imported"] = stamp
            report["added" if original is None else "updated"].append(pid)
    validate_catalogue(graph, root)
    if not dry_run:
        report["files"] = sorted(save_metadata(*editor.documents()))
    return report
