"""Read-only shaclpy viewer backed by Concepts and MetaLad records."""

import base64
import json
import os
import re
import shlex
from functools import cache
from pathlib import Path

import streamlit as st
import yaml
from jinja2 import Environment, FileSystemLoader

from shacl_py.branding import branding
from shacl_py.browser import (
    dataset_keys,
    file_metadata,
    file_selection,
    items_from,
    neighbours,
    publication_key,
    searchable,
    source_content,
)
from shacl_py.files import scoped_path
from shacl_py.native import declared_title
from shacl_py.navigation import current_route, url
from shacl_py.records import load_records
from shacl_py.sources import source_url
from shacl_py.study import person_names

assets = Path(__file__).with_name("templates")
template = Environment(loader=FileSystemLoader(assets), autoescape=True).get_template(
    "browser.html"
)


FORMATS = {
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
IMAGES = {
    ".png": "image/png",
    ".jpg": "image/jpeg",
    ".jpeg": "image/jpeg",
    ".gif": "image/gif",
    ".webp": "image/webp",
}
PREVIEW_BYTES = 8192
IMAGE_BYTES = 5 * 1048576


def human_size(n):
    if n < 1024:
        return f"{n:,} B"
    if n < 1048576:
        return f"{n / 1024:.1f} KiB"
    return f"{n / 1048576:.1f} MiB"


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
        if mime := IMAGES.get(path.suffix.casefold()):
            if path.stat().st_size <= IMAGE_BYTES:
                encoded = base64.b64encode(path.read_bytes()).decode()
                preview["image"] = f"data:{mime};base64,{encoded}"
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


def short_citation(item):
    """Cite a paper as 'Surname et al. Year', falling back to its title."""
    year = field(item, "year", "datePublished")[:4]
    return " ".join(filter(None, [short_authors(item) or item.label, year]))


def labels(item):
    value = item.fields.get("labels", [])
    return [
        v for v in (value if isinstance(value, list) else [value]) if isinstance(v, str)
    ]


def browse(items, stored, base, brand, params):
    papers = [i for i in items if i.is_publication]
    datasets = [i for i in items if i.is_dataset]
    keys = dataset_keys(papers, datasets)

    def key_for(i):
        return keys[i] if i.is_dataset else publication_key(i)

    years = {}
    for paper in papers:
        if year := field(paper, "year", "datePublished"):
            years.setdefault(key_for(paper), set()).add(
                year[:4] if year[:4].isdigit() else year
            )

    def publication_year(item):
        year = field(item, "year", "datePublished")
        if year:
            return year[:4] if year[:4].isdigit() else year
        matches = years.get(key_for(item), set())
        return next(iter(matches)) if len(matches) == 1 else ""

    others = [i for i in items if i not in papers and i not in datasets]
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
    default = next(
        (name for name, group in sections.items() if selected_item in group),
        next(iter(sections)),
    )
    section = next(
        (name for name in sections if name.lower() == params.get("section")), default
    )
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

    def linked(i, group):
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

    q = params.get("q", "").strip().casefold()
    tag = params.get("tag", "All")
    sidebar_route = {
        "section": section.lower(),
        "q": q,
        "filter": params.get("filter", ""),
    }
    options = [
        "All",
        *sorted(
            {v for i in scope for v in (roles(i) if global_ds else labels(i))}
            - {"All", "Not all local"}
        ),
    ]
    if global_ds:
        options.append("Not all local")
    shown = []
    for i in scope:
        ds = linked(i, datasets)
        if (
            q
            and q not in searchable([i.ref, i.fields])
            and not any(q in searchable(d.fields) or file_matches(d, q) for d in ds)
            and not file_matches(i, q)
        ):
            continue
        if params.get("filter", "").casefold() not in searchable(
            [i.ref, i.fields, author_line(i)]
        ):
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
        count = file_count(i) if global_ds else len(ds)
        shown.append(
            {
                "item": i,
                "href": url(sidebar_route | i.route, tag=tag),
                "authors": short_citation(linked(i, papers)[0])
                if global_ds and linked(i, papers)
                else "" if global_ds else sidebar_author(i),
                "venue": field(i, "format", "encodingFormat", "media_type")
                if global_ds
                else field(i, "venue", "journal"),
                "year": "" if global_ds else publication_year(i),
                "count": f"{count} {'file' if global_ds else 'dataset'}{'s' if count != 1 else ''}",
                "tags": labels(i),
            }
        )
    if section in ("Papers", "Datasets"):
        unique = {}
        for row in shown:
            key = key_for(row["item"])
            if key not in unique or row["item"] is selected_item:
                unique[key] = row
        shown = list(unique.values())
    item = (
        selected_item
        if any(r["item"] is selected_item for r in shown)
        else next((r["item"] for r in shown), None)
    )
    nav = [
        (
            name,
            url({}, section=name.lower(), q=q),
            len({key_for(i) for i in group}),
            name == section,
        )
        for name, group in sections.items()
    ]
    context = {
        "brand": brand,
        "params": params,
        "section": section,
        "url": url,
        "shown": shown,
        "nav": nav,
        "global_ds": global_ds,
        "options": options,
        "active_filter": tag,
        "sidebar_route": sidebar_route,
        "item": item,
    }

    if not item:
        st.html(template.render(context))
        return
    item_route = sidebar_route | item.route | {"tag": tag}
    ds = linked(item, datasets)
    parents = list({publication_key(p): p for p in linked(item, papers)}.values())
    tabs = (
        [("files", "Files", file_count(item)), ("paper", "Paper", None)]
        if global_ds
        else [
            ("datasets", "Datasets", len(ds)),
            ("abstract", "Abstract", None),
            ("notes", "Notes", None),
            ("files", "Other files", None),
        ]
    )
    tabs.append(("source", "Raw metadata", None))
    view = params.get("view", tabs[0][0])
    if view not in {k for k, _, _ in tabs}:
        view = tabs[0][0]
    dsrows = []
    for d in ds:
        if params.get("dsfilter", "").casefold() in searchable(d.fields):
            dsrows.append(
                {
                    "item": d,
                    "count": file_count(d),
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
    directory = params.get("folder", ".")
    folders, files = (
        listing(owner, directory)
        if owner and view in ("datasets", "files")
        else ([], {})
    )
    if item.is_publication and view == "files":
        excluded = {d.folder / path for d in ds for path in listing(d)[1]}
        files = {p: r for p, r in files.items() if item.folder / p not in excluded}
    up = url(route, folder=str(Path(directory).parent))
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
            }
        )
    if owner and directory == "." and view in ("datasets", "files"):
        rows.extend(
            {
                "name": f["name"],
                "path": f["name"],
                "href": f["url"],
                "preview": f.get("preview_url"),
                "provider": f.get("provider_url"),
                "parent": "",
                "size": "",
                "local": False,
            }
            for f in owner.linked_files
        )
    dataset_owner = item if global_ds else selected if view == "datasets" else None
    try:
        dataset_url = source_url(field(dataset_owner, "source_url", "url"))
    except ValueError:
        dataset_url = None
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
    context.update(
        item_route=item_route,
        view=view,
        tabs=tabs,
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
        ds_folder=local_folder(selected),
        role=", ".join(dict.fromkeys(roles(item)))
        if global_ds
        else related(item).get(selected, ""),
        paper_rows=[
            {
                "href": url(p.route, dataset=item.key, dataset_record=item.ref),
                "short": short_citation(p),
                "title": p.label,
            }
            for p in parents
        ],
        availability=f"{sum(f['local'] for f in rows)} of {len(rows)} files local",
        format=field(owner, "format", "encodingFormat", "media_type"),
        parents=parents,
        route=route,
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
    if "file" in params and owner:
        if row := files.get(params["file"]):
            paper = item if item.is_publication else next(iter(parents), None)
            context["fp"] = file_panel(
                owner, row, route, stored, base, paper, page=params.get("page")
            )
        else:
            st.warning("This file is outside the current selection.")
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
    if entries := stored.get(path):
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
        "owner_kind": "Dataset" if owner.is_dataset else "Paper"
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
        **(file_preview(path, base) if local else {"image": None, "text": None}),
    }


@st.fragment
def viewer(items, stored, base, brand):
    params = current_route()
    if params is not None:
        try:
            browse(items, stored, base, brand, params)
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
    if items:
        st.html(assets / "browser.css")
        with st.container(key="shacl_viewer"):
            viewer(items, file_metadata(records), base, brand)
    else:
        st.info("No metadata found.")


try:
    main()
except (OSError, ValueError) as error:
    st.error(str(error))
