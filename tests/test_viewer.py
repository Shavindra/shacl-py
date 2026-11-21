import shutil
from html.parser import HTMLParser
from importlib.resources import files
from pathlib import Path
from unittest.mock import patch

import streamlit as st
import yaml
from datalad.api import create, meta_add
from streamlit.testing.v1 import AppTest

from shacl_py.cli import main

EXAMPLE = Path(__file__).resolve().parents[1] / "examples/coastal-survey"


def open_viewer(root, monkeypatch):
    monkeypatch.setenv("SHACL_PY_ROOT", str(root))
    # AppTest runs Python without a browser to supply the URL fragment.
    monkeypatch.setattr(
        "shacl_py.navigation.router",
        lambda **_: {"route": st.session_state.get("fragment", "")},
    )
    page = AppTest.from_file(str(files("shacl_py") / "app.py")).run()
    assert not page.exception
    return page


def html(page):
    return "\n".join(node.proto.body for node in page.get("html"))


def follow(page, label):
    class Links(HTMLParser):
        href = None

        def __init__(self):
            super().__init__()
            self.links = {}

        def handle_starttag(self, tag, attrs):
            if tag == "a":
                self.href = dict(attrs).get("href")
                self.label = ""

        def handle_data(self, text):
            if self.href:
                self.label += text

        def handle_endtag(self, tag):
            if tag == "a" and self.href:
                self.links[self.label.strip()] = self.href
                self.href = None

    parser = Links()
    parser.feed(html(page))
    href = next(
        value
        for key, value in parser.links.items()
        if key == label or key.startswith(label + " ")
    )
    assert href.startswith("#")
    page.session_state["fragment"] = href[1:]
    page.run()
    assert not page.exception and not page.error
    return page


def opened_file(page):
    """Return the open file drawer, or the full file page, from the rendered HTML."""
    body = html(page)
    start = body.find('<aside class="drawer">')
    if start < 0:
        start = body.find('<main class="filepage">')
    assert start >= 0
    return body[start:]


def test_view_metadata_file(tmp_path, monkeypatch):
    paper = tmp_path / "collection"
    paper.mkdir()
    (paper / "README.md").write_text("# Review notes")
    (paper / ".studyminimeta.yaml").write_text(
        "dataset: {name: Station readings}\npublication: [{title: Field survey}]\nperson: {}\n"
    )
    data = paper / "data"
    data.mkdir()
    (data / "measurements").write_text("value\n42\n")
    page = open_viewer(tmp_path, monkeypatch)

    assert "Field survey</h1>" in html(page)

    assert "In this metadata source" in html(page)
    follow(page, "data/")
    follow(page, "measurements")
    drawer = opened_file(page)
    assert "<code>measurements</code>" in drawer and "Local" in drawer
    assert "value\n42" in drawer
    follow(page, "Open page ↗")
    assert '<h1 class="mono">measurements</h1>' in opened_file(page)
    assert not list(tmp_path.rglob("metadata.yaml"))


def test_view_metalad_store_read_only(tmp_path, monkeypatch):
    config = tmp_path / "gitconfig"
    config.write_text("[user]\nname = Viewer test\nemail = test@example.org\n")
    monkeypatch.setenv("GIT_CONFIG_GLOBAL", str(config))
    root = tmp_path / "observations"
    dataset = create(path=str(root), annex=False, result_renderer="disabled")
    (root / "observations.tsv").write_text("depth\n5\n")
    dataset.save(result_renderer="disabled")
    record = {
        "type": "dataset",
        "dataset_id": dataset.id,
        "dataset_version": dataset.repo.get_hexsha(),
        "extractor_name": "example",
        "extractor_version": "1",
        "extraction_parameter": {},
        "extraction_time": 1700000000.0,
        "agent_name": "Viewer test",
        "agent_email": "test@example.org",
        "extracted_metadata": {"@type": "Dataset", "name": "Stored observations"},
    }
    meta_add(record, dataset=dataset, result_renderer="disabled")
    meta_add(
        {
            **record,
            "type": "file",
            "path": "observations.tsv",
            "extracted_metadata": {"units": "metres"},
        },
        dataset=dataset,
        result_renderer="disabled",
    )

    def contents():
        return {p: p.read_bytes() for p in root.rglob("*") if p.is_file()}

    before = contents()
    page = open_viewer(root, monkeypatch)
    assert "Stored observations</h1>" in html(page)
    follow(page, "Files")
    follow(page, "observations.tsv")
    drawer = opened_file(page)
    assert "<code>observations.tsv</code>" in drawer
    follow(page, "Open page ↗")
    assert "metres" in opened_file(page)
    assert contents() == before


