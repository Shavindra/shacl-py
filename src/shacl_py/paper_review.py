"""Optional paper-review template. Its paths and review vocabulary are local choices."""

import os
from dataclasses import dataclass
from pathlib import Path

from shacl_py.catalogue import record_validator, validate_catalogue
from shacl_py.files import IGNORED, local_path
from shacl_py.metadata_io import MetadataFile, save_metadata
from shacl_py.prompts import (
    add_group,
    choose,
    edit_dataset,
    edit_details,
    edit_groups,
    from_token,
    list_options,
    lookup,
    new_entity,
    prompt,
    set_dataset_location,
    source_url,
)
from shacl_py.sources import METADATA_FILES, initial_fields, stored_metadata
from shacl_py.study import person_names, publication_info, read_study

STATUSES = ("unreviewed", "reviewing", "useful", "excluded")
PAPER_SOURCES = METADATA_FILES - {"project.json"}


@dataclass(frozen=True)
class ReviewLayout:
    collection: str = "research/papers"
    notes: str = "README.md"
    notebooks: str = "notebooks"
    raw: str = "data/raw"
    outputs: str = "data/output"
    shared: tuple = (
        ("Shared code", "src"),
        ("Scripts", "scripts"),
        ("Catalogue", "research/catalogue"),
        ("Comparisons", "research/comparisons"),
    )

    @property
    def paper_files(self):
        return (
            ("Review notes", self.notes),
            ("Notebooks", self.notebooks),
            ("Raw data", self.raw),
            ("Analysis outputs", self.outputs),
        )


def suggested_groups(entity, base, suggestions):
    if "file_groups" in entity:
        return
    for label, name in suggestions:
        if os.path.lexists(base / name):
            add_group(entity, label, [name])


def append_link(paper, dataset, role):
    links = paper.setdefault("dataset_links", [])
    link = {"dataset": dataset["pid"], "role": role}
    if role != "related":
        links[:] = [
            item
            for item in links
            if item != {"dataset": dataset["pid"], "role": "related"}
        ]
    if link not in links:
        links.append(link)


def add_datasets(root, selector, entries, linked_files=()):
    document = MetadataFile.read(root / "metadata.yaml")
    graph = document.data.get("catalogue")
    if not graph:
        raise ValueError(
            "No project catalogue found. Run shacl-py setup --template paper-review first."
        )
    validate_catalogue(graph, root)
    publications = graph.get("publications", [])
    matches = [
        p for p in publications if p.get("local_folder") == Path(selector).as_posix()
    ]
    if len(matches) > 1:
        raise ValueError("Several papers use this folder. Select a paper by PID.")
    paper = matches[0] if matches else lookup(publications, selector)
    if paper is None and selector.startswith("10."):
        paper = lookup(publications, source_url(selector))
    if paper is None:
        raise ValueError(f"Unknown paper: {selector}")
    datasets = graph.setdefault("datasets", [])
    for name, selection in entries:
        if selection.startswith(("http://", "https://")):
            location = source_url(selection)
            dataset = next(
                (d for d in datasets if d.get("source_url") == location), None
            )
            if dataset is None:
                dataset = new_entity(name, location)
                datasets.append(dataset)
        else:
            path = local_path(root, selection)
            base = path if path.is_dir() else path.parent
            relative = base.relative_to(root).as_posix()
            member = path.relative_to(base).as_posix()
            matches = [
                d
                for d in datasets
                if d.get("title") == name
                and d.get("local_folder") == relative
                and any(
                    g.get("label") == "Data files" and member in g["paths"]
                    for g in d.get("file_groups", [])
                )
            ]
            if len(matches) > 1:
                raise ValueError(
                    f"Multiple dataset records match {name!r} at {selection}"
                )
            if matches:
                dataset = matches[0]
            else:
                dataset = new_entity(name)
                set_dataset_location(dataset, root, selection)
                datasets.append(dataset)
        if not any(
            link["dataset"] == dataset["pid"] for link in paper.get("dataset_links", [])
        ):
            append_link(paper, dataset, "related")
    for values in linked_files:
        if not 3 <= len(values) <= 5:
            raise ValueError(
                "--linked-file expects DATASET_URL FILENAME DOWNLOAD_URL [PREVIEW_URL [PROVIDER_URL]]"
            )
        dataset_url, filename, file_url, *optional = values
        matches = [
            d
            for d in datasets
            if d.get("source_url") == source_url(dataset_url)
            and any(
                link["dataset"] == d["pid"] for link in paper.get("dataset_links", [])
            )
        ]
        if len(matches) != 1:
            raise ValueError(
                f"Expected one dataset linked to this paper at {dataset_url}"
            )
        files = matches[0].setdefault("linked_files", [])
        entry = {"name": filename, "url": source_url(file_url)}
        existing = next(
            (f for f in files if f["name"] == filename and f["url"] == entry["url"]),
            None,
        )
        if existing is None:
            files.append(entry)
            existing = entry
        for key, value in zip(("preview_url", "provider_url"), optional):
            existing[key] = source_url(value)
    validate_catalogue(graph, root)
    changed = save_metadata(document)
    print(f"{'Updated' if changed else 'Kept'} {document.path}")


