"""Local, read-only metadata browser."""

import os
from html import escape
from pathlib import Path
from urllib.parse import urlencode

import streamlit as st

from shacl_py.browser import (
    file_metadata,
    file_selection,
    items_from,
    neighbours,
    searchable,
    source_content,
)
from shacl_py.files import scoped_path
from shacl_py.native import MetadataSource
from shacl_py.records import load_records
from shacl_py.sources import source_url

st.set_page_config(
    page_title="shacl-py", page_icon=":material/folder_open:", layout="wide"
)
st.html("""
<style>
.stMainBlockContainer {max-width: 94rem; padding: 2rem clamp(1rem, 4vw, 3rem) 4rem;}
.stMain h1 {font-size: clamp(1.8rem, 4vw, 2.6rem); line-height: 1.16; letter-spacing: -.025em; overflow-wrap: anywhere;}
.stMain h2 {font-size: 1.25rem;}
.stMain a.catalogue-link {color: inherit; text-decoration-thickness: 1px; text-underline-offset: .2em; overflow-wrap: anywhere;}
[aria-current="page"] {font-weight: 700; border-bottom: 2px solid currentColor;}
.record-list {list-style: none; padding: 0; margin: 0;}
.record-list li {border-bottom: 1px solid #90909066; padding: .7rem 0; line-height: 1.45;}
.record-list a {font-weight: 600;}
.record-list small, .record-list .summary {display: block; margin-top: .15rem;}
.record-tabs {display: flex; flex-wrap: wrap; gap: .35rem 1.35rem; border-bottom: 1px solid #90909088;}
.record-tabs a {padding: .45rem 0; text-decoration: none;}
.record-tabs [aria-current] {border-bottom: 2px solid currentColor; font-weight: 650;}
dl.metadata {display: grid; grid-template-columns: minmax(6rem, 11rem) minmax(0, 1fr); margin: .2rem 0;}
dl.metadata dt, dl.metadata dd {margin: 0; padding: .44rem 0; border-bottom: 1px solid #90909044; overflow-wrap: anywhere; white-space: pre-line;}
dl.metadata dt {font-weight: 600; padding-right: .8rem;}
table.local-files {width: 100%; border-collapse: collapse;}
table.local-files th, table.local-files td {text-align: left; padding: .45rem .25rem; border-bottom: 1px solid #90909055;}
table.local-files th:last-child {width: 8rem;}
@media(max-width: 600px) {.stMainBlockContainer {padding-top: 2.5rem;} dl.metadata {grid-template-columns: minmax(5rem, 35%) 1fr;}}
</style>
""")
params = st.query_params.to_dict()


def anchor(label, route, *, current=False):
    href = escape("?" + urlencode(route), quote=True)
    active = ' aria-current="page"' if current else ""
    return f'<a class="catalogue-link" target="_self" href="{href}"{active}>{escape(str(label))}</a>'


def link(label, route):
    st.html(anchor(label, route))


def listing(entries, parent=None):
    rows = []
    for item, context in entries:
        route = dict(item.route)
        if parent:
            route.update(parent_record=parent.ref, parent_entry=parent.key)
        note = " · ".join(filter(None, [item.kind, context]))
        summary = item.fields.get("description") or item.fields.get("abstract")
        desc = (
            f'<span class="summary">{escape(summary)}</span>'
            if isinstance(summary, str)
            else ""
        )
        rows.append(
            f"<li>{anchor(item.label, route)}<small>{escape(note)}</small>{desc}</li>"
        )
    if rows:
        st.html('<ul class="record-list">' + "".join(rows) + "</ul>")


def metadata(fields):
    flat, nested = [], {}
    for key, value in fields.items():
        if isinstance(value, list) and value and all(isinstance(v, str) for v in value):
            value = "\n".join(value)
        if isinstance(value, (dict, list)):
            nested[key] = value
        else:
            field = escape(str(key).replace("_", " ").removeprefix("@").capitalize())
            flat.append(f"<dt>{field}</dt><dd>{escape(str(value))}</dd>")
    if flat:
        st.html('<dl class="metadata">' + "".join(flat) + "</dl>")
    if nested:
        st.json(nested, expanded=2)


def record_metadata(item, related, route):
    metadata(item.fields)
    if not item.fields:
        st.caption("This source has no dataset-level fields.")
    if related:
        st.subheader("Related records", anchor=False)
        listing(related.items(), item)
    link(f"View source metadata · {item.ref}", {**route, "view": "source"})


