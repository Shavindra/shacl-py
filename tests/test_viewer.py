import shutil
from html.parser import HTMLParser
from importlib.resources import files
from pathlib import Path
from unittest.mock import patch
from urllib.parse import parse_qsl

import yaml
from datalad.api import create, meta_add
from streamlit.testing.v1 import AppTest

from shacl_py.cli import main

EXAMPLE = Path(__file__).resolve().parents[1] / "examples/coastal-survey"


def open_viewer(root, monkeypatch):
    monkeypatch.setenv("SHACL_PY_ROOT", str(root))
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
    page.query_params.clear()
    page.query_params.update(parse_qsl(href.removeprefix("?")))
    page.run()
    assert not page.exception and not page.error
    return page


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
    assert page.title[-1].value == "measurements" and "Available" in html(page)
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
    assert page.title[-1].value == "observations.tsv" and "metres" in html(page)
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
    assert page.title[-1].value == "readings.csv" and "Available" in html(page)
    follow(page, "Papers")
    follow(page, "Notes")
    assert "comparison of station means" in html(page)
    follow(page, "Other files")
    follow(page, "missing.csv")
    assert "Unavailable" in html(page) and not page.button


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