def test_setup_uses_supplied_metadata(tmp_path):
    folder = tmp_path / "sources/one"
    folder.mkdir(parents=True)
    (folder / "README.md").write_text("# My review")
    assert (
        main(
            [
                "setup",
                str(tmp_path),
                "--template",
                "paper-review",
                "--papers-folder",
                "sources",
                "--title",
                "Survey",
                "--no-input",
            ]
        )
        == 0
    )
    graph = yaml.safe_load((tmp_path / "metadata.yaml").read_text())["catalogue"]
    assert "title" not in graph["publications"][0] and "reviews" not in graph
    assert (
        yaml.safe_load((tmp_path / ".studyminimeta.yaml").read_text())["study"]["name"]
        == "Survey"
    )
    assert main(["validate", str(tmp_path)]) == 0


def test_validate_identifies_the_invalid_record(tmp_path, capsys):
    path = tmp_path / "metadata.yaml"
    path.write_text("catalogue: {project: {title: Missing ID}}\n")
    assert main(["validate", str(tmp_path)]) == 1
    error = capsys.readouterr().err
    assert str(path) in error and "pid" in error


def test_serve_on_localhost_with_requested_port():
    with patch("shacl_py.cli.subprocess.call", return_value=0) as launch:
        assert main(["serve", str(EXAMPLE), "--port", "8510"]) == 0
    command = launch.call_args.args[0]
    assert "--server.address=127.0.0.1" in command and "--server.port=8510" in command


def test_example_homepage_and_annex_files(tmp_path, monkeypatch):
    shutil.copytree(EXAMPLE, tmp_path, dirs_exist_ok=True)
    raw = tmp_path / "papers/field-survey/data/raw"
    (raw / "missing.csv").symlink_to(tmp_path / ".git/annex/objects/missing")
    page = open_viewer(tmp_path, monkeypatch)
    follow(page, "Papers")
    follow(page, "Datasets 2")
    assert "Station readings" in html(page)
    follow(page, "readings.csv")
    drawer = opened_file(page)
    assert "<code>readings.csv</code>" in drawer and "Local" in drawer
    follow(page, "Papers")
    follow(page, "Notes")
    assert "comparison of station means" in html(page)
    follow(page, "Other files")
    follow(page, "missing.csv")
    drawer = opened_file(page)
    assert "Remote (annexed)" in drawer and "datalad get" in drawer
    assert not page.button


def test_primary_author_in_paper_list(tmp_path, monkeypatch):
    metadata = tmp_path / ".studyminimeta.yaml"
    paper = {"title": "Field survey", "author": ["a", "b"], "primary_author": "b"}
    study = {
        "publication": [paper],
        "person": {
            "a": {"given_name": "Jo", "last_name": "Smith"},
            "b": {"given_name": "Sam", "last_name": "Patel"},
        },
    }
    for expected in ("Sam Patel", "Jo Smith, Sam Patel"):
        metadata.write_text(yaml.safe_dump(study))
        page = open_viewer(tmp_path, monkeypatch)
        assert f'class="byline-text">{expected}</span>' in html(page).split("<main>")[0]
        assert "Jo Smith, Sam Patel" in html(page).split("<main>")[1]
        paper.pop("primary_author", None)


def test_viewer_branding(tmp_path, monkeypatch):
    from shacl_py.branding import branding

    metadata = tmp_path / ".studyminimeta.yaml"
    metadata.write_text("publication: [{title: Field survey}]\nperson: {}\n")
    folder = tmp_path / ".shacl-py"
    folder.mkdir()
    config = folder / "config.yaml"
    circle = '<circle cx="9" cy="9" r="9" fill="#fff">'
    assert circle in html(open_viewer(tmp_path, monkeypatch))
    assert branding(tmp_path)["page_title"] == "shaclpy"
    config.write_text("app_name: Cell sim\n")
    assert branding(tmp_path)["page_title"] == "Cell sim"
    config.write_text(
        "app_name: Cell sim\npage_title: Papers\napp_theme: {logo: logo.svg}\n"
    )
    (folder / "logo.svg").write_text('<svg xmlns="http://www.w3.org/2000/svg"/>')
    assert branding(tmp_path)["page_title"] == "Papers"
    for root in (tmp_path, metadata):
        markup = html(open_viewer(root, monkeypatch))
        assert circle not in markup
        assert 'src="data:image/svg+xml;base64,' in markup
        assert "Cell sim</strong>" in markup


