"""Read-only shaclpy viewer backed by Concepts and MetaLad records."""

import json
import os
import re
import shlex
from functools import cache
from pathlib import Path, PurePosixPath
from urllib.parse import urlsplit

import streamlit as st
import yaml
from jinja2 import Environment, FileSystemLoader

from shacl_py.attributes import (
    annotation_values,
    attribute_groups,
    attribute_value,
    data_content,
    is_data_content,
    metadata_groups,
)
from shacl_py.branding import branding
from shacl_py.browser import (
    dataset_keys,
    file_metadata,
    file_selection,
    items_from,
    linked_file_parts,
    linked_file_selection,
    neighbours,
    publication_key,
    searchable,
    source_content,
)
from shacl_py.collection import Collection
from shacl_py.collection_view import detail_view
from shacl_py.files import IMAGE_TYPES, inline_image, scoped_path
from shacl_py.graph import record_graph
from shacl_py.methods import (
    MethodIndex,
    declared_file_records,
    file_attributes,
    local_file_id,
    method_view,
    techniques,
)
from shacl_py.methods import (
    annotations as method_annotations,
)
from shacl_py.native import declared_title
from shacl_py.navigation import current_route, url
from shacl_py.records import load_records
from shacl_py.sources import source_url
from shacl_py.study import person_names
from shacl_py.terms import TermIndex, grouped_terms, topic_terms

assets = Path(__file__).with_name("templates")
template = Environment(loader=FileSystemLoader(assets), autoescape=True).get_template(
    "browser.html"
)


FORMATS = {
    ".tar.gz": "TAR.GZ archive",
    ".zip": "ZIP archive",
    ".rar": "RAR archive",
    ".npz": "NumPy archive",
    ".ome.tif": "OME-TIFF",
    ".ome.tiff": "OME-TIFF",
    ".tif": "TIFF",
    ".tiff": "TIFF",
    ".png": "PNG image",
    ".jpg": "JPEG image",
    ".jpeg": "JPEG image",
    ".gif": "GIF image",
    ".webp": "WebP image",
    ".xlsx": "Excel workbook",
    ".csv": "CSV",
    ".tsv": "TSV",
    ".parquet": "Parquet",
    ".mrc": "MRC volume",
    ".json": "JSON",
    ".yaml": "YAML",
    ".yml": "YAML",
    ".md": "Markdown",
    ".ipynb": "Jupyter notebook",
    ".pdf": "PDF",
    ".txt": "Text",
}
PREVIEW_BYTES = 8192


def human_size(n):
    if n < 1024:
        return f"{n:,} B"
    if n < 1048576:
        return f"{n / 1024:.1f} KiB"
    return f"{n / 1048576:.1f} MiB"


def linked_size(attributes):
    """Use a declared DCAT byte count for the external file's Size column."""
    for node in attributes or []:
        value = node.get("value")
        if node.get("predicate") == "http://www.w3.org/ns/dcat#byteSize":
            try:
                count = int(value)
                if count >= 0:
                    return human_size(count)
            except TypeError, ValueError, OverflowError:
                continue
        elif value is None and (size := linked_size(node.get("attributes"))):
            return size
    return ""


def file_format(name):
    lower = name.casefold()
    suffix = next((s for s in FORMATS if lower.endswith(s)), "")
    if suffix:
        return FORMATS[suffix]
    return Path(name).suffix.removeprefix(".").upper() or "File"


def annex_key(path):
    """Name the git-annex key behind a symlinked or unlocked file, if any."""
    try:
        if path.is_symlink():
            target = os.readlink(path)
            return Path(target).name if "/annex/objects/" in target else ""
        if path.is_file() and path.stat().st_size <= 1024:
            first = path.read_bytes().split(b"\n", 1)[0].decode(errors="replace")
            if first.startswith("/annex/objects/"):
                return first.rsplit("/", 1)[-1]
    except OSError:
        pass
    return ""


def file_preview(path, base):
    """Return an inline image or the leading text of a local file.

    Symlinks are followed only when they resolve inside the project, as
    present git-annex files do.
    """
    preview = {"image": None, "text": None, "truncated": False}
    try:
        if not path.is_file() or (
            path.is_symlink() and not path.resolve().is_relative_to(base)
        ):
            return preview
        if path.suffix.casefold() in IMAGE_TYPES:
            preview["image"] = inline_image(path, base)
            return preview
        with path.open("rb") as stream:
            data = stream.read(PREVIEW_BYTES + 1)
    except OSError:
        return preview
    text = data[:PREVIEW_BYTES].decode("utf-8", errors="replace")
    if "\x00" not in text and "\ufffd" not in text.rstrip("\ufffd"):
        preview["text"] = text
        preview["truncated"] = len(data) > PREVIEW_BYTES
    return preview


def display(value):
    if isinstance(value, list):
        return ", ".join(filter(None, map(display, value)))
    if isinstance(value, dict):
        return declared_title(value) or str(value.get("@id", ""))
    return "" if value is None else str(value)


def field(item, *names):
    return (
        next((display(item.fields[n]) for n in names if item.fields.get(n)), "")
        if item
        else ""
    )


