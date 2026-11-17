"""Optional paper-review template. Its paths and review vocabulary are local choices."""

import os
import re
from dataclasses import dataclass

from shacl_py.catalogue import record_validator
from shacl_py.files import IGNORED, local_path
from shacl_py.metadata_io import MetadataFile
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
from shacl_py.sources import initial_fields, stored_metadata
from shacl_py.study import person_names, validate_study

STATUSES = ("unreviewed", "reviewing", "useful", "excluded")


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


def review_for(graph, paper, default="unreviewed"):
    reviews = graph.setdefault("reviews", [])
    for review in reviews:
        if review["publication"] == paper["pid"]:
            return review
    review = {"publication": paper["pid"], "status": default}
    reviews.append(review)
    return review


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
            folder, single=True, graph_type="ScholarlyArticle"
        ).get(folder)
    fields = initial_fields(folder, stored, graph_type="ScholarlyArticle")
    fields.update(original.data)
    sidecar = MetadataFile.read(folder / ".studyminimeta.yaml")
    data = sidecar.data
    if data:
        data.setdefault("person", {})
        validate_study(data, sidecar.path)
    candidates = data.get("publication", [])
    known_url = fields.get("source_url")
    paper_info = (
        candidates[0]
        if len(candidates) == 1
        else next(
            (
                p
                for p in candidates
                if p.get("doi") and source_url(p["doi"]) == known_url
            ),
            {},
        )
    )
    name = paper_info.get("title") or fields["display_label"]
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
    description = fields.get("description")
    if description and not re.match(
        r"(paper id\b|.*\.studyminimeta\.yaml)", description, re.IGNORECASE
    ):
        paper.setdefault("description", description)
    review_for(graph, paper, fields.get("review_status", STATUSES[0]))
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
        if paper and folder != paper.get("local_folder"):
            paper["local_folder"] = folder
    if paper is None:
        paper = seed
        if folder:
            paper["local_folder"] = folder
        publications.append(paper)
    edit_details(paper)
    base = local_path(root, paper.get("local_folder", "."), directory=True)
    review = review_for(graph, paper)
    review["status"] = prompt(
        f"Review status ({', '.join(STATUSES)})", review["status"]
    )
    notes = prompt("Review notes (optional)", review.get("notes"))
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
                outputs = review.setdefault("outputs", [])
                if dataset["pid"] not in outputs:
                    outputs.append(dataset["pid"])
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
        stored = stored_metadata(base, graph_type="ScholarlyArticle")
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