def import_paper(graph, root, folder, layout, stored=None):
    """Import a chosen ordinary folder. Original paper descriptors stay untouched."""
    relative = folder.relative_to(root).as_posix()
    publications = graph.setdefault("publications", [])
    for item in publications:
        if item.get("local_folder") == relative:
            return item
    original = MetadataFile.read(folder / "metadata.yaml")
    if original.data:
        problem = next(record_validator().iter_errors(original.data), None)
        if problem:
            raise ValueError(f"{original.path}: {problem.json_path}: {problem.message}")
    if original.data and (
        existing := next(
            (p for p in publications if p["pid"] == original.data["pid"]), None
        )
    ):
        return existing
    if stored is None:
        stored = stored_metadata(
            folder,
            single=True,
            graph_type="ScholarlyArticle",
            descriptors=PAPER_SOURCES,
        ).get(folder)
    fields = initial_fields(
        folder, stored, graph_type="ScholarlyArticle", descriptors=("paper.json",)
    )
    fields.update(original.data)
    data = read_study(folder / ".studyminimeta.yaml")
    known_url = fields.get("source_url")
    paper_info = publication_info(data, known_url)
    name = paper_info.get("title") or fields.get("display_label")
    url = source_url(paper_info.get("doi") or known_url)
    paper = next(
        (
            p
            for p in publications
            if p["pid"] == fields["pid"] or (url and p.get("source_url") == url)
        ),
        None,
    )
    if paper is None:
        paper = new_entity(name, url, fields["pid"])
        publications.append(paper)
    # Older records may point at a file base distinct from their metadata folder.
    file_base = local_path(folder, fields.get("local_folder", "."), directory=True)
    paper.setdefault("local_folder", file_base.relative_to(root).as_posix())
    suggested_groups(paper, file_base, layout.paper_files)
    people = data.get("person", {})
    if authors := person_names(people, paper_info.get("author", [])):
        paper.setdefault("author_names", authors)
    primary = fields.get("primary_author")
    if not primary and (key := paper_info.get("primary_author")):
        primary = person_names(people, [key])[0]
    if primary:
        paper.setdefault("primary_author", primary)
    highlighted = fields.get("highlighted", paper_info.get("highlighted"))
    if isinstance(highlighted, bool):
        paper.setdefault("highlighted", highlighted)
    if description := fields.get("description"):
        paper.setdefault("description", description)
    if status := fields.get("review_status"):
        reviews = graph.setdefault("reviews", [])
        if not any(r["publication"] == paper["pid"] for r in reviews):
            reviews.append({"publication": paper["pid"], "status": status})
    dataset_info = data.get("dataset", {})
    if dataset_info.get("name"):
        location = dataset_info.get("location")
        dataset_url = (
            source_url(location)
            if location and location.startswith(("http://", "https://"))
            else None
        )
        datasets = graph.setdefault("datasets", [])
        dataset = next(
            (d for d in datasets if dataset_url and d.get("source_url") == dataset_url),
            None,
        )
        if dataset is None:
            dataset = new_entity(dataset_info["name"], dataset_url)
            if authors := person_names(people, dataset_info.get("author", [])):
                dataset["author_names"] = authors
            if dataset_info.get("description"):
                dataset["description"] = dataset_info["description"]
            if (file_base / layout.raw).is_dir():
                set_dataset_location(
                    dataset, root, (file_base / layout.raw).relative_to(root).as_posix()
                )
            datasets.append(dataset)
        if "highlighted" in dataset_info:
            dataset.setdefault("highlighted", dataset_info["highlighted"])
        append_link(paper, dataset, "related")
    return paper