def files_table(rows, route):
    if not rows:
        return
    cells = []
    for row in rows:
        path = row["Relative path"]
        name = anchor(Path(path).name, {**route, "file": path})
        cells.append(
            f"<tr><td>{name}</td><td>{escape(str(Path(path).parent))}</td><td>{escape(row['Availability'])}</td></tr>"
        )
    st.html(
        '<table class="local-files"><thead><tr><th scope="col">File</th><th scope="col">Path</th>'
        '<th scope="col">Availability</th></tr></thead><tbody>'
        + "".join(cells)
        + "</tbody></table>"
    )


def file_page(item, row, route, stored):
    link(f"← Files · {item.label}", route)
    path = scoped_path(item.folder, row["Relative path"])
    st.title(path.name, anchor=False)
    metadata(
        {"Relative path": row["Relative path"], "Availability": row["Availability"]}
    )
    entries = stored.get(path, [])
    if entries:
        st.subheader("File metadata", anchor=False)
        for entry in entries:
            if extractor := entry.get("extractor_name"):
                st.caption(str(extractor))
            fields = entry.get("extracted_metadata")
            if isinstance(fields, dict):
                metadata(fields)
            else:
                st.json(fields)
        with st.expander("Extractor records"):
            st.json(entries, expanded=2)
    else:
        st.caption("No file-level metadata supplied.")
    if (
        row["Availability"] == "Available"
        and not path.is_symlink()
        and st.button("Preview text")
    ):
        with path.open("rb") as stream:
            data = stream.read(8193)
        text = data[:8192].decode("utf-8", errors="replace")
        if "\x00" in text or "\ufffd" in text.rstrip("\ufffd"):
            st.caption("A text preview is unavailable for this file.")
        else:
            st.code(text, language=None)
            if len(data) > 8192:
                st.caption("Showing the first 8 KiB.")


def browse_files(item, route, stored, excluded=None):
    directory = params.get("folder", ".")
    folder_mode = params.get("listing") == "folder"
    route = dict(route)
    if folder_mode:
        route["listing"] = "folder"
    if directory != ".":
        route["folder"] = directory
    folders, groups = file_selection(item, directory, folder_mode=folder_mode)
    if excluded:
        groups = [
            (
                label,
                [
                    row
                    for row in rows
                    if item.folder / row["Relative path"] not in excluded
                ],
            )
            for label, rows in groups
        ]
    if "file" in params:
        row = next(
            (
                row
                for _, rows in groups
                for row in rows
                if row["Relative path"] == params["file"]
            ),
            None,
        )
        if row:
            file_page(item, row, route, stored)
        else:
            link("← Files", route)
            st.warning(
                "This file is outside the current selection or is no longer listed."
            )
        return
    if (
        isinstance(item.source, MetadataSource)
        and item.source.file_records
        and item.folder.is_dir()
    ):
        base_route = {k: v for k, v in route.items() if k not in ("folder", "listing")}
        if folder_mode:
            link("Show recorded files", base_route)
        else:
            link("Browse local folder", {**base_route, "listing": "folder"})
    if directory != ".":
        up = Path(directory).parent.as_posix()
        link(f"↑ {up}", {**route, "folder": up})
    if folders:
        rows = [
            f"<li>{anchor(Path(folder).name + '/', {**route, 'folder': folder})}</li>"
            for folder in folders
        ]
        st.html('<ul class="record-list">' + "".join(rows) + "</ul>")
    for label, rows in groups:
        if rows:
            st.subheader(f"{label} ({len(rows)})", anchor=False)
            query = st.text_input(
                "Filter files", key=f"filter:{item.ref}:{item.key}:{label}"
            ).casefold()
            files_table(
                [row for row in rows if query in row["Relative path"].casefold()], route
            )
    if not folders and not any(rows for _, rows in groups):
        st.caption(
            "This folder is empty."
            if groups
            else "No local files are specified for this record."
        )


def labels(item):
    values = item.fields.get("labels") or item.fields.get("keywords") or []
    if isinstance(values, str):
        return [values]
    return [v for v in values if isinstance(v, str)] if isinstance(values, list) else []


