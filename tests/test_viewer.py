import shutil
from html.parser import HTMLParser
from importlib.resources import files
from pathlib import Path
from unittest.mock import patch

import streamlit as st
import yaml
from datalad.api import create, meta_add
from streamlit.testing.v1 import AppTest

from shacl_py.browser import linked_file_selection
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
    href = parser.links.get(label) or next(
        value for key, value in parser.links.items() if key.startswith(label + " ")
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


def test_project_collection_navigation(tmp_path, monkeypatch):
    shutil.copytree(EXAMPLE, tmp_path, dirs_exist_ok=True)
    (tmp_path / ".shacl-py").mkdir()
    (tmp_path / ".shacl-py/config.yaml").write_text(
        "collections:\n  stations:\n    title: Survey stations\n    data: sites.yaml\n"
        "    schema: sites.schema.json\n    records: sites\n    id_field: station_id\n"
        "    label_field: display\n    field_labels: {depth_m: Depth (m)}\n"
        "  empty: {title: Empty collection, data: empty.yaml, schema: sites.schema.json, records: sites}\n"
    )
    (tmp_path / "sites.schema.json").write_text(
        '{"type":"object","required":["sites"]}'
    )
    (tmp_path / "empty.yaml").write_text("sites: []")
    data = tmp_path / "sites.yaml"
    rows = [
        {"station_id": "west", "display": "Marsh"},
        {
            "station_id": "east & bay",
            "display": "Harbour",
            "measurements": [
                {
                    "depth_m": 0,
                    "observed": False,
                    "source": "https://example.org/stations",
                }
            ],
        },
    ]
    data.write_text(yaml.safe_dump({"survey": "Autumn", "sites": rows}))
    page = open_viewer(tmp_path, monkeypatch)
    assert "Shoreline field survey" in html(page)
    follow(page, "Survey stations")
    follow(page, "Harbour")
    body = html(page)
    assert "Harbour</h1>" in body and "Depth (m)</dt>" in body
    assert ">0<" in body and "false" in body and "Autumn" in body
    assert 'href="https://example.org/stations"' in body
    bookmark = page.session_state["fragment"]
    data.write_text(yaml.safe_dump({"survey": "Autumn", "sites": rows[::-1]}))
    page.run()
    assert "Harbour</h1>" in html(page) and page.session_state["fragment"] == bookmark
    page.session_state["fragment"] = "section=collection%2Fstations&q=Marsh"
    page.run()
    assert "Marsh</h1>" in html(page) and "Harbour" not in html(page)
    page.session_state["fragment"] = "section=stations&entry=west"
    page.run()
    assert "Marsh</h1>" in html(page)
    for section in ("stations", "collection%2Fstations"):
        page.session_state["fragment"] = (
            f"section={section}&record=metadata.yaml&entry=urn:example:field-paper&view=attributes"
        )
        page.run()
        body = html(page)
        assert "Harbour</h1>" in body
        assert "Shoreline field survey" not in body
    page.session_state["fragment"] = (
        "section=collection%2Fmissing&record=metadata.yaml&entry=urn:example:field-paper"
    )
    page.run()
    body = html(page)
    assert "This section is unavailable" in body
    assert "Shoreline field survey" not in body
    follow(page, "Empty collection")
    assert "No records in this collection." in html(page)
    follow(page, "Papers")
    assert "Shoreline field survey" in html(page)


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


def test_highlighted_papers_and_datasets_sort_before_their_peers(tmp_path, monkeypatch):
    path = tmp_path / "metadata.yaml"
    graph = {
        "project": {"pid": "urn:project", "title": "Project"},
        "publications": [
            {"pid": "urn:ordinary", "title": "Ordinary paper", "highlighted": False},
            {
                "pid": "urn:pinned",
                "title": "Pinned paper",
                "highlighted": True,
                "dataset_links": [
                    {"dataset": "urn:ordinary-data", "role": "describes"},
                    {"dataset": "urn:pinned-data", "role": "describes"},
                ],
            },
            {
                "pid": "urn:duplicate",
                "source_url": "https://doi.org/10.1234/other",
                "title": "Other paper",
            },
        ],
        "datasets": [
            {"pid": "urn:ordinary-data", "title": "Ordinary data"},
            {"pid": "urn:pinned-data", "title": "Pinned data", "highlighted": True},
        ],
    }
    path.write_text(yaml.safe_dump({"catalogue": graph}))
    (tmp_path / ".studyminimeta.yaml").write_text(
        "person: {}\npublication: [{title: Other paper, doi: 10.1234/other, highlighted: true}]\n"
    )
    assert main(["validate", str(tmp_path)]) == 0
    page = open_viewer(tmp_path, monkeypatch)
    side, detail = html(page).split("<main>")
    assert (
        side.index("Pinned paper</b>")
        < side.index("Other paper</b>")
        < side.index("Ordinary paper</b>")
    )
    assert detail.index("Pinned data</b>") < detail.index("Ordinary data</b>")
    assert "Pinned data</h2>" in detail
    follow(page, "Starred")
    side = html(page).split("<main>")[0]
    assert "Ordinary paper</b>" not in side and side.count("Other paper</b>") == 1
    follow(page, "Open in Datasets")
    side, detail = html(page).split("<main>")
    assert side.index("Pinned data</b>") < side.index("Ordinary data</b>")
    assert 'aria-label="Starred"' in detail
    follow(page, "Starred")
    assert "Ordinary data</b>" not in html(page).split("<main>")[0]

    for kind in ("publications", "datasets"):
        graph[kind][0]["highlighted"] = "true"
        path.write_text(yaml.safe_dump({"catalogue": graph}))
        assert main(["validate", str(tmp_path)]) == 1
        del graph[kind][0]["highlighted"]


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
        "dataset: {name: Example measurements, highlighted: true}\n"
        "publication: [{title: Field survey, doi: 10.1234/example, highlighted: true}]\nperson: {}\n"
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
    imported = yaml.safe_load((tmp_path / "metadata.yaml").read_text())["catalogue"]
    assert imported["publications"][0]["highlighted"] is True
    assert imported["datasets"][0]["highlighted"] is True
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
    from shacl_py.attributes import (
        annotation_values,
        attribute_groups,
        count_leaves,
        metadata_groups,
        unit_symbol,
    )

    qudt = "http://qudt.org/vocab/unit/"
    exposure = {
        "predicate": "urn:x:attributes",
        "display_label": "Exposure",
        "value": "15",
        "unit": qudt + "MilliSEC",
        "attributes": [
            {"predicate": "https://schema.org/propertyID", "value": "OME Plane"},
            {
                "predicate": "http://qudt.org/schema/qudt/hasQuantityKind",
                "value": "http://qudt.org/vocab/quantitykind/Time",
            },
        ],
    }
    nodes = [
        {"predicate": "urn:x:property:note", "value": "loose"},
        {
            "predicate": "https://schema.org/measurementTechnique",
            "display_label": "Brightfield channel",
            "value": "bright-field microscopy",
            "defined_by": "http://purl.obolibrary.org/obo/FBbi_00000243",
            "attributes": [exposure],
        },
        {
            "predicate": "urn:x:attributes",
            "display_label": "Specimen",
            "attributes": [
                {
                    "predicate": "urn:x:attributes",
                    "display_label": "Field of view",
                    "attributes": [
                        {
                            "predicate": "http://purl.org/dc/terms/identifier",
                            "value": "f1",
                        }
                    ],
                },
                {
                    "predicate": "urn:x:attributes",
                    "display_label": "Area",
                    "value": "3.0",
                    "unit": qudt + "MicroM2",
                    "about": ["http://purl.obolibrary.org/obo/GO_0005773"],
                },
            ],
        },
    ]
    general, channel, specimen = attribute_groups(nodes)
    assert (general["label"], general["rows"][0]["label"]) == ("General", "Note")
    # A value with sub-properties leads its own group; qualifiers are not rows.
    lead = channel["lead"]
    assert lead["value"] == {
        "text": "bright-field microscopy",
        "href": "http://purl.obolibrary.org/obo/FBbi_00000243",
    }
    (row,) = channel["rows"]
    assert (row["label"], row["value"]["text"], row["unit"]) == ("Exposure", "15", "ms")
    assert [q["label"] for q in row["qualifiers"]] == ["Property ID", "Quantity kind"]
    assert row["qualifiers"][1]["terms"][0]["text"] == "Time"
    # A label naming a single identifier collapses to one row.
    view, area = specimen["rows"]
    assert (view["label"], view["value"]["text"]) == ("Field of view", "f1")
    assert area["unit"] == "µm²" and area["qualifiers"][0]["terms"][0]["text"] == (
        "GO:0005773"
    )
    assert count_leaves(nodes) == 5
    assert unit_symbol(qudt + "UNITLESS") == "" and unit_symbol("µm") == "µm"
    assert unit_symbol(qudt + "DEG_C") == "°C"
    assert annotation_values({"annotations": {"record_use": "template_only"}}) == [
        "template only"
    ]
    assert annotation_values(
        {"annotations": [{"annotation_tag": "a", "annotation_value": "b"}]}
    ) == ["b"]
    (group,) = metadata_groups(
        [{"extractor_name": "tags", "extracted_metadata": {"units": "metres"}}]
    )
    assert (group["source"], group["rows"][0]["value"]["text"]) == ("File", "metres")


def test_metadata_only_dataset_displays_values_with_qualifiers(tmp_path, monkeypatch):
    (tmp_path / "metadata.yaml").write_text(
        """catalogue:
  project: {pid: 'urn:example:project'}
  publications:
  - pid: urn:example:paper
    title: Field survey
    primary_author: Sam Surveyor
    author_names: [Sam Surveyor, Alex Field]
    annotations: {record_use: template_only}
    attributes: [{predicate: 'http://purl.org/dc/terms/issued', value: '2026-03-10'}]
    dataset_links: [{dataset: 'urn:example:measurements', role: describes}]
  datasets:
  - pid: urn:example:measurements
    title: Measurements
    attributes:
    - predicate: urn:example:duration
      display_label: Duration
      value: '20'
      unit: http://qudt.org/vocab/unit/MilliSEC
      description: Time per reading.
      attributes:
      - predicate: urn:example:uncertainty
        value: '0.5'
        unit: ms
        attributes: [{predicate: 'urn:example:source', value: Table 1}]
"""
    )
    page = open_viewer(tmp_path, monkeypatch)
    sidebar, detail = html(page).split("<main>")
    assert 'class="byline-text">Sam Surveyor</span><span>· 2026' in sidebar
    assert "Sam Surveyor, Alex Field · 2026" in detail.replace("<i></i>", "")
    assert 'class="anno">template only' in sidebar
    for location in ("paper", "dataset"):
        if location == "dataset":
            follow(page, "Open in Datasets")
        body = html(page)
        # The source qualifies the uncertainty, so it is not counted as a value.
        assert "2 attributes" in body
        assert "Attributes <small>2</small>" in body
        panel = body.split('aria-label="Attributes for Measurements">')[1].split(
            "</aside>"
        )[0]
        main_groups = body.split('<div class="agroups">')[1]
        for section in (panel, main_groups):
            assert '<span class="aval">20 <span class="unit"' in section
            assert (
                'href="http://qudt.org/vocab/unit/MilliSEC"' in section
                and ">ms</a>" in section
            )
            assert (
                '<span class="aval">0.5 <span class="unit" title="ms">ms</span>'
                in section
            )
            assert (
                '<li><span title="urn:example:source">Source</span> Table 1</li>'
                in section
            )
            assert "Time per reading." in section
        if location == "dataset":
            assert "Surveyor et al. 2026" in body.split("<main>")[0]
        follow(page, "Files")
        assert "No files linked. This record holds metadata only." in html(page)


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
    assert "Microscope" in body and '">µm</span>' in body
    assert "1 of 1 files local" in body
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
    follow(page, "Attributes")
    assert "External · 0 of 1 files local" in html(page).split("<main>")[1]


def test_linked_files_show_their_own_and_inherited_attributes(tmp_path, monkeypatch):
    path = tmp_path / "metadata.yaml"
    path.write_text(
        """catalogue:
  project: {pid: 'urn:example:project'}
  publications:
  - pid: urn:example:paper
    title: Example paper
    dataset_links: [{dataset: 'urn:example:dataset', role: related}]
  datasets:
  - pid: urn:example:dataset
    title: External comparison
    source_url: https://example.org/source
    attributes:
    - predicate: urn:example:specimen
      display_label: Specimen
      attributes: [{predicate: 'urn:example:compartment', value: vacuole}]
    linked_files:
    - name: image.tif
      url: https://example.org/image.tif
      attributes:
      - predicate: urn:example:acquisition
        display_label: Acquisition
        attributes:
        - predicate: urn:example:exposure
          value: '20'
          unit: http://qudt.org/vocab/unit/MilliSEC
          attributes: [{predicate: 'urn:example:evidence', value: illustrative}]
        - {predicate: 'http://www.w3.org/ns/dcat#byteSize', value: '1024'}
    - {name: centres.txt, url: 'https://example.org/centres.txt'}
"""
    )
    assert main(["validate", str(tmp_path)]) == 0
    page = open_viewer(tmp_path, monkeypatch)
    for location in ("paper", "datasets"):
        if location == "datasets":
            follow(page, "Open in Datasets")
        assert "1.0 KiB" in html(page)
        follow(page, "image.tif")
        for view in ("drawer", "full page"):
            if view == "full page":
                follow(page, "Open page")
            panel = opened_file(page)
            assert "1 group inherited from the dataset" in panel
            assert ">File</span>" in panel and ">Dataset</span>" in panel
            assert ">Acquisition</span>" in panel and ">Specimen</span>" in panel
            assert ">20 " in panel and ">ms</a>" in panel
            assert "1.0 KiB" in panel
            assert "illustrative" in panel and "vacuole" in panel
        assert "predicate: urn:example:exposure" in opened_file(page)
        follow(page, "← Back")
        follow(page, "centres.txt")
        panel = opened_file(page)
        assert "vacuole" in panel
        assert all(
            text not in panel for text in ("Acquisition", "illustrative", "1.0 KiB")
        )
        follow(page, "×")

    graph = yaml.safe_load(path.read_text())
    graph["catalogue"]["datasets"][0]["linked_files"][0]["attributes"] = [
        {"value": "20"}
    ]
    path.write_text(yaml.safe_dump(graph))
    assert main(["validate", str(tmp_path)]) == 1


def test_external_file_folders_preserve_links_and_navigation(tmp_path, monkeypatch):
    linked = [
        {"name": "summary.txt", "url": "https://example.org/summary.txt"},
        {
            "name": "sample_a/image.tif",
            "url": "https://example.org/a/image.tif?version=1",
            "preview_url": "https://example.org/a/preview.png",
            "provider_url": "https://example.org/a/provider",
            "attributes": [{"predicate": "urn:example:marker", "value": "Marker A"}],
        },
        {"name": "sample_a/masks/mask.tif", "url": "https://example.org/a/mask.tif"},
        {
            "name": "sample_a/masks/nuclei/nucleus.tif",
            "url": "https://example.org/a/nucleus.tif",
        },
        {"name": "sample_b/image.tif", "url": "https://example.org/b/image.tif"},
        {"name": "../legacy.tif", "url": "https://example.org/legacy.tif"},
    ]
    graph = {
        "project": {"pid": "urn:example:project"},
        "publications": [
            {
                "pid": "urn:example:paper",
                "title": "Example paper",
                "dataset_links": [{"dataset": "urn:example:data", "role": "describes"}],
            }
        ],
        "datasets": [
            {
                "pid": "urn:example:data",
                "title": "External images",
                "source_url": "https://example.org/source",
                "linked_files": linked,
                "attributes": [{"predicate": "urn:example:specimen", "value": "Cells"}],
            }
        ],
    }
    (tmp_path / "metadata.yaml").write_text(yaml.safe_dump({"catalogue": graph}))
    assert main(["validate", str(tmp_path)]) == 0
    page = open_viewer(tmp_path, monkeypatch)
    body = html(page)
    assert "External · 0 of 6 files local" in body
    assert ">sample_a/</a>" in body and ">sample_b/</a>" in body
    assert ">summary.txt</span>" in body and ">../legacy.tif</span>" in body
    assert ">image.tif</span>" not in body and ">mask.tif</span>" not in body

    follow(page, "sample_a/")
    assert "folder=sample_a" in page.session_state["fragment"]
    assert ">masks/</a>" in html(page) and ">summary.txt</span>" not in html(page)
    follow(page, "image.tif")
    assert "linked=sample_a%2Fimage.tif" in page.session_state["fragment"]
    panel = opened_file(page)
    for value in (
        "https://example.org/a/image.tif?version=1",
        "https://example.org/a/preview.png",
        "https://example.org/a/provider",
        "sample_a/image.tif",
        "Marker A",
        "Cells",
    ):
        assert value in panel
    assert "https://example.org/b/image.tif" not in panel
    follow(page, "Open page")
    assert "sample_a/image.tif" in opened_file(page)
    follow(page, "← Back")
    follow(page, "masks/")
    assert "folder=sample_a%2Fmasks" in page.session_state["fragment"]
    assert ">mask.tif</span>" in html(page) and ">image.tif</span>" not in html(page)
    follow(page, "nuclei/")
    assert "folder=sample_a%2Fmasks%2Fnuclei" in page.session_state["fragment"]
    assert ">nucleus.tif</span>" in html(page)
    follow(page, "↑ Parent folder")
    assert "folder=sample_a%2Fmasks" in page.session_state["fragment"]
    assert ">mask.tif</span>" in html(page) and ">nuclei/</a>" in html(page)
    follow(page, "↑ Parent folder")
    assert "folder=sample_a" in page.session_state["fragment"]
    follow(page, "↑ Parent folder")
    follow(page, "sample_b/")
    follow(page, "image.tif")
    assert "linked=sample_b%2Fimage.tif" in page.session_state["fragment"]
    assert "https://example.org/b/image.tif" in opened_file(page)
    assert "Marker A" not in opened_file(page)
    follow(page, "×")
    follow(page, "↑ Parent folder")
    follow(page, "../legacy.tif")
    assert "https://example.org/legacy.tif" in opened_file(page)


def test_virtual_folders_can_coexist_with_local_files(tmp_path, monkeypatch):
    (tmp_path / "data").mkdir()
    (tmp_path / "data/local.txt").write_text("Local file\n")
    (tmp_path / "metadata.yaml").write_text(
        """catalogue:
  project: {pid: 'urn:example:project'}
  datasets:
  - pid: urn:example:data
    title: Mixed files
    local_folder: data
    linked_files:
    - {name: 'remote/image.tif', url: 'https://example.org/image.tif'}
"""
    )
    page = open_viewer(tmp_path, monkeypatch)
    follow(page, "Datasets 1")
    assert ">local.txt</span>" in html(page)
    follow(page, "remote/")
    assert ">image.tif</span>" in html(page) and ">local.txt</span>" not in html(page)
    follow(page, "↑ Parent folder")
    assert ">local.txt</span>" in html(page)


def test_unusual_linked_names_stay_literal_at_root():
    names = [
        "/absolute/image.tif",
        "../image.tif",
        "sample/../image.tif",
        "sample/./image.tif",
        "sample//image.tif",
        "C:/sample/image.tif",
        r"sample\image.tif",
    ]
    linked = [{"name": name, "url": "https://example.org/image.tif"} for name in names]
    folders, rows = linked_file_selection(linked)
    assert folders == []
    assert [row["name"] for row in rows] == names
    assert all(row["parent"] == "" for row in rows)
    assert linked_file_selection(linked, "sample") == ([], [])
    assert linked_file_selection(linked, "../sample") == ([], [])


def test_modalities_follow_files_across_dataset_views(tmp_path, monkeypatch):
    folder = tmp_path / "data"
    folder.mkdir()
    for name in ("section.tif", "unknown.tif"):
        (folder / name).touch()
    (tmp_path / "metadata.yaml").write_text(
        """catalogue:
  project:
    pid: urn:example:project
    annotations: {identifier_namespace: 'urn:example'}
  publications:
  - pid: urn:example:paper
    title: Example paper
    dataset_links: [{dataset: 'urn:example:dataset', role: describes}]
    characterized_by:
    - {predicate: 'http://purl.org/dc/terms/hasPart', object: 'urn:example:file:data/section.tif'}
    relations:
      urn:example:file:data/section.tif:
        attributes: [{predicate: 'urn:example:data-modality', value: 2D optical section}]
  datasets:
  - pid: urn:example:dataset
    title: Microscopy
    local_folder: data
    attributes: [{predicate: 'http://purl.org/dc/terms/type', display_label: Data modality, value: '3D z-stacks, 2D sections'}]
    linked_files:
    - name: annotations.zip
      url: https://example.org/annotations.zip
      attributes:
      - {predicate: 'urn:example:archive-contents', value: 2D masks (TIFF)}
      - {predicate: 'urn:example:archive-contents', value: cell measurements (CSV)}
"""
    )
    page = open_viewer(tmp_path, monkeypatch)
    archive = "2D masks (TIFF), cell measurements (CSV)"
    for location in ("paper", "datasets"):
        if location == "datasets":
            follow(page, "Open in Datasets")
        body = html(page)
        assert "<dt>Data modality</dt><dd>3D z-stacks, 2D sections</dd>" in body
        assert "<b>Archive contents</b> " + archive in body
        assert "<b>Data modality</b> 2D optical section" in body
        for name, value in (
            ("annotations.zip", archive),
            ("section.tif", "2D optical section"),
        ):
            follow(page, name)
            assert value in opened_file(page)
            follow(page, "Open page")
            assert value in opened_file(page)
            follow(page, "← Back")
        follow(page, "unknown.tif")
        assert "Data modality" not in opened_file(
            page
        ) and "Archive contents" not in opened_file(page)
        follow(page, "×")