def author_line(item, limit=None):
    source = source_content(item.source)
    ids = item.fields.get("author")
    if (
        isinstance(source, dict)
        and isinstance(source.get("person"), dict)
        and isinstance(ids, list)
        and all(isinstance(k, str) for k in ids)
    ):
        names = person_names(source["person"], ids)
    else:
        value = next(
            (
                item.fields[k]
                for k in ("author_names", "authors", "author", "creator")
                if item.fields.get(k)
            ),
            [],
        )
        names = (
            list(filter(None, map(display, value)))
            if isinstance(value, list)
            else [display(value)]
        )
    if limit is not None and len(names) > limit:
        return ", ".join(names[:limit]) + ", …"
    return ", ".join(names)


def sidebar_author(item):
    primary = field(item, "primary_author").strip() if item.is_publication else ""
    if not primary:
        return author_line(item)
    source = source_content(item.source)
    if isinstance(source, dict) and isinstance(source.get("person"), dict):
        return person_names(source["person"], [primary])[0]
    return primary


def short_authors(item):
    """Abbreviate the author list as 'Surname et al.'."""
    names = [n.strip() for n in author_line(item).split(",") if n.strip()]
    if not names:
        return ""
    return names[0].split()[-1] + (" et al." if len(names) > 1 else "")


def declared_year(item):
    date = field(item, "year", "datePublished") or attribute_value(
        item.fields, "issued", "datePublished", "date"
    )
    return date[:4] if date[:4].isdigit() else date


def short_citation(item, year=None):
    """Cite a paper as 'Surname et al. Year', falling back to its title."""
    if year is None:
        year = declared_year(item)
    return " ".join(filter(None, [short_authors(item) or item.label, year]))


def labels(item):
    value = item.fields.get("labels", [])
    return [
        v for v in (value if isinstance(value, list) else [value]) if isinstance(v, str)
    ]


