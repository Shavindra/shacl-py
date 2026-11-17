"""Terminal prompts shared by project setup and the optional review workflow."""

import os
import re
from uuid import uuid4

from shacl_py.catalogue import title
from shacl_py.files import local_path
from shacl_py.sources import source_url

DOC_FILES = (
    "README.md",
    "README",
    "LICENSE",
    "LICENSE.md",
    "CITATION.cff",
    "dataset_description.json",
    "metadata.yaml",
    ".studyminimeta.yaml",
)


def prompt(label, default=""):
    default = default or ""
    answer = input(f"{label}{f' [{default}]' if default else ''}: ").strip()
    return answer or default


def choose(label, choices, default):
    while True:
        value = prompt(label, default)
        if value in choices:
            return value
        print(f"Choose one of {', '.join(choices)}.")


def add_group(entity, label, paths, section="files"):
    if not paths:
        return
    group = {"label": label, "paths": paths}
    if section != "files":
        group["section"] = section
    groups = entity.setdefault("file_groups", [])
    for old in groups:
        if old["label"] == label:
            old.update(group)
            return
    groups.append(group)


def edit_groups(entity, base):
    groups = entity.setdefault("file_groups", [])
    for group in groups:
        print(f"  {group['label']}: {', '.join(group['paths'])}")
    while label := prompt("File group to add or change (Enter to continue)"):
        old = next((g for g in groups if g["label"] == label), None)
        path = prompt(f"File or folder under {base.name} (- removes the group)")
        if path == "-" and old:
            groups.remove(old)
        elif path and path != "-":
            paths = [path]
            while path := prompt("Another path in this group (Enter to finish)"):
                paths.append(path)
            for value in paths:
                local_path(base, value)
            section = old.get("section", "files") if old else "files"
            section = choose(
                "Group section (files/documentation)",
                ("files", "documentation"),
                section,
            )
            if old:
                old["section"] = section
            add_group(entity, label, paths, section)


def set_dataset_location(dataset, root, selection):
    path = local_path(root, selection)
    base = path if path.is_dir() else path.parent
    dataset["local_folder"] = base.relative_to(root).as_posix()
    add_group(dataset, "Data files", [path.relative_to(base).as_posix()])
    docs = [name for name in DOC_FILES if os.path.lexists(base / name)]
    if docs:
        add_group(dataset, "Documentation", docs, "documentation")
    else:
        dataset["file_groups"] = [
            g for g in dataset["file_groups"] if g["label"] != "Documentation"
        ]


def lookup(items, token):
    """An explicit selection can use the displayed number, ID, title or source."""
    if token.isdecimal() and 0 < int(token) <= len(items):
        return items[int(token) - 1]
    matches = [
        item
        for item in items
        if token in (item["pid"], item.get("source_url"), title(item))
    ]
    if len(matches) > 1:
        raise ValueError(f"Several records match {token!r}. Select a number or ID.")
    return matches[0] if matches else None


def list_options(items):
    for i, item in enumerate(items, 1):
        print(f"  {i}. {title(item)} ({item['pid']})")


def new_entity(name, url=None, pid=None):
    entity = {"pid": pid or f"urn:uuid:{uuid4()}"}
    if name:
        entity["title"] = name
    if url:
        entity["source_url"] = url
    return entity


def edit_details(entity):
    if name := prompt("Title", entity.get("title")):
        entity["title"] = name
    url = prompt("DOI or source URL (optional)", entity.get("source_url"))
    if url:
        entity["source_url"] = source_url(url)
    description = prompt("Description (optional)", entity.get("description"))
    if description:
        entity["description"] = description


def from_token(token):
    if token.startswith(("http://", "https://")) or re.match(r"10\.\d{4,9}/", token):
        return new_entity(None, source_url(token))
    return new_entity(token)


def edit_dataset(graph, root, token, *, default_path="", derived=False):
    datasets = graph.setdefault("datasets", [])
    seed = from_token(token)
    dataset = lookup(datasets, seed.get("source_url", token))
    if dataset is None:
        dataset = seed
        edit_details(dataset)
        url = dataset.get("source_url")
        existing = next(
            (d for d in datasets if url and d.get("source_url") == url), None
        )
        if existing:
            dataset = existing
        else:
            datasets.append(dataset)
    previous = dataset.get("local_folder", "")
    selection = prompt(
        "Local dataset file or folder, relative to project (- for online only)",
        previous or default_path,
    )
    if selection == "-":
        dataset.pop("local_folder", None)
        dataset.pop("file_groups", None)
    elif selection and selection != previous:
        set_dataset_location(dataset, root, selection)
    if (
        dataset.get("local_folder")
        and choose("Customise dataset file groups? (y/n)", ("y", "n"), "n") == "y"
    ):
        edit_groups(dataset, local_path(root, dataset["local_folder"], directory=True))
    if derived:
        sources = [d for d in datasets if d is not dataset]
        list_options(sources)
        while value := prompt("Source dataset number or ID (Enter to finish)"):
            source = lookup(sources, value)
            if source is None:
                raise ValueError(f"Unknown source dataset {value!r}")
            ids = dataset.setdefault("source_datasets", [])
            if source["pid"] not in ids:
                ids.append(source["pid"])
        notebook = prompt(
            "Notebook used, relative to project (optional)",
            dataset.get("notebook_path"),
        )
        if notebook:
            dataset["notebook_path"] = notebook
    return dataset