def detail_page(item, items, stored):
    related = neighbours(item, items)
    datasets = [other for other in related if other.is_dataset]
    route = item.route
    view = params.get("view", "files" if item.is_dataset else "datasets")
    st.title(str(item.label), anchor=False)
    fields = item.fields
    header = {
        k: fields[k]
        for k in (
            "author",
            "authors",
            "journal",
            "year",
            "pid",
            "@id",
            "keywords",
            "labels",
            "local_folder",
        )
        if fields.get(k)
    }
    metadata(header)
    for field in ("doi", "source_url", "url", "sameAs"):
        if isinstance(value := fields.get(field), str):
            try:
                url = source_url(value)
            except ValueError:
                continue
            if url:
                st.link_button(value, url)
                break
    tabs = {
        "datasets": f"Datasets ({len(datasets)})",
        "abstract": "Abstract",
        "notes": "Notes",
        "files": "Files" if item.is_dataset else "Other files",
        "source": "Raw metadata",
    }
    st.html(
        '<nav class="record-tabs" aria-label="Record sections">'
        + "".join(
            anchor(label, {**route, "view": key}, current=key == view)
            for key, label in tabs.items()
        )
        + "</nav>"
    )
    if view == "datasets":
        if not datasets:
            st.caption("No related datasets.")
            return
        left, right = st.columns([1, 2])
        with left:
            query = st.text_input("Filter datasets").strip().casefold()
            shown = [d for d in datasets if query in searchable(d.fields)]
            if not shown:
                st.caption("No matching datasets.")
                return

            def dataset_route(d):
                return {
                    **route,
                    "view": "datasets",
                    "dataset_record": d.ref,
                    "dataset": d.key,
                }

            selected = next(
                (
                    d
                    for d in shown
                    if d.ref == params.get("dataset_record")
                    and d.key == params.get("dataset")
                ),
                shown[0],
            )
            for d in shown:
                st.html(anchor(d.label, dataset_route(d), current=d is selected))
        with right:
            st.subheader(str(selected.label))
            metadata(
                {
                    **{
                        k: selected.fields[k]
                        for k in ("pid", "@id", "local_folder")
                        if k in selected.fields
                    },
                    "Relationship": related[selected],
                }
            )
            with st.expander("All dataset fields"):
                metadata(selected.fields)
            browse_files(selected, dataset_route(selected), stored)
    elif view == "files":
        excluded = set()
        if item.is_publication:
            for dataset in datasets:
                _, groups = file_selection(dataset, ".", folder_mode=False)
                for _, rows in groups:
                    excluded.update(
                        dataset.folder / row["Relative path"] for row in rows
                    )
        browse_files(item, {**route, "view": "files"}, stored, excluded)
    elif view == "abstract":
        st.write(
            fields.get("abstract")
            or fields.get("description")
            or "No abstract supplied."
        )
    elif view == "notes":
        notes = [fields["notes"]] if fields.get("notes") else []
        graph = getattr(item.source, "graph", {})
        notes.extend(
            r["notes"]
            for r in graph.get("reviews", [])
            if r.get("publication") == item.key and r.get("notes")
        )
        for note in notes:
            st.write(note)
        if not notes:
            st.caption("No notes supplied.")
    else:
        record_metadata(item, related, route)
        st.json(source_content(item.source), expanded=2)


def main():
    root = Path(os.environ.get("SHACL_PY_ROOT", ".")).absolute()
    records, errors = load_records(
        root, metalad=os.environ.get("SHACL_PY_METALAD") == "1"
    )
    for error in errors:
        st.error(error)
    base = root if root.is_dir() else root.parent
    items = list(items_from(records, base.resolve()))
    item = next(
        (
            i
            for i in items
            if i.ref == params.get("record") and i.key == params.get("entry", "")
        ),
        None,
    )
    with st.sidebar:
        papers = [entry for entry in items if entry.is_publication]
        scope = papers or items
        if papers and st.toggle("Show all metadata records"):
            scope = items
        query = (
            st.text_input("Search papers" if scope is papers else "Search metadata")
            .strip()
            .casefold()
        )
        options = sorted({tag for entry in scope for tag in labels(entry)})
        tags = st.multiselect("Filter by label", options) if options else []
        shown = [
            entry
            for entry in scope
            if query in searchable([entry.label, entry.fields, entry.ref])
            and all(tag in labels(entry) for tag in tags)
        ]
        if item is None and shown and "record" not in params:
            item = next((entry for entry in shown if entry.is_publication), shown[0])
        for entry in shown:
            st.html(anchor(entry.label, entry.route, current=entry is item))
            if entry.is_publication:
                count = sum(d.is_dataset for d in neighbours(entry, items))
                st.caption(
                    " · ".join(
                        [
                            f"{count} dataset" if count == 1 else f"{count} datasets",
                            *labels(entry),
                        ]
                    )
                )
        if not shown:
            st.caption("No matching records.")
    if item:
        detail_page(item, items, file_metadata(records))
    else:
        st.info("Select a record." if items else "No metadata found.")


try:
    main()
except (OSError, ValueError) as error:
    st.error(str(error))