def browse(items, stored, base, brand, params, collections):
    papers = [i for i in items if i.is_publication]
    datasets = [i for i in items if i.is_dataset]
    keys = dataset_keys(papers, datasets)

    def key_for(i):
        return keys[i] if i.is_dataset else publication_key(i)

    # One displayed record can have both catalogue and StudyMiniMeta descriptions.
    highlighted = {key_for(i) for i in items if i.fields.get("highlighted") is True}

    def is_starred(i):
        return key_for(i) in highlighted

    term_index = TermIndex([*papers, *datasets], key_for)
    namespaces = {
        project.source.folder: ns
        for project in items
        if project.is_project
        if (ns := method_annotations(project.fields).get("identifier_namespace"))
    }

    def topics(i):
        return term_index.topics(key_for(i))

    years = {}
    for paper in papers:
        if year := declared_year(paper):
            years.setdefault(key_for(paper), set()).add(year)

    def publication_year(item):
        if year := declared_year(item):
            return year
        matches = years.get(key_for(item), set())
        return next(iter(matches)) if len(matches) == 1 else ""

    others = [i for i in items if not i.is_publication and not i.is_dataset]
    sections = {
        name: group
        for name, group in [
            ("Papers", papers),
            ("Datasets", datasets),
            ("Records", others),
        ]
        if group
    }
    selected_item = next(
        (
            i
            for i in items
            if i.route == {k: params.get(k, "") for k in ("record", "entry")}
        ),
        None,
    )
    collection_sections = {collection.section: collection for collection in collections}
    default = next(
        (name for name, group in sections.items() if selected_item in group),
        next(iter(sections), next(iter(collection_sections), None)),
    )
    requested = params.get("section")
    routes = {name.lower(): name for name in sections}
    if papers or datasets:
        routes["terms"] = "Terms"
    if items:
        routes["graph"] = "Graph"
    for c in collections:
        routes[c.section] = c.section
        routes.setdefault(c.key, c.section)
    section = routes.get(requested) if requested else default
    collection = collection_sections.get(section)
    if (
        collection
        and params.get("record")
        and params.get("entry") not in collection.entries
    ):
        # Ignore a selection carried over from a paper or dataset.
        params = {
            k: v
            for k, v in params.items()
            if k not in ("record", "entry", "variant", "view")
        }
    q = params.get("q", "").strip().casefold()
    shared_query = None if collection else q
    facet_route = {
        key: params[key] for key in ("technique", "compartment") if params.get(key)
    }
    nav = [
        (
            name,
            url(
                facet_route if name in ("Papers", "Datasets") else {},
                section=name.lower(),
                q=shared_query,
            ),
            len({key_for(i) for i in group}),
            name == section,
        )
        for name, group in sections.items()
    ]
    records_tab = nav.pop() if others else None
    nav.extend(
        (
            c.title,
            url(
                {},
                section=c.section,
                q=q if section == c.section else shared_query or None,
            ),
            len(c.groups) if c.presentation else len(c.entries),
            section == c.section,
        )
        for c in collections
    )
    if records_tab:
        nav.append(records_tab)
    if papers or datasets:
        nav.append(
            (
                "Terms",
                url({}, section="terms", q=shared_query or None),
                None,
                section == "Terms",
            )
        )
    if items:
        nav.append(
            (
                "Graph",
                url({}, section="graph", q=shared_query or None),
                None,
                section == "Graph",
            )
        )
    context = {
        "brand": brand,
        "params": params,
        "section": section,
        "url": url,
        "nav": nav,
        "grouped_terms": grouped_terms,
        "topic_terms": topic_terms,
    }
    if section is None:
        st.html(template.render(context))
        return
    if section == "Terms":
        subject, term, keyword = (
            params.get(k, "") for k in ("subject", "term", "keyword")
        )
        # Older bookmarks use the term parameter for general keywords.
        if term.startswith("keyword/"):
            keyword, term = keyword or term, ""
        term_route = {
            "section": "terms",
            "subject": subject,
            "term": term,
            "keyword": keyword,
        }
        st.html(
            template.render(
                context,
                term_route=term_route,
                term_results=term_index.results(
                    q, subject, term, is_starred, keyword=keyword
                ),
                term_filters=term_index.filters(),
                is_starred=is_starred,
            )
        )
        return
    if collection:
        if collection.presentation:
            detail = detail_view(collection, params)
            group = detail.get("group")
            subject_links = {}
            if group:
                refs = [
                    *group.terms,
                    *group.members,
                    *(
                        f"{ns}:{collection.key}:{key}"
                        for root, ns in namespaces.items()
                        if root == collection.project_root
                        for key in group.members
                    ),
                ]
                subject_links = {
                    ref: term_index.facets["subject"][ref].label
                    for ref in refs
                    if ref in term_index.facets["subject"]
                }
            st.html(
                template.render(
                    context,
                    collection=collection,
                    detail=detail,
                    subject_links=subject_links,
                )
            )
            return
        rows = {
            key: row
            for key, row in collection.entries.items()
            if not q or q in searchable(row)
        }
        selected = params.get("entry", next(iter(rows), None))
        st.html(
            template.render(
                context,
                collection=collection,
                rows=rows,
                selected=selected,
                row=rows.get(selected),
            )
        )
        return
    if section == "Graph":
        graph = record_graph(
            items, key_for, selected=selected_item, label=params.get("label"), query=q
        )
        relation = params.get("relation", "")
        predicates = {predicate for _, predicate, _ in graph.edges}
        if relation:
            predicates.add(relation)
            graph = graph.with_relationship(relation)
        st.html(
            template.render(
                context, graph=graph, predicates=sorted(predicates), relation=relation
            )
        )
        if graph.nodes:
            network = st.components.v2.component(
                "shacl-py.network",
                html=(assets.parent / "network/network.html").read_text(),
                css="network.css",
                js="network.js",
            )
            network(data=graph.network_data(), key="record_network")
        return
    scope = sections[section]
    global_ds = section == "Datasets"

    @cache
    def related(i):
        return neighbours(i, items)

    @cache
    def listing(i, directory="."):
        folders, groups = file_selection(i, directory)
        return folders, {
            row["Relative path"]: row for _, rows in groups for row in rows
        }

    def file_count(i):
        return len(listing(i)[1]) + len(i.linked_files)

    @cache
    def dataset_groups(i):
        return attribute_groups(i.fields.get("attributes"))

    @cache
    def record_methods(i):
        return list(techniques(i.fields.get("attributes")))

    def attribute_count(i):
        return sum(group["count"] for group in dataset_groups(i))

    @cache
    def dataset_summary(i):
        if count := file_count(i):
            return count, "file"
        if folders := listing(i)[0]:
            return len(folders), "folder"
        if count := attribute_count(i):
            return count, "attribute"
        if record_methods(i):
            return len(record_methods(i)), "method"
        return 0, "file"

    def default_dataset_tab(i):
        return {"attribute": "attributes", "method": "methods"}.get(
            dataset_summary(i)[1], "files"
        )

    def count_label(count, noun):
        return f"{count} {noun}{'s' if count != 1 else ''}"

    def linked_items(i, group):
        unique = {}
        for j in related(i):
            if j in group:
                unique.setdefault(key_for(j), j)
        return list(unique.values())

    def roles(i):
        return [related(p)[i] for p in papers if i in related(p) and related(p)[i]]

    def local_folder(i):
        return field(i, "local_folder") or (
            os.path.relpath(i.folder, base) if i and i.has_folder else ""
        )

    def pid(i):
        return field(i, "pid", "@id", "identifier")

    def file_matches(i, q):
        return any(
            q in searchable([path, stored.get(i.folder / path, [])])
            for path in listing(i)[1]
        )

    def sidebar_match(i, filter_words, extra=""):
        if not filter_words:
            return True
        parsed = parse_terms(" ".join(filter_words))
        if parsed.scoped and (i.is_publication or i.is_dataset):
            return topic_match(i, parsed)
        text = searchable([i.label, i.key, i.ref, i.fields, author_line(i), extra])
        return all(word in text for word in filter_words) or topic_match(i, parsed)

    index = MethodIndex(collections, namespaces.values())
    technique = facet_route.get("technique", "")
    compartment = facet_route.get("compartment", "")

    @cache
    def record_facets(i):
        return index.facets(i.fields)

    @cache
    def file_records(i):
        return declared_file_records(i)

    @cache
    def catalogue_file_content(folder):
        # A paper and a dataset can list the same local file.
        content = {}
        for member in [*papers, *datasets]:
            if member.source.folder == folder:
                for identifier, record in file_records(member).items():
                    if facts := data_content(record.get("attributes")):
                        content.setdefault(identifier, {}).update(facts)
        return content

    def local_file_content(owner, path):
        records = catalogue_file_content(owner.source.folder)
        declared = records.get(local_file_id(owner, path), {})
        return declared | data_content(file_attributes(stored.get(path)))

    def linked_file_content(owner, linked):
        declared = file_records(owner).get(linked["url"], {})
        return data_content(declared.get("attributes")) | data_content(
            linked.get("attributes")
        )

    def listed_path(i, relative):
        if relative in listing(i)[1]:
            return "."
        parts = linked_file_parts(relative)
        if len(parts) > 1:
            directory = "/".join(parts[:-1])
            if (i.folder / directory).is_dir() and relative in listing(i, directory)[1]:
                return directory
        return None

    @cache
    def file_facets(i):
        records = dict(file_records(i))
        for f in i.linked_files:
            claimed = records.get(f["url"], {})
            records[f["url"]] = {
                **claimed,
                **f,
                "attributes": [
                    *claimed.get("attributes", []),
                    *f.get("attributes", []),
                ],
            }
        if stored and i.has_folder:
            for path, entries in stored.items():
                if (
                    path.is_relative_to(i.folder)
                    and listed_path(i, path.relative_to(i.folder).as_posix())
                    is not None
                ):
                    key = local_file_id(i, path) or path
                    claimed = records.get(key, {})
                    records[key] = {
                        **claimed,
                        "attributes": [
                            *claimed.get("attributes", []),
                            *file_attributes(entries),
                        ],
                    }
        return [index.facets(record) for record in records.values()]

    def matches_facets(i):
        own = record_facets(i)
        if own.matches(technique, compartment):
            return True
        # Both selected facets must belong to this record or to the same file.
        return any(
            f.matches(
                "" if technique in own.acquisition else technique,
                "" if compartment in own.subjects else compartment,
            )
            for f in file_facets(i)
        )

    if section in ("Papers", "Datasets"):
        for member in [*papers, *datasets]:
            record_facets(member)
        for member in [*papers, *datasets]:
            file_facets(member)

    tag = params.get("tag", "All")
    can_star = section in ("Papers", "Datasets") or any(is_starred(i) for i in scope)
    starred_only = can_star and params.get("starred") == "1"
    filter_words = params.get("filter", "").casefold().split()
    sidebar_route = {
        "section": section.lower(),
        "q": q,
        "filter": params.get("filter", ""),
        **facet_route,
    }
    if starred_only:
        sidebar_route["starred"] = "1"
    options = [
        "All",
        *sorted(
            {v for i in scope for v in (roles(i) if global_ds else labels(i))}
            - {"All", "Not all local"}
        ),
    ]
    if global_ds:
        options.append("Not all local")
    parse_terms = cache(term_index.query)
    parsed_query = parse_terms(q)

    def topic_match(i, query):
        return any(t.matches(query) for t in topics(i))

    def search_matches(i, linked):
        if topic_match(i, parsed_query):
            return True
        if parsed_query.scoped and (i.is_publication or i.is_dataset):
            return False
        return (
            q in searchable([i.ref, i.fields])
            or file_matches(i, q)
            or any(
                q in searchable(d.fields)
                or file_matches(d, q)
                or topic_match(d, parsed_query)
                for d in linked
            )
        )

    shown = []
    for i in scope:
        if starred_only and not is_starred(i):
            continue
        ds = linked_items(i, datasets)
        if (
            facet_route
            and section in ("Papers", "Datasets")
            and not matches_facets(i)
            and (not i.is_publication or not any(matches_facets(d) for d in ds))
        ):
            continue
        if q and not search_matches(i, ds):
            continue
        if tag == "Not all local" and global_ds:
            if (
                not i.linked_files
                and (i.has_folder or not i.fields.get("source_url"))
                and all(
                    r["Availability"] == "Available" for r in listing(i)[1].values()
                )
            ):
                continue
        elif tag != "All" and tag not in (roles(i) if global_ds else labels(i)):
            continue
        if global_ds:
            parent = next(iter(linked_items(i, papers)), None)
            byline = short_citation(parent, publication_year(parent)) if parent else ""
            year = ""
        else:
            byline, year = sidebar_author(i), publication_year(i)
        if not sidebar_match(i, filter_words, [byline, year]):
            continue
        shown.append(
            {
                "item": i,
                "href": url(
                    sidebar_route | i.route,
                    tag=tag,
                    view=params.get("view")
                    if params.get("view") in ("methods", "terms")
                    and section in ("Papers", "Datasets")
                    else None,
                ),
                "starred": is_starred(i),
                "authors": byline,
                "venue": field(i, "format", "encodingFormat", "media_type")
                if global_ds
                else field(i, "venue", "journal"),
                "year": year,
                "count": count_label(*dataset_summary(i))
                if global_ds
                else count_label(len(ds), "dataset"),
                "tags": labels(i),
                "annotations": annotation_values(i.fields),
            }
        )
    if section in ("Papers", "Datasets"):
        unique = {}
        for row in shown:
            key = key_for(row["item"])
            if key not in unique or row["item"] is selected_item:
                unique[key] = row
        shown = list(unique.values())
    shown.sort(key=lambda row: not row["starred"])
    item = (
        selected_item
        if any(r["item"] is selected_item for r in shown)
        else next((r["item"] for r in shown), None)
    )
    context.update(
        {
            "shown": shown,
            "global_ds": global_ds,
            "techniques": sorted(
                index.acquisition.items(), key=lambda pair: pair[1].casefold()
            ),
            "compartments": sorted(
                index.compartments.items(), key=lambda pair: pair[1].casefold()
            ),
            "facet_route": facet_route,
            "show_facets": section in ("Papers", "Datasets")
            and bool(index.acquisition or index.compartments or facet_route),
            "facet_args": {
                **sidebar_route,
                "tag": tag,
                **{
                    k: params[k]
                    for k in (
                        "record",
                        "entry",
                        "view",
                        "dataset",
                        "dataset_record",
                        "dtab",
                        "dsfilter",
                    )
                    if k in params
                },
            },
            "options": options,
            "active_filter": tag,
            "can_star": can_star,
            "starred_only": starred_only,
            "is_starred": is_starred,
            "sidebar_route": sidebar_route,
            "item": item,
        }
    )

    if not item:
        st.html(template.render(context))
        return
    item_route = sidebar_route | item.route | {"tag": tag}
    ds = sorted(linked_items(item, datasets), key=lambda d: not is_starred(d))
    parents = list({publication_key(p): p for p in linked_items(item, papers)}.values())
    tabs = (
        [
            ("files", "Files", file_count(item)),
            (
                "attributes",
                "Attributes",
                attribute_count(item),
            ),
            ("methods", "Methods", len(record_methods(item))),
            ("paper", "Paper", None),
        ]
        if global_ds
        else [
            ("datasets", "Datasets", len(ds)),
            ("abstract", "Abstract", None),
            ("notes", "Notes", None),
            ("files", "Other files", None),
        ]
    )
    if item.is_publication:
        tabs.insert(2, ("methods", "Methods", len(record_methods(item))))
    if not global_ds and (count := attribute_count(item)):
        tabs.append(("attributes", "Attributes", count))
    if item.is_publication or item.is_dataset:
        tabs.append(("terms", "Terms", len(topic_terms(topics(item)))))
    tabs.append(("source", "Raw metadata", None))
    default_view = default_dataset_tab(item) if global_ds else tabs[0][0]
    view = params.get("view", default_view)
    if view not in {k for k, _, _ in tabs}:
        view = default_view
    dsrows = []
    dataset_words = params.get("dsfilter", "").casefold().split()
    for d in ds:
        if sidebar_match(d, dataset_words, related(item)[d]):
            dsrows.append(
                {
                    "item": d,
                    "annotations": annotation_values(d.fields),
                    "count": count_label(*dataset_summary(d)),
                    "role": related(item)[d],
                    "href": url(
                        item_route,
                        view="datasets",
                        dataset=d.key,
                        dataset_record=d.ref,
                        dsfilter=params.get("dsfilter", ""),
                    ),
                }
            )
    selected = next(
        (
            r["item"]
            for r in dsrows
            if r["item"].key == params.get("dataset")
            and r["item"].ref == params.get("dataset_record")
        ),
        next((r["item"] for r in dsrows), None),
    )
    owner = selected if view == "datasets" else item
    route = item_route | {"view": view}
    if view == "datasets" and selected:
        route.update(dataset=selected.key, dataset_record=selected.ref)
        if params.get("dsfilter"):
            route["dsfilter"] = params["dsfilter"]
    directory = params.get("folder", ".")
    linked_folders, linked_rows = (
        linked_file_selection(owner.linked_files, directory)
        if owner and view in ("datasets", "files")
        else ([], [])
    )
    try:
        folders, files = (
            listing(owner, directory)
            if owner and view in ("datasets", "files")
            else ([], {})
        )
    except ValueError:
        if directory == "." or not (linked_folders or linked_rows):
            raise
        # A virtual folder need not also exist in a dataset's local folder.
        folders, files = [], {}
    folders = sorted(set(folders) | set(linked_folders), key=str.casefold)
    if item.is_publication and view == "files":
        excluded = {d.folder / path for d in ds for path in listing(d)[1]}
        files = {p: r for p, r in files.items() if item.folder / p not in excluded}
    up = url(route, folder=str(PurePosixPath(directory).parent))
    if directory != ".":
        route["folder"] = directory
    rows = []
    for path, r in files.items():
        local = r["Availability"] == "Available"
        size = ""
        if local:
            try:
                size = human_size((owner.folder / path).stat().st_size)
            except OSError:
                pass
        rows.append(
            {
                "name": Path(path).name,
                "path": path,
                "parent": str(Path(path).parent),
                "size": size,
                "local": local,
                "linked": False,
                "content": local_file_content(owner, owner.folder / path),
            }
        )
    for row in linked_rows:
        linked = row["file"]
        rows.append(
            {
                "name": row["name"],
                "path": row["path"],
                "linked": True,
                "href": linked["url"],
                "preview": linked.get("preview_url") or linked["url"],
                "parent": row["parent"],
                "size": linked_size(linked.get("attributes")),
                "content": linked_file_content(owner, linked),
                "local": False,
            }
        )
    dataset_owner = item if global_ds else selected if view == "datasets" else None
    try:
        dataset_url = source_url(field(dataset_owner, "source_url", "url"))
    except ValueError:
        dataset_url = None
    external = bool(dataset_url and dataset_owner and not dataset_owner.has_folder)
    availability = ""
    if dataset_owner:
        root_folders, root_files = listing(dataset_owner)
        total = file_count(dataset_owner)
        if total:
            local_count = sum(
                r["Availability"] == "Available" for r in root_files.values()
            )
            availability = f"{local_count} of {total} files local"
            if external:
                availability = f"External · {availability}"
        elif root_folders:
            availability = count_label(len(root_folders), "folder")
        elif external:
            availability = "External source"
        else:
            availability = "0 files" if dataset_owner.has_folder else "Metadata only"

    def dataset_link(d):
        return {
            "label": d.label,
            "href": url({"section": "datasets"} | d.route, view="attributes"),
        }

    def provenance(d):
        if not d or not d.is_dataset:
            return [], []
        own = d.fields.get("source_datasets") or []
        derived = {key_for(x): x for x in datasets if x.key in own}
        used = {
            key_for(x): x
            for x in datasets
            if d.key in (x.fields.get("source_datasets") or [])
        }
        return list(map(dataset_link, derived.values())), list(
            map(dataset_link, used.values())
        )

    def resolve_resource(ref):
        # Dataset PIDs are exact. A file name is only a link when it identifies
        # one visible file in the record's dataset or its paper's datasets.
        direct = {key_for(d): d for d in datasets if d.key == ref}
        if len(direct) == 1:
            return url(
                next(iter(direct.values())).route, section="datasets", view="files"
            )

        def file_links(d):
            target = d.route | {
                "section": "datasets" if d.is_dataset else "papers",
                "view": "files",
            }
            found = []
            for f in d.linked_files:
                name = f["name"]
                parts = linked_file_parts(name)
                if ref in (name, parts[-1], f["url"]):
                    found.append(
                        url(target, linked=name, folder="/".join(parts[:-1]) or None)
                    )
            if d.has_folder:
                candidates = listing(d)[1]
                for path in candidates:
                    if ref in (
                        local_file_id(d, d.folder / path),
                        path,
                        PurePosixPath(path).name,
                        (d.folder / path).relative_to(base).as_posix(),
                    ):
                        found.append(url(target, file=path))
                # Ordinary folders are browsed one level at a time.
                if (
                    ref not in candidates
                    and (directory := listed_path(d, ref)) is not None
                ):
                    found.append(url(target, file=ref, folder=directory))
            return found

        candidates = [dataset_owner or item]
        siblings = (
            ds
            if item.is_publication
            else [d for p in parents for d in linked_items(p, datasets)]
        )
        for scope in (
            candidates,
            list(dict.fromkeys(d for d in siblings if d not in candidates)),
        ):
            found = {href for d in scope for href in file_links(d)}
            if found:
                return next(iter(found)) if len(found) == 1 else None
        return None

    derived_from, used_by = provenance(dataset_owner)
    default_dtab = default_dataset_tab(selected) if selected else "files"
    dtab = params.get("dtab", default_dtab)
    if dtab not in ("files", "attributes", "methods", "terms"):
        dtab = default_dtab
    doi_label = field(item, "doi", "source_url", "url", "sameAs")
    try:
        doi = source_url(doi_label)
    except ValueError:
        doi = None
    notes = [field(item, "notes")]
    notes.extend(
        display(r.get("notes"))
        for r in getattr(item.source, "graph", {}).get("reviews", [])
        if r.get("publication") == item.key
    )
    displayed_topics = topics(owner) if owner else ()
    context.update(
        item_route=item_route,
        view=view,
        tabs=tabs,
        sidebar_groups=dataset_groups(item),
        pid=pid(item),
        folder=local_folder(item),
        authors=author_line(item, limit=10),
        venue=field(item, "journal", "venue", "isPartOf"),
        year=publication_year(item),
        keywords=field(item, "keywords", "keyword"),
        tags=labels(item),
        doi=doi,
        doi_label=doi_label,
        dsrows=dsrows,
        selected=selected,
        ds_pid=pid(selected),
        dataset_url=dataset_url,
        dataset_description=field(dataset_owner, "description"),
        dataset_content_facts=[
            (label, value, False, None)
            for label, value in data_content(
                dataset_owner.fields.get("attributes")
            ).items()
        ]
        if dataset_owner
        else [],
        ds_folder=local_folder(selected),
        role=", ".join(dict.fromkeys(roles(item)))
        if global_ds
        else related(item).get(selected, ""),
        paper_rows=[
            {
                "href": url(p.route, dataset=item.key, dataset_record=item.ref),
                "short": short_citation(p, publication_year(p)),
                "title": p.label,
                "starred": is_starred(p),
            }
            for p in sorted(parents, key=lambda paper: not is_starred(paper))
        ],
        availability=availability,
        external=external,
        host=urlsplit(dataset_url).netloc if dataset_url else "",
        annotations=annotation_values(dataset_owner.fields) if dataset_owner else [],
        dtab=dtab,
        record_topics=displayed_topics,
        term_relationships=[
            t for t in displayed_topics if t.note or t.subject and t.value
        ],
        method_groups=method_view(record_methods(owner), index.labels, resolve_resource)
        if owner and (view == "methods" or view == "datasets" and dtab == "methods")
        else [],
        dtabs=[
            ("files", "Files", file_count(selected) if selected else 0),
            (
                "attributes",
                "Attributes",
                attribute_count(selected) if selected else 0,
            ),
            ("methods", "Methods", len(record_methods(selected)) if selected else 0),
            ("terms", "Terms", len(topic_terms(topics(selected))) if selected else 0),
        ],
        attr={
            "groups": attribute_groups(item.fields.get("attributes"), "Paper")
            if view == "attributes" and not global_ds
            else dataset_groups(dataset_owner)
            if dataset_owner
            else [],
            "derived": derived_from,
            "used": used_by,
        },
        format=field(owner, "format", "encodingFormat", "media_type"),
        parents=parents,
        route=route,
        file_owner=owner,
        rows=rows,
        folders=folders,
        up=up,
        abstract=field(item, "abstract", "description") or "No abstract supplied.",
        notes="\n\n".join(filter(None, notes)) or "No notes supplied.",
        raw=yaml.safe_dump(
            item.fields or source_content(item.source),
            allow_unicode=True,
            sort_keys=False,
        )
        if view == "source"
        else "",
    )
    if view == "source":
        context["alternate_sources"] = [
            p for p in items if p is not item and key_for(p) == key_for(item)
        ]
        context["source"] = yaml.safe_dump(
            source_content(item.source), allow_unicode=True, sort_keys=False
        )
    if "linked" in params and owner:
        linked = next(
            (f for f in owner.linked_files if f["name"] == params["linked"]), None
        )
        if linked:
            paper = item if item.is_publication else next(iter(parents), None)
            declared = file_records(owner).get(linked["url"], {})
            extra = declared.get("attributes", [])
            file_content = linked_file_content(owner, linked)
            file_methods = techniques([*linked.get("attributes", []), *extra])
            context["fp"] = linked_panel(
                owner, linked, route, paper, page=params.get("page")
            )
        else:
            st.warning("This file is outside the current selection.")
    elif "file" in params and owner:
        if row := files.get(params["file"]):
            paper = item if item.is_publication else next(iter(parents), None)
            path = owner.folder / row["Relative path"]
            declared = file_records(owner).get(local_file_id(owner, path), {})
            extra = declared.get("attributes", [])
            file_content = local_file_content(owner, path)
            file_methods = techniques([*extra, *file_attributes(stored.get(path))])
            context["fp"] = file_panel(
                owner, row, route, stored, base, paper, page=params.get("page")
            )
        else:
            st.warning("This file is outside the current selection.")
    if "fp" in context:
        context["fp"]["rows"].extend(
            (label, value, False) for label, value in file_content.items()
        )
        if extra:
            panel = context["fp"]
            panel["groups"] = attribute_groups(extra, "File") + panel["groups"]
            raw = yaml.safe_load(panel["raw"])
            raw["catalogue_file"] = declared
            panel["raw"] = yaml.safe_dump(raw, sort_keys=False, allow_unicode=True)
        context["fp"]["methods"] = method_view(
            file_methods, index.labels, resolve_resource
        )
    st.html(template.render(context))