def test_setup_and_serve_overlapping_sources(tmp_path, monkeypatch):
    folder = tmp_path / "papers" / "sample"
    folder.mkdir(parents=True)
    metadata = folder / ".studyminimeta.yaml"
    paper = {"title": "Field survey", "doi": "10.1234/EXAMPLE"}
    metadata.write_text(yaml.safe_dump({"person": {}, "publication": [paper]}))
    setup = [
        "setup",
        str(tmp_path),
        "--template",
        "paper-review",
        "--papers-folder",
        "papers",
        "--no-input",
    ]
    assert main(setup) == 0
    catalogue = tmp_path / "metadata.yaml"
    before = catalogue.read_bytes()
    assert main(setup) == 0
    assert catalogue.read_bytes() == before
    # Another article can share a title. Its own DOI identifies it separately.
    second = folder / "paper.json"
    second.write_text('{"title":"Field survey","doi":"10.1234/different"}')
    page = open_viewer(tmp_path, monkeypatch)
    body = html(page)
    assert "Papers <small>2</small>" in body
    assert body.split("<main>")[0].count(">Field survey</b>") == 2
    follow(page, "Raw metadata")
    assert "papers/sample/.studyminimeta.yaml</a>" in html(page)
    follow(page, "papers/sample/.studyminimeta.yaml")
    assert "10.1234/EXAMPLE" in html(page).split("<article>")[-1]


def test_dataset_counts_after_paper_review_import(tmp_path, monkeypatch):
    folder = tmp_path / "papers" / "sample"
    (folder / "data/raw").mkdir(parents=True)
    (folder / ".studyminimeta.yaml").write_text(
        "dataset: {name: Example measurements}\npublication: [{title: Field survey, doi: 10.1234/example}]\nperson: {}\n"
    )
    (tmp_path / ".studyminimeta.yaml").write_text(
        "dataset: {name: Whole project}\nperson: {}\n"
    )
    assert (
        main(
            [
                "setup",
                str(tmp_path),
                "--template",
                "paper-review",
                "--papers-folder",
                "papers",
                "--no-input",
            ]
        )
        == 0
    )
    page = open_viewer(tmp_path, monkeypatch)
    assert "Datasets <small>2</small>" in html(page).split("</header>")[0]
    assert "Datasets <small>1</small>" in html(page).split("<main>")[1]
    follow(page, "Datasets 2")
    assert html(page).split("<main>")[0].count(">Example measurements</b>") == 1
    assert "<code>papers/sample/data/raw</code>" in html(page).split("<main>")[1]


def test_add_datasets_command(tmp_path):
    root = tmp_path / "project"
    shutil.copytree(EXAMPLE, root)
    path = root / "metadata.yaml"
    args = [
        "add-datasets",
        "--project",
        str(root),
        "--paper",
        "papers/field-survey",
        "--dataset",
        "Readings file",
        "papers/field-survey/data/raw/readings.csv",
        "--dataset",
        "Output folder",
        "papers/field-survey/data/output",
    ]
    before = path.read_bytes()
    assert main(args + ["--dataset", "Missing", "missing"]) == 1
    assert path.read_bytes() == before
    assert main(args) == 0
    graph = yaml.safe_load(path.read_text())["catalogue"]
    linked = {link["dataset"] for link in graph["publications"][0]["dataset_links"]}
    assert {d["title"] for d in graph["datasets"] if d["pid"] in linked} >= {
        "Readings file",
        "Output folder",
    }
    saved = path.read_bytes()
    assert main(args) == 0
    assert path.read_bytes() == saved


def test_header_metadata_and_dataset_description(tmp_path, monkeypatch):
    folder = tmp_path / "papers" / "sample"
    folder.mkdir(parents=True)
    names = [f"Author {i:02}" for i in range(1, 12)]
    metadata = {
        "publication": [
            {
                "title": "Field survey",
                "doi": "10.1234/field",
                "year": 2023,
                "author": names,
            }
        ],
        "dataset": {"name": "Readings", "description": "Depth at each station."},
        "person": {},
    }
    (folder / ".studyminimeta.yaml").write_text(yaml.safe_dump(metadata))
    assert (
        main(
            [
                "setup",
                str(tmp_path),
                "--template",
                "paper-review",
                "--papers-folder",
                "papers",
                "--no-input",
            ]
        )
        == 0
    )
    page = open_viewer(tmp_path, monkeypatch)
    body = html(page).split("<main>")[1]
    assert "Author 10, …" in body and "Author 11" not in body
    assert " · 2023" in body and "Depth at each station." in body
    follow(page, "Open in Datasets")
    assert "Depth at each station." in html(page).split("<main>")[1]


