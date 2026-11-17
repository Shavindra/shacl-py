"""Interactive setup for the installed CLI. All writes occur after validation."""

from shacl_py.catalogue import (
    record_validator,
    title,
    validate_catalogue,
    validate_structure,
)
from shacl_py.files import local_path
from shacl_py.metadata_io import MetadataFile, save_metadata
from shacl_py.prompts import add_group, edit_dataset, edit_groups, list_options, prompt
from shacl_py.sources import initial_fields, stored_metadata
from shacl_py.study import dataset_root, validate_study


def setup_project(args, review_layout=None):
    root = args.path.resolve()
    if not root.is_dir():
        raise ValueError(f"{root}: expected an existing project directory")
    is_review = args.template == "paper-review"
    if args.papers_folder is not None and not is_review:
        raise ValueError("--papers-folder requires --template paper-review")
    meta = MetadataFile.read(root / "metadata.yaml")
    host = dataset_root(root)
    study = MetadataFile.read(host / ".studyminimeta.yaml")
    study.data.setdefault("person", {})
    validate_study(study.data, study.path)
    legacy = {k: v for k, v in meta.data.items() if k != "catalogue"}
    if legacy:
        problem = next(record_validator().iter_errors(legacy), None)
        if problem:
            raise ValueError(f"{meta.path}: {problem.json_path}: {problem.message}")
    initial = "catalogue" not in meta.data
    if initial:
        hint = initial_fields(root, stored_metadata(root, single=True).get(root))
        hint.update(legacy)
        dataset_info = study.data.get("dataset", {}) if host == root else {}
        study_info = study.data.get("study", {}) if host == root else {}
        name = (
            study_info.get("name") or dataset_info.get("name") or hint["display_label"]
        )
        project = {"pid": hint["pid"], "title": name}
        description = (
            study_info.get("purpose")
            or dataset_info.get("description")
            or hint.get("description")
        )
        if description:
            project["description"] = description
        if hint.get("source_url"):
            project["source_url"] = hint["source_url"]
        meta.data["catalogue"] = {"project": project}
    graph = meta.data["catalogue"]
    if not isinstance(graph, dict) or not isinstance(graph.get("project"), dict):
        raise TypeError(f"{meta.path}: catalogue.project must be a mapping")
    if not initial:
        try:
            validate_structure(graph)
        except ValueError as error:
            raise ValueError(f"{meta.path}: {error}") from error
    project = graph["project"]
    old_title = title(project)
    old_description = project.get("description", "")
    interactive = not args.no_input
    new_title = (
        args.title
        if args.title is not None
        else (prompt("Project title", old_title) if interactive else old_title)
    )
    if new_title != old_title:
        project["title"] = new_title
    description = (
        args.description
        if args.description is not None
        else (
            prompt("Project description", old_description)
            if interactive
            else old_description
        )
    )
    if description != old_description:
        project["description"] = description

    base = local_path(root, project.get("local_folder", "."), directory=True)
    if args.data_folder:
        for folder in args.data_folder:
            local_path(base, folder, directory=True)
        add_group(project, "Data files", args.data_folder)
    elif interactive and not is_review and not project.get("file_groups"):
        folder = prompt(
            "Data folder (Enter to skip)", "data" if (base / "data").is_dir() else ""
        )
        if folder:
            local_path(base, folder, directory=True)
            add_group(project, "Data files", [folder])
    if is_review:
        from shacl_py.paper_review import ReviewLayout, configure_review

        configure_review(
            graph,
            root,
            args.papers_folder,
            interactive,
            review_layout or ReviewLayout(),
        )
    elif interactive:
        while True:
            list_options(graph.get("datasets", []))
            token = prompt(
                "Dataset to add or edit (number, title or DOI; Enter to finish)"
            )
            if not token:
                break
            edit_dataset(graph, root, token)
    if interactive:
        print("Project files")
        edit_groups(project, base)

    # StudyMiniMeta describes the containing dataset. A nested project's details
    # cannot stand in for its enclosing DataLad dataset.
    host_title = title(project) if host == root else host.name
    for section in ("study", "dataset"):
        values = study.data.setdefault(section, {})
        if "name" not in values or (host == root and values["name"] == old_title):
            values["name"] = host_title
    if host == root and description:
        for section, field in (("dataset", "description"), ("study", "purpose")):
            values = study.data[section]
            if field not in values or values[field] == old_description:
                values[field] = description
    try:
        validate_catalogue(graph, root)
    except ValueError as error:
        raise ValueError(f"{meta.path}: {error}") from error
    validate_study(study.data, study.path)
    changed = save_metadata(meta, study)
    for doc in (meta, study):
        action = "Kept"
        if doc.path in changed:
            action = "Created" if doc.original is None else "Updated"
        print(f"{action} {doc.path}")
    print("Validated project and study metadata.")