def edit_paper(graph, root, token, layout):
    publications = graph.setdefault("publications", [])
    seed = from_token(token)
    paper = lookup(publications, seed.get("source_url", token))
    folder = prompt(
        "Paper folder relative to project (optional)",
        paper.get("local_folder") if paper else "",
    )
    if folder:
        base = local_path(root, folder, directory=True)
        if (
            paper is None
            and base != root
            and any(
                (base / n).is_file() for n in ("metadata.yaml", ".studyminimeta.yaml")
            )
        ):
            paper = import_paper(graph, root, base, layout)
            for field in ("title", "source_url"):
                if field in seed:
                    paper.setdefault(field, seed[field])
        if paper and folder != paper.get("local_folder"):
            paper["local_folder"] = folder
    if paper is None:
        paper = seed
        if folder:
            paper["local_folder"] = folder
        publications.append(paper)
    edit_details(paper)
    base = local_path(root, paper.get("local_folder", "."), directory=True)
    review = next(
        (r for r in graph.get("reviews", []) if r["publication"] == paper["pid"]), None
    )
    current = review or {}
    status = prompt(
        f"Review status ({', '.join(STATUSES)}, optional)", current.get("status")
    )
    notes = prompt("Review notes (optional)", current.get("notes"))
    if status or notes:
        if review is None:
            review = {"publication": paper["pid"]}
            graph.setdefault("reviews", []).append(review)
        if status:
            review["status"] = status
        if notes:
            review["notes"] = notes
    if folder:
        suggested_groups(paper, base, layout.paper_files)
    print("Paper files")
    edit_groups(paper, base)
    for derived in (False, True):
        while True:
            list_options(graph.get("datasets", []))
            label = (
                "Derived dataset to register"
                if derived
                else "Dataset this paper describes or reuses"
            )
            token = prompt(f"{label} (number, title or DOI; Enter to skip)")
            if not token:
                break
            directory = base / (layout.outputs if derived else layout.raw)
            default_path = (
                directory.relative_to(root).as_posix()
                if folder and directory.is_dir()
                else ""
            )
            dataset = edit_dataset(
                graph, root, token, default_path=default_path, derived=derived
            )
            if derived:
                append_link(paper, dataset, "output")
            else:
                role = choose(
                    "Relationship (describes/reuses)",
                    ("describes", "reuses"),
                    "describes",
                )
                append_link(paper, dataset, role)


def configure_review(graph, root, collection, interactive, layout):
    project = graph["project"]
    suggested_groups(project, root / project.get("local_folder", "."), layout.shared)
    if collection is None and interactive:
        default = layout.collection if (root / layout.collection).is_dir() else ""
        collection = prompt(
            "Import existing paper folders from (Enter to skip)", default
        )
    if collection:
        base = local_path(root, collection, directory=True)
        stored = stored_metadata(
            base, graph_type="ScholarlyArticle", descriptors=PAPER_SOURCES
        )
        for folder in sorted(base.iterdir()):
            if (
                folder.name not in IGNORED
                and not folder.name.startswith(".")
                and not folder.is_symlink()
                and folder.is_dir()
            ):
                import_paper(graph, root, folder, layout, stored.get(folder, {}))
    if interactive:
        while True:
            list_options(graph.get("publications", []))
            token = prompt(
                "Paper to add or review (number, title or DOI; Enter to finish)"
            )
            if not token:
                break
            edit_paper(graph, root, token, layout)