def test_attribute_groups_and_annotations():
    from shacl_py.attributes import annotation_values, attribute_groups, metadata_groups

    nodes = [
        {"predicate": "urn:x:property:note", "value": "loose"},
        {
            "predicate": "urn:x:property:microscope",
            "display_label": "Microscope",
            "attributes": [
                {"display_label": "Pixel size", "value": "0.065", "unit": "µm"},
                {
                    "display_label": "Channel",
                    "attributes": [{"display_label": "Exposure", "value": "20"}],
                },
                {
                    "display_label": "Term",
                    "value": "http://purl.obolibrary.org/obo/GO_1",
                },
            ],
        },
    ]
    general, microscope = attribute_groups(nodes)
    assert (general["label"], general["rows"][0]["label"]) == ("General", "note")
    assert microscope["count"] == 3
    rows = microscope["rows"]
    assert rows[0]["unit"] == "µm" and rows[1]["header"] and rows[2]["pad"] == 14
    assert rows[3]["link"] and not rows[0]["link"]
    assert annotation_values({"annotations": {"record_use": "template_only"}}) == [
        "template only"
    ]
    assert annotation_values(
        {"annotations": [{"annotation_tag": "a", "annotation_value": "b"}]}
    ) == ["b"]
    (group,) = metadata_groups(
        [{"extractor_name": "tags", "extracted_metadata": {"units": "metres"}}]
    )
    assert (group["source"], group["rows"][0]["value"]) == ("File", "metres")


def test_dataset_attributes_and_external_files(tmp_path, monkeypatch):
    source = "https://open.quiltdata.com/b/allencell/packages/example"
    long_name = "6677e50cfb7370eb6dbbcee4865563d5604a7dc5_Scene-1-P24-E06.ome.tiff"
    first, second = "urn:example:acquisition", "urn:example:model"
    (tmp_path / "data").mkdir()
    (tmp_path / "data/settings.yaml").write_text("exposure: 20\n")
    graph = {
        "project": {"pid": "urn:example:dummy", "title": "Dummy"},
        "publications": [
            {
                "pid": "urn:example:paper",
                "title": "Reference records",
                "dataset_links": [
                    {"dataset": d, "role": "describes"}
                    for d in (first, second, "urn:example:external")
                ],
            }
        ],
        "datasets": [
            {
                "pid": first,
                "title": "Acquisition",
                "local_folder": "data",
                "annotations": {"record_use": "template_only"},
                "file_groups": [{"label": "Files", "paths": ["settings.yaml"]}],
                "attributes": [
                    {
                        "predicate": "urn:example:property:microscope",
                        "display_label": "Microscope",
                        "attributes": [
                            {
                                "predicate": "urn:example:property:pixel-size",
                                "display_label": "Pixel size",
                                "value": "0.065",
                                "unit": "µm",
                            }
                        ],
                    }
                ],
            },
            {"pid": second, "title": "Model", "source_datasets": [first]},
            {
                "pid": "urn:example:external",
                "title": "External images",
                "source_url": source,
                "linked_files": [
                    {
                        "name": long_name,
                        "url": "https://example.org/files/" + long_name,
                        "preview_url": "https://example.org/preview/" + long_name,
                    }
                ],
            },
        ],
    }
    (tmp_path / "metadata.yaml").write_text(yaml.safe_dump({"catalogue": graph}))
    assert main(["validate", str(tmp_path)]) == 0
    page = open_viewer(tmp_path, monkeypatch)
    follow(page, "Datasets 3")
    follow(page, "Acquisition")
    body = html(page).split("<main>")[1]
    assert '<span class="anno">template only</span>' in body
    follow(page, "Attributes")
    body = html(page).split("<main>")[1]
    assert "Microscope" in body and '<span class="unit">µm</span>' in body
    assert "Used by" in body and ">Model</a>" in body
    follow(page, "Files")
    follow(page, "settings.yaml")
    drawer = opened_file(page)
    assert (
        "1 group inherited from the dataset" in drawer and ">Dataset</span>" in drawer
    )
    follow(page, "Model")
    assert "No files linked. This record holds metadata only." in html(page)
    assert "Metadata only" in html(page).split("<main>")[1]
    follow(page, "External images")
    body = html(page).split("<main>")[1]
    assert (
        "Hosted on open.quiltdata.com" in body
        and "External · 0 of 1 files local" in body
    )
    follow(page, long_name)
    drawer = opened_file(page)
    assert "Hosted externally on open.quiltdata.com" in drawer
    assert "Provider page ↗" in drawer and "Availability" in drawer