def file_panel(owner, row, route, stored, base, paper, page=None):
    """Describe one listed file for the side drawer and its full page."""
    relative = row["Relative path"]
    path = scoped_path(owner.folder, relative)
    local = row["Availability"] == "Available"
    key = annex_key(path)
    size = ""
    if local:
        try:
            size = human_size(path.stat().st_size)
        except OSError:
            pass
    if not size and (match := re.search(r"-s(\d+)--", key)):
        size = human_size(int(match.group(1)))
    shown_path = os.path.relpath(path, base)
    kind = file_format(path.name)
    rows = [("Path", shown_path, True), ("Size", size or "—", False)]
    rows += [
        ("Format", kind, False),
        ("Availability", "Local" if local else "Remote (annexed)", False),
    ]
    if key:
        rows.append(("Annex key", key, True))
    raw = {
        "path": shown_path,
        "size": size or None,
        "format": kind,
        "annex_key": key or None,
        "present": local,
        "dataset" if owner.is_dataset else "record": field(owner, "pid", "@id")
        or owner.label,
    }
    if paper and paper is not owner:
        raw["paper"] = field(paper, "pid", "@id") or paper.label
    entries = stored.get(path)
    if entries:
        raw["metadata"] = json.loads(json.dumps(entries, default=str))
    crumbs = []
    if paper:
        crumbs.append((short_citation(paper), url(paper.route, view="abstract")))
    if owner is not paper:
        crumbs.append((owner.label, url(route)))
    return {
        "name": path.name,
        "page": page == "file",
        "local": local,
        "format": kind,
        "rows": rows,
        "fetch": "datalad get " + shlex.quote(shown_path),
        "owner_kind": "Dataset"
        if owner.is_dataset
        else "Paper"
        if owner.is_publication
        else "Record",
        "owner": owner.label,
        "owner_description": field(owner, "description"),
        "paper": short_citation(paper) if paper and paper is not owner else "",
        "crumbs": crumbs,
        "back": url(route),
        "open": url(route, file=relative, page="file"),
        "raw": yaml.safe_dump(
            {k: v for k, v in raw.items() if v is not None},
            allow_unicode=True,
            sort_keys=False,
            default_flow_style=False,
        ),
        **content_groups(metadata_groups(entries), owner),
        **(file_preview(path, base) if local else {"image": None, "text": None}),
    }


