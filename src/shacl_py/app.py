"""Local, read-only catalogue navigation."""

import os
from pathlib import Path
from urllib.parse import quote

import streamlit as st

from shacl_py.catalogue import Catalogue, title
from shacl_py.files import grouped_files
from shacl_py.native import MetadataSource, declared_title
from shacl_py.records import load_records, project_files
from shacl_py.sources import source_url

st.set_page_config(
    page_title="shacl-py", page_icon=":material/folder_open:", layout="wide"
)
st.html("""
<style>
.stMainBlockContainer {max-width: 68rem; padding: 3.5rem clamp(1rem, 4vw, 3rem) 4rem;}
.stMain h1, .stMain h2, .stMain h3 {letter-spacing: -.025em; text-wrap: pretty;}
.stMain h1 {font-size: clamp(1.9rem, 5vw, 2.7rem); line-height: 1.15;}
.stMain [data-baseweb="tab-list"] {gap: 1.4rem;}
.stMain [data-baseweb="tab"] {font-weight: 600;}
.stMain .stButton button {min-height: 2.6rem;}
@media(max-width: 600px) {.stMainBlockContainer {padding-top: 3rem;}}
</style>
""")
root = Path(os.environ.get("SHACL_PY_ROOT", "."))


def go(**params):
    st.query_params.from_dict(params)
    st.rerun()


def back(label, **params):
    if st.button(label, icon=":material/arrow_back:", type="tertiary", key="back"):
        go(**params)


def matches(entity, query, extra=""):
    text = " ".join(
        (
            title(entity),
            entity.get("description", ""),
            " ".join(entity.get("author_names", [])),
            entity.get("source_url", ""),
            extra,
        )
    )
    return query.casefold().strip() in text.casefold()


def description(entity):
    if entity.get("description"):
        st.write(entity["description"])


def details(entity):
    st.title(title(entity), anchor=False)
    description(entity)
    if entity.get("author_names"):
        st.caption(", ".join(entity["author_names"]))
    if entity.get("source_url"):
        st.link_button(
            "DOI / source", entity["source_url"], icon=":material/open_in_new:"
        )


def metadata_panel(entity):
    with st.expander("Metadata"):
        st.json(entity, expanded=False)


def table(rows):
    if rows:
        st.dataframe(
            rows,
            hide_index=True,
            width="stretch",
            height=min(390, 36 + 35 * len(rows)),
            column_config={"Availability": st.column_config.TextColumn(width="small")},
        )
    else:
        st.caption("No files in this selection.")


def files_for(record, entity, *, dataset=False):
    groups = grouped_files(record.folder, entity)
    descriptions = {
        row["Relative path"]
        for group, rows in groups
        if group.get("section") == "documentation"
        for row in rows
    }

    def show(section):
        selections = [
            (g, rows)
            for g, rows in groups
            if not dataset or g.get("section", "files") == section
        ]
        if not selections and section == "files":
            st.caption("No local files selected.")
        for group, rows in selections:
            st.subheader(group["label"], anchor=False)
            if dataset and section == "files":
                rows = [r for r in rows if r["Relative path"] not in descriptions]
            table(rows)

    if dataset:
        data, docs = st.tabs(["Data files", "Documentation and metadata"])
        with data:
            show("files")
        with docs:
            show("documentation")
            metadata_panel(entity)
    else:
        show("files")


def entity_row(entity, kind, project_id, key, context="", parent_paper=None):
    with st.container(border=True):
        if st.button(
            title(entity),
            key=key,
            type="tertiary",
            icon=":material/article:" if kind == "paper" else ":material/database:",
        ):
            params = {"project": project_id, kind: entity["pid"]}
            if parent_paper:
                params["from_paper"] = parent_paper
            go(**params)
        if context:
            st.caption(context)
        description(entity)


def paper_datasets(paper, review):
    for link in paper.get("dataset_links", []):
        yield link["dataset"], link["role"].capitalize()
    for output in review.get("outputs", []):
        yield output, "Derived during this review"


def linked_project(record, has_others):
    graph = record.graph
    project = graph["project"]
    pid = project["pid"]
    papers = {p["pid"]: p for p in graph.get("publications", [])}
    datasets = {d["pid"]: d for d in graph.get("datasets", [])}
    reviews = {r["publication"]: r for r in graph.get("reviews", [])}
    papers_by_dataset = {}
    for key, publication in papers.items():
        for target, role in paper_datasets(publication, reviews.get(key, {})):
            papers_by_dataset.setdefault(target, {}).setdefault(key, []).append(role)
    paper_id = st.query_params.get("paper")
    dataset_id = st.query_params.get("dataset")
    parent = st.query_params.get("from_paper")
    if dataset_id and parent in papers:
        back(title(papers[parent]), project=pid, paper=parent)
    elif paper_id or dataset_id:
        back(title(project), project=pid)
    elif has_others:
        back("All projects")
    if paper_id:
        paper = papers.get(paper_id)
        if paper is None:
            st.warning("Paper not found.")
            return
        details(paper)
        review = reviews.get(paper_id, {})
        if review:
            st.caption(f"Review status · {review['status']}")
        if review.get("notes"):
            st.write(review["notes"])
        files, linked = st.tabs(["Files", "Datasets"])
        with files:
            files_for(record, paper)
            metadata_panel(paper)
        with linked:
            connections = list(paper_datasets(paper, review))
            if not connections:
                st.caption("No linked datasets.")
            for i, (target, role) in enumerate(connections):
                entity_row(
                    datasets[target],
                    "dataset",
                    pid,
                    f"paper-dataset-{i}",
                    role,
                    paper_id,
                )
    elif dataset_id:
        dataset = datasets.get(dataset_id)
        if dataset is None:
            st.warning("Dataset not found.")
            return
        details(dataset)
        sources = dataset.get("source_datasets", [])
        if sources:
            st.subheader("Derived from", anchor=False)
            for i, source in enumerate(sources):
                entity_row(datasets[source], "dataset", pid, f"source-{i}")
        if dataset.get("notebook_path"):
            st.caption("Analysis notebook")
            st.code(dataset["notebook_path"], language=None)
        linked_papers = papers_by_dataset.get(dataset_id, {})
        if linked_papers:
            with st.expander(f"Linked papers ({len(linked_papers)})"):
                for key, roles in linked_papers.items():
                    entity_row(
                        papers[key],
                        "paper",
                        pid,
                        f"dataset-paper-{key}",
                        ", ".join(roles),
                    )
        files_for(record, dataset, dataset=True)
    else:
        details(project)
        # A single-project root opens directly on its records.
        names = (
            ["Papers", "Datasets", "Files"]
            if papers or reviews
            else ["Datasets", "Files"]
        )
        tabs = dict(zip(names, st.tabs(names), strict=True))
        if "Papers" in tabs:
            with tabs["Papers"]:
                query = st.text_input("Search papers")
                shown = 0
                for key, paper in papers.items():
                    status = reviews.get(key, {}).get("status", "")
                    if matches(paper, query, status):
                        entity_row(paper, "paper", pid, f"publication-{key}", status)
                        shown += 1
                if not shown:
                    st.caption("No matching papers.")
        with tabs["Datasets"]:
            if datasets:
                query = st.text_input("Search datasets")
                shown = 0
                for key, dataset in datasets.items():
                    paper_titles = ", ".join(
                        title(papers[p]) for p in papers_by_dataset.get(key, {})
                    )
                    if matches(dataset, query, paper_titles):
                        context = (
                            f"Linked papers · {paper_titles}" if paper_titles else ""
                        )
                        entity_row(dataset, "dataset", pid, f"dataset-{key}", context)
                        shown += 1
                if not shown:
                    st.caption("No matching datasets.")
            else:
                st.caption("No datasets registered.")
        with tabs["Files"]:
            files_for(record, project)
            metadata_panel(project)


def legacy_project(record):
    back("All projects")
    entity = record.data
    st.header(title(entity))
    description(entity)
    st.caption(entity["review_status"])
    if entity.get("source_url"):
        st.link_button("DOI / source", entity["source_url"])
    data_rows, docs_rows = project_files(record)
    data_tab, docs_tab = st.tabs(["Data files", "Dataset"])
    with data_tab:
        table(data_rows)
    with docs_tab:
        table(docs_rows)
        metadata_panel(entity)


def source_page(record, has_others):
    if has_others:
        back("All records")
    st.title(record.label, anchor=False)
    if record.label != record.reference:
        st.caption(record.reference)
    for kind, fields in record.entries:
        label = declared_title(fields)
        st.subheader(kind, anchor=False)
        st.write(label or "Title unavailable")
        if (
            summary := fields.get("description")
            or fields.get("purpose")
            or fields.get("abstract")
        ):
            st.write(summary)
        link = (
            fields.get("doi")
            or fields.get("source_url")
            or fields.get("sameAs")
            or fields.get("url")
        )
        if isinstance(link, str) and link:
            try:
                href = source_url(link)
            except ValueError:
                st.write(link)
            else:
                href = quote(href, safe=":/?#[]@!$&'()*+,;=%")
                st.markdown(f"<{href}>")
    with st.expander("Source metadata"):
        st.json(record.content)


def home(records):
    has_sources = not records or any(isinstance(r, MetadataSource) for r in records)
    st.title("Metadata" if has_sources else "Projects", anchor=False)
    query = st.text_input("Search metadata" if has_sources else "Search projects")
    shown = 0
    for record in records:
        if isinstance(record, MetadataSource):
            if record.matches(query):
                shown += 1
                with st.container(border=True):
                    st.subheader(record.label, anchor=False)
                    if record.label != record.reference:
                        st.caption(record.reference)
                    if st.button("Open metadata", key=f"source-{record.reference}"):
                        go(source=record.reference)
            continue
        entity = record.data
        status = entity.get("review_status", "")
        if not matches(entity, query, status):
            continue
        shown += 1
        with st.container(border=True):
            st.subheader(title(entity), anchor=False)
            description(entity)
            if status:
                st.caption(status)
            if st.button("Open project", key=f"open-{entity['pid']}"):
                go(project=entity["pid"])
    if not shown:
        if has_sources:
            st.info("No matching metadata." if query else "No metadata found.")
        else:
            st.info("No matching projects.")


try:
    records, errors = load_records(
        root, metalad=os.environ.get("SHACL_PY_METALAD") == "1"
    )
    for error in errors:
        st.error(error)
    selected = st.query_params.get("project")
    selected_source = st.query_params.get("source")
    if selected_source:
        source = next(
            (
                r
                for r in records
                if isinstance(r, MetadataSource) and r.reference == selected_source
            ),
            None,
        )
        if source is None:
            back("All records")
            st.warning("Metadata source not found.")
        else:
            source_page(source, len(records) > 1)
    elif not selected and len(records) == 1 and isinstance(records[0], MetadataSource):
        source_page(records[0], False)
    elif not selected and len(records) == 1 and isinstance(records[0], Catalogue):
        linked_project(records[0], False)
    elif selected:
        record = next(
            (
                r
                for r in records
                if not isinstance(r, MetadataSource) and r.data["pid"] == selected
            ),
            None,
        )
        if isinstance(record, Catalogue):
            linked_project(record, len(records) > 1)
        elif record:
            legacy_project(record)
        else:
            back("All projects")
            st.warning("Project not found.")
    else:
        home(records)
except (OSError, ValueError) as error:
    st.error(str(error))