def content_groups(file_groups, owner):
    """Combine a file's own attributes with those it inherits from its dataset."""
    inherited = (
        attribute_groups(
            [a for a in owner.fields.get("attributes") or [] if not is_data_content(a)],
            "Dataset",
        )
        if owner.is_dataset
        else []
    )
    count = len(inherited)
    return {
        "groups": file_groups + inherited,
        "content_note": f"{count} group{'s' if count != 1 else ''} inherited from the dataset"
        if count
        else "",
    }


def linked_panel(owner, linked, route, paper, page=None):
    """Describe one externally hosted file linked from a dataset record."""
    try:
        provider = source_url(
            linked.get("provider_url") or field(owner, "source_url", "url")
        )
    except ValueError:
        provider = None
    download = linked["url"]
    preview = linked.get("preview_url") or download
    host = urlsplit(provider or download).netloc
    kind = file_format(linked["name"])
    rows = [
        ("Host", host, True),
        ("Format", kind, False),
        ("Availability", "External", False),
    ]
    parts = linked_file_parts(linked["name"])
    if len(parts) > 1:
        rows.insert(0, ("Path", linked["name"], True))
    if size := linked_size(linked.get("attributes")):
        rows.insert(1, ("Size", size, False))
    raw = {
        **linked,
        "format": kind,
        "external": True,
        "dataset": field(owner, "pid", "@id") or owner.label,
    }
    if paper and paper is not owner:
        raw["paper"] = field(paper, "pid", "@id") or paper.label
    crumbs = []
    if paper:
        crumbs.append((short_citation(paper), url(paper.route, view="abstract")))
    if owner is not paper:
        crumbs.append((owner.label, url(route)))
    return {
        "name": parts[-1],
        "page": page == "file",
        "local": False,
        "external": True,
        "host": host,
        "download": download,
        "preview_url": preview,
        "provider": provider,
        "format": kind,
        "rows": rows,
        "owner_kind": "Dataset",
        "owner": owner.label,
        "owner_description": field(owner, "description"),
        "paper": short_citation(paper) if paper and paper is not owner else "",
        "crumbs": crumbs,
        "back": url(route),
        "open": url(route, linked=linked["name"], page="file"),
        "raw": yaml.safe_dump(
            {k: v for k, v in raw.items() if v is not None},
            allow_unicode=True,
            sort_keys=False,
        ),
        **content_groups(attribute_groups(linked.get("attributes"), "File"), owner),
        "image": None,
        "text": None,
    }


@st.fragment
def viewer(items, stored, base, brand, collections):
    params = current_route()
    if params is not None:
        try:
            browse(items, stored, base, brand, params, collections)
        except (OSError, ValueError) as error:
            st.error(str(error))


def main():
    root = Path(os.environ.get("SHACL_PY_ROOT", ".")).absolute()
    base = (root if root.is_dir() else root.parent).resolve()
    try:
        brand = branding(base)
    except TypeError as error:
        st.error(str(error))
        return
    st.set_page_config(page_title=brand["page_title"], layout="wide")
    records, errors = load_records(
        root, metalad=os.environ.get("SHACL_PY_METALAD") == "1"
    )
    for error in errors:
        st.error(error)
    items = list(items_from(records, base))
    collections = [source for source in records if isinstance(source, Collection)]
    if items or collections:
        st.html(assets / "browser.css")
        with st.container(key="shacl_viewer"):
            viewer(items, file_metadata(records), base, brand, collections)
    else:
        st.info("No metadata found.")


try:
    main()
except (OSError, ValueError) as error:
    st.error(str(error))
