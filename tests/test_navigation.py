import os
import socket
import subprocess
import sys
import time
from contextlib import contextmanager
from importlib.resources import files
from pathlib import Path
from urllib.error import URLError
from urllib.parse import parse_qsl, urlsplit
from urllib.request import urlopen

import pytest
from playwright.sync_api import expect, sync_playwright
from test_collection_detail import project as collection_project


@contextmanager
def serve_project(root):
    with socket.socket() as sock:
        sock.bind(("127.0.0.1", 0))
        port = sock.getsockname()[1]
    url = f"http://127.0.0.1:{port}/"
    with subprocess.Popen(
        [
            sys.executable,
            "-m",
            "streamlit",
            "run",
            str(files("shacl_py") / "app.py"),
            "--server.address=127.0.0.1",
            f"--server.port={port}",
            "--server.headless=true",
        ],
        env=os.environ | {"SHACL_PY_ROOT": str(root)},
    ) as server:
        try:
            for _ in range(100):
                if server.poll() is not None:
                    pytest.fail("Viewer exited before startup")
                try:
                    with urlopen(url + "_stcore/health", timeout=1):
                        break
                except URLError:
                    time.sleep(0.1)
            else:
                pytest.fail("Viewer did not start")
            yield url
        finally:
            server.terminate()


@pytest.fixture
def viewer_url():
    with serve_project(
        Path(__file__).resolve().parents[1] / "examples/coastal-survey"
    ) as url:
        yield url


@pytest.fixture
def page():
    with sync_playwright() as playwright, playwright.chromium.launch() as browser:
        yield browser.new_page()


def test_navigation_stays_in_one_document(page, viewer_url):
    documents = []
    sockets = []

    def record_navigation(request):
        if request.is_navigation_request() and request.frame == page.main_frame:
            documents.append(request.url)

    page.on("request", record_navigation)
    page.on("websocket", lambda socket: sockets.append(socket.url))
    page.goto(viewer_url, wait_until="domcontentloaded")
    notes = page.locator(".study .notes")
    page.get_by_role("link", name="Notes", exact=True).click()
    expect(notes).to_contain_text("comparison of station means")
    bookmark = page.url

    page.go_back()
    expect(page.locator(".study .dshead")).to_be_visible()
    page.go_forward()
    expect(notes).to_be_visible()
    assert page.url == bookmark

    search = page.get_by_role("searchbox", name="Search papers, datasets, files")
    term = "coast & sea #1 + β"
    search.fill(term)
    search.press("Enter")
    expect(page.locator(".study main")).to_contain_text("No matching records")
    assert dict(parse_qsl(urlsplit(page.url).fragment)) == {"q": term}
    page.go_back()
    expect(notes).to_be_visible()
    assert documents == [viewer_url]
    assert len(sockets) == 1

    page.reload(wait_until="domcontentloaded")
    expect(notes).to_contain_text("comparison of station means")
    assert page.url == bookmark


def test_sidebar_search_as_you_type(page, viewer_url):
    page.goto(viewer_url, wait_until="domcontentloaded")
    sidebar = page.locator(".study .layout > aside")
    rows = sidebar.locator("a.row b")
    search = sidebar.get_by_role("searchbox")
    expect(rows).to_have_count(3)

    search.fill("sho")
    expect(rows).to_have_text(["Shoreline field survey"])
    expect(search).to_be_focused()
    page.keyboard.press("Home")
    page.keyboard.press("ArrowRight")
    page.keyboard.type("X")
    expect(rows).to_have_count(0)
    expect(search).to_have_value("sXho")
    expect(search).to_be_focused()
    assert search.evaluate("e => e.selectionStart") == 2
    bookmark = page.url
    page.go_back()
    expect(rows).to_have_count(3)
    page.go_forward()
    expect(search).to_have_value("sXho")
    page.reload(wait_until="domcontentloaded")
    expect(rows).to_have_count(0)
    assert page.url == bookmark

    search.fill("")
    expect(rows).to_have_count(3)
    nested = page.get_by_role("searchbox", name="Filter datasets", exact=True)
    nested.fill("unlisted")
    expect(page.locator(".study .split article")).to_have_text("No matching datasets.")
    nested.fill("READING")
    expect(page.locator(".study .split h2")).to_have_text("Station readings")
    expect(nested).to_be_focused()
    page.locator(".study header").get_by_role("link", name="Datasets 3").click()
    expect(search).to_have_attribute("placeholder", "Filter by name, PID, format")
    sidebar.get_by_role("link", name="Starred", exact=True).click()
    expect(rows).to_have_text(["Station readings"])
    search.fill("unlisted")
    expect(rows).to_have_count(0)
    search.fill("")
    expect(rows).to_have_text(["Station readings"])
    sidebar.get_by_role("link", name="All", exact=True).click()
    expect(rows).to_have_count(3)


def test_concept_notes_across_record_tabs(page, tmp_path):
    collection_project(tmp_path)
    with serve_project(tmp_path) as url:
        page.goto(url, wait_until="domcontentloaded")
        notes = page.locator(".concept-notes")
        summary = notes.locator("summary")
        expect(summary).to_be_visible()
        expect(notes.locator("dl")).to_be_hidden()
        summary.press("Enter")
        expect(notes.locator("dd")).to_have_text(["Sandstone", "Nature reserve"])
        expect(notes.locator("dl")).to_be_visible()

        page.get_by_role("link", name="North 2", exact=True).click()
        expect(page.locator(".record-id code")).to_have_text("spring")
        expect(notes.locator("dl")).to_be_visible()
        page.get_by_role("link", name="Raw metadata", exact=True).click()
        expect(page.locator("article > pre")).to_contain_text("sample: spring")
        expect(notes.locator("dl")).to_be_visible()

        summary.press("Enter")
        page.get_by_role("link", name="North 1", exact=True).click()
        expect(page.locator("article > pre")).to_contain_text("sample: winter")
        expect(notes.locator("dl")).to_be_hidden()
        page.get_by_text("Inlet", exact=True).click()
        expect(notes).to_have_count(0)


def test_graph_navigation_and_search(page, viewer_url):
    page.goto(viewer_url, wait_until="domcontentloaded")
    page.get_by_role("link", name="Graph", exact=True).click()
    chart = page.locator("svg.canvas")
    nodes = chart.locator(".node")
    expect(nodes).to_have_count(7)
    expect(chart.locator(".edge")).to_have_count(6)
    expect(chart.locator(".paper")).to_have_count(3)
    expect(chart.locator(".dataset")).to_have_count(3)
    tag = chart.get_by_role("link", name="Label · Coastal monitoring")
    tag.click()
    expect(page.locator(".graph-heading h1")).to_have_text("Coastal monitoring")
    expect(nodes).to_have_count(3)
    expect(chart.locator(".edge.tag")).to_have_count(2)
    page.get_by_role("combobox", name="Relationship", exact=True).select_option(
        "Labelled"
    )
    expect(nodes).to_have_count(3)
    assert "label=Coastal+monitoring" in page.url
    page.get_by_role("link", name="Show full graph").click()
    expect(nodes).to_have_count(7)
    full_graph = page.url

    page.get_by_role("combobox", name="Relationship", exact=True).select_option(
        "Derived from"
    )
    expect(nodes).to_have_count(2)
    expect(chart.locator(".edge title")).to_have_text("Derived from")
    page.get_by_text("List relationships", exact=True).click()
    table = page.get_by_role("table", name="Record relationships")
    expect(table.get_by_role("cell")).to_have_text(
        ["Mean reading per station", "Derived from", "Station readings"]
    )
    page.get_by_role("link", name="Show full graph").click()
    expect(nodes).to_have_count(7)
    chart.get_by_role("link", name="Dataset · Station readings").press("Enter")
    expect(
        page.get_by_role("heading", name="Station readings", exact=True)
    ).to_be_visible()
    page.go_back()
    expect(nodes).to_have_count(7)
    assert page.url == full_graph
    page.go_forward()
    page.get_by_role("link", name="View in graph").click()
    expect(nodes).to_have_count(4)
    focus = page.url
    page.reload(wait_until="domcontentloaded")
    expect(chart.locator(".edge")).to_have_count(3)
    assert page.url == focus

    search = page.get_by_role("searchbox", name="Find a graph record")
    search.fill("unknown record")
    search.press("Enter")
    expect(page.locator(".graph-heading")).to_contain_text("No matching records")
    expect(chart).to_have_count(0)
    page.get_by_role("link", name="Show full graph").click()
    expect(nodes).to_have_count(7)


def test_graph_mouse_controls(page, viewer_url):
    page.goto(viewer_url + "#section=graph", wait_until="domcontentloaded")
    chart = page.locator("svg.canvas")
    viewport = chart.locator(".viewport")
    expect(chart.locator(".node")).to_have_count(7)
    chart.scroll_into_view_if_needed()
    box = chart.bounding_box()
    x, y = box["x"] + 30, box["y"] + 36

    def camera():
        return viewport.evaluate(
            "(g) => {const m = g.transform.baseVal.consolidate().matrix; return [m.a, m.e, m.f]}"
        )

    initial = camera()
    original = viewport.get_attribute("transform")
    page.mouse.move(x, y)
    page.mouse.wheel(0, -180)
    expect(viewport).not_to_have_attribute("transform", original)
    k, tx, ty = camera()
    assert k > initial[0]
    assert (30 - tx) / k == pytest.approx((30 - initial[1]) / initial[0], abs=0.1)
    assert (36 - ty) / k == pytest.approx((36 - initial[2]) / initial[0], abs=0.1)
    page.get_by_role("button", name="Zoom out").click()
    assert camera()[0] < k
    page.get_by_role("button", name="Zoom in").click()
    assert camera()[0] == pytest.approx(k)
    page.get_by_role("button", name="Fit graph").click()
    assert camera() == pytest.approx(initial)

    page.mouse.move(x, y)
    page.mouse.down()
    page.mouse.move(x + 70, y + 45, steps=6)
    page.mouse.up()
    assert camera() == pytest.approx([initial[0], initial[1] + 70, initial[2] + 45])
    page.get_by_role("button", name="Fit graph").click()
    assert camera() == pytest.approx(initial)

    point = chart.get_by_role("link", name="Dataset · Station readings").locator(
        ".mark"
    )
    mark = point.bounding_box()
    edges = chart.locator(".edge")

    def paths():
        return edges.evaluate_all(
            "(paths) => paths.map(path => path.getAttribute('d'))"
        )

    before = paths()
    x = mark["x"] + mark["width"] / 2
    y = mark["y"] + mark["height"] / 2
    page.mouse.move(x, y)
    page.mouse.down()
    page.mouse.move(x + 36, y + 24, steps=6)
    page.mouse.up()
    assert point.bounding_box()["x"] == pytest.approx(mark["x"] + 36, abs=1)
    assert point.bounding_box()["y"] == pytest.approx(mark["y"] + 24, abs=1)
    assert paths() != before
    assert camera() == pytest.approx(initial)
    assert page.url.endswith("#section=graph")
    point.click()
    expect(
        page.get_by_role("heading", name="Station readings", exact=True)
    ).to_be_visible()


def test_method_summary_shows_variant_and_compact_parameter_rows(page, tmp_path):
    (tmp_path / "metadata.yaml").write_text(
        "catalogue:\n  project: {pid: 'urn:test:p'}\n  includes: [paper.yaml]\n"
    )
    (tmp_path / "paper.yaml").write_text(
        """publications:
- pid: urn:test:paper
  title: Imaging
  attributes:
  - predicate: urn:test:methods
    attributes:
    - predicate: urn:test:experimental
      attributes:
      - predicate: urn:test:image-acquisition
        attributes:
        - predicate: urn:test:technique
          defined_by: urn:test:brightfield
          value: Bright-field microscopy
          description: A detailed acquisition protocol.
          annotations: {presentation: summary, variant: Tiled overview}
          attributes:
          - predicate: urn:test:overlap
            display_label: Tile overlap
            value: 10%
"""
    )
    with serve_project(tmp_path) as url:
        page.goto(url, wait_until="domcontentloaded")
        page.locator(".heading nav").get_by_role("link", name="Methods 1").click()
        entry = page.locator(".method-entry")
        expect(entry.locator(".method-name")).to_have_text("Bright-field microscopy")
        expect(entry).to_contain_text("Tiled overview")
        expect(entry).not_to_contain_text("A detailed acquisition protocol.")
        entry.get_by_text("Parameters", exact=True).click()
        expect(entry.locator("dd")).to_have_text("10%")
        for field in ("dt", "dd", ".aval"):
            expect(entry.locator(field)).to_have_css("font-size", "12.5px")


def test_methods_filters_and_file_links(page, tmp_path):
    import yaml

    def group(identifier, label, *children):
        return {
            "predicate": f"urn:example:{identifier}",
            "display_label": label,
            "attributes": list(children),
        }

    def microscopy(term, **annotation):
        node = {
            "predicate": "urn:example:technique",
            "value": term,
            "defined_by": f"urn:example:{term}",
        }
        if annotation:
            node["annotations"] = annotation
        return group(
            "methods",
            "Methods",
            group(
                "experimental",
                "Experimental",
                group("image-acquisition", "Image acquisition", node),
            ),
        )

    def subject(go):
        return {"predicate": "http://purl.org/dc/terms/subject", "object": go}

    def paper(key, title, *datasets):
        return {
            "pid": key,
            "title": title,
            "dataset_links": [{"dataset": ds, "role": "describes"} for ds in datasets],
        }

    vacuole = "http://purl.obolibrary.org/obo/GO_0005773"
    nucleus = "http://purl.obolibrary.org/obo/GO_0005634"
    a, b, c = ("urn:example:" + k for k in ("paired", "unlabelled", "other"))
    image = {
        "name": "stack/field.tif",
        "url": "https://example.org/field.tif",
        "attributes": [
            microscopy(
                "DIC",
                purpose="Record contrast",
                inputs=["Specimen"],
                outputs=[{"label": "Measurements", "ref": c}],
            )
        ],
    }
    catalogue = {
        "project": {"pid": "urn:example:project", "title": "Sample"},
        "publications": [
            paper("urn:example:p", "Matching paper", a),
            paper("urn:example:q", "Separate datasets", b, c),
        ],
        "datasets": [
            {
                "pid": a,
                "title": "Paired images",
                "characterized_by": [subject(vacuole)],
                "linked_files": [image],
            },
            {
                "pid": b,
                "title": "DIC only",
                "attributes": [microscopy("DIC")],
                "characterized_by": [subject(nucleus)],
            },
            {
                "pid": c,
                "title": "Measurements",
                "attributes": [
                    microscopy(
                        "Fluorescence",
                        purpose="Image the sample",
                        inputs=[{"label": "Source images", "ref": a}],
                    )
                ],
                "characterized_by": [subject(vacuole)],
                "linked_files": [
                    {"name": "table.tsv", "url": "https://example.org/table.tsv"}
                ],
            },
        ],
    }
    (tmp_path / "metadata.yaml").write_text(
        yaml.safe_dump({"catalogue": catalogue}, sort_keys=False)
    )
    with serve_project(tmp_path) as url:
        page.goto(url, wait_until="domcontentloaded")
        side = page.locator(".layout > aside")
        technique = side.get_by_label("Technique", exact=True)
        compartment = side.get_by_label("Compartment", exact=True)
        technique.select_option(label="DIC")
        expect(side.locator("a.row")).to_have_count(2)
        compartment.select_option(value="GO:0005773")
        expect(side.locator("a.row")).to_have_count(1)
        expect(side.locator("a.row")).to_contain_text("Matching paper")
        main = page.locator(".study main")
        main.locator(".heading nav").get_by_role("link", name="Methods 0").click()
        expect(main).to_contain_text("No methods recorded for this paper.")
        page.locator(".study header nav").get_by_role("link", name="Datasets 3").click()
        expect(side.locator("a.row")).to_have_count(1)
        expect(main.locator("h1")).to_have_text("Paired images")
        main.get_by_role("link", name="stack/").click()
        main.get_by_role("link", name="field.tif", exact=True).click()
        drawer = page.locator(".drawer")
        expect(drawer.locator(".file-methods")).to_contain_text(
            "Experimental › Image acquisition"
        )
        expect(drawer.locator(".file-methods")).to_contain_text("Record contrast")
        drawer.get_by_role("link", name="Open page").click()
        page.locator(".filepage .file-methods").get_by_role(
            "link", name="Measurements"
        ).click()
        expect(main.locator("h1")).to_have_text("Measurements")
        main.get_by_role("link", name="table.tsv", exact=True).click()
        expect(page.locator(".drawer")).to_be_visible()
        expect(page.locator(".drawer .file-methods")).to_have_count(0)
        page.locator(".drawer").get_by_role("link", name="Close", exact=True).click()
        main.locator(".heading nav").get_by_role("link", name="Methods 1").click()
        main.locator(".method-grid").get_by_role("link", name="Source images").click()
        expect(main.locator("h1")).to_have_text("Paired images")


def test_terms_search_keeps_subject_and_property_together(page, tmp_path):
    (tmp_path / "metadata.yaml").write_text("""
catalogue:
  project:
    pid: urn:example:terms
    term_vocabulary:
      - {id: 'urn:nucleus', label: Nucleus, role: subject, category: Compartment, aliases: [nuclear]}
      - {id: 'urn:envelope', label: Nuclear envelope, role: subject, category: Compartment}
      - {id: 'urn:vacuole', label: Vacuole, role: subject, category: Compartment}
      - {id: 'urn:size', label: Size, role: property}
      - {id: 'urn:volume', label: Volume, role: property, broader: 'urn:size'}
      - {id: 'urn:location', label: Location, role: property, aliases: [position]}
  publications:
    - pid: urn:paper:volume
      title: Volume paper
      source_url: https://doi.org/10.1234/volume
      index_terms: [{subject: 'urn:nucleus', term: 'urn:volume', note: Table 1.}]
      dataset_links: [{dataset: 'urn:data:volume', role: describes}]
    - pid: urn:paper:spatial
      title: Spatial paper
      index_terms:
        - {subject: 'urn:nucleus', term: 'urn:location'}
        - {subject: 'urn:vacuole', term: 'urn:volume'}
      dataset_links: [{dataset: 'urn:data:volume', role: reuses}]
  datasets:
    - pid: urn:data:volume
      title: Volume table
      index_terms: [{subject: 'urn:nucleus', property: 'urn:volume', note: Measured in 3D.}]
    - pid: urn:data:envelope
      title: Envelope image
      index_terms: [{subject: 'urn:envelope', term: 'urn:location'}]
    - pid: urn:data:plain
      title: General keywords
      keywords: [Nucleus, Volume]
    - pid: urn:data:separate
      title: Independent terms
      index_terms: [{term: 'urn:nucleus'}, {property: 'urn:volume'}]
    - pid: urn:data:atlas
      title: Nucleus atlas
      characterized_by: [{predicate: 'http://purl.org/dc/terms/subject', object: 'urn:nucleus'}]
""")
    (tmp_path / ".studyminimeta.yaml").write_text(
        "publication: [{title: Alternate title, doi: 10.1234/volume, keyword: [Morphometry]}]\n"
    )
    with serve_project(tmp_path) as root:
        page.goto(root + "#section=terms", wait_until="domcontentloaded")
        papers = page.get_by_role("region", name="Matching papers")
        datasets = page.get_by_role("region", name="Matching datasets")
        search = page.get_by_role("searchbox", name="Search terms")

        def query(text):
            search.fill(text)
            search.press("Enter")

        query("NuClEaR volume")
        expect(papers.locator(".result-title")).to_have_text(["Volume paper"])
        expect(datasets.locator(".result-title")).to_have_text(["Volume table"])
        query("nucleus size or location")
        expect(papers.locator(".result-title")).to_have_text(
            ["Spatial paper", "Volume paper"]
        )
        expect(datasets.locator(".result-title")).to_have_text(["Volume table"])
        query("nuclear position")
        expect(papers.locator(".result-title")).to_have_text(["Spatial paper"])
        expect(datasets).to_contain_text("No matching datasets")
        query("nuclear envelope position")
        expect(datasets.locator(".result-title")).to_have_text(["Envelope image"])
        query("Morphometry")
        expect(papers.locator(".result-title")).to_have_text(["Volume paper"])
        query("unindexed")
        expect(papers).to_contain_text("No matching papers")

        page.get_by_role("link", name="Clear filters").click()
        compartment = page.get_by_role("combobox", name="Compartment", exact=True)
        prop = page.get_by_role("combobox", name="Property", exact=True)
        compartment.select_option("urn:nucleus")
        expect(datasets.locator(".result-title")).to_have_text(
            ["Independent terms", "Nucleus atlas", "Volume table"]
        )
        prop.select_option("urn:size")
        expect(papers.locator(".result-title")).to_have_text(["Volume paper"])
        expect(datasets.locator(".result-title")).to_have_text(["Volume table"])
        bookmark = page.url
        datasets.get_by_role("link", name="Volume table").click()
        expect(page.locator(".study main .record-terms")).to_contain_text(
            "Measured in 3D."
        )
        page.go_back()
        expect(datasets.locator(".result-title")).to_have_text(["Volume table"])
        assert page.url == bookmark
        papers.locator(".result-title").click()
        expect(page.locator(".study main .record-terms")).to_contain_text("Table 1.")
        record_terms = page.locator(".study main .record-terms")
        expect(record_terms.locator("dt")).to_have_text(
            ["Compartment", "Property", "Keyword"]
        )
        record_terms.get_by_role("link", name="Nucleus", exact=True).click()
        expect(compartment).to_have_value("urn:nucleus")
        expect(prop).to_have_value("")
        expect(datasets.locator(".result-title")).to_have_count(3)
        page.go_back()
        record_terms.get_by_role("link", name="Volume", exact=True).click()
        expect(compartment).to_have_value("")
        expect(prop).to_have_value("urn:volume")
        expect(papers.locator(".result-title")).to_have_text(
            ["Spatial paper", "Volume paper"]
        )
        expect(datasets.locator(".result-title")).to_have_text(
            ["Independent terms", "Volume table"]
        )
        page.go_back()
        record_terms.get_by_role(
            "link", name="Find records for Nucleus and Volume"
        ).click()
        expect(compartment).to_have_value("urn:nucleus")
        expect(prop).to_have_value("urn:volume")
        expect(papers.locator(".result-title")).to_have_text(["Volume paper"])
        expect(datasets.locator(".result-title")).to_have_text(["Volume table"])

        page.locator(".study header nav").get_by_role("link", name="Papers 2").click()
        sidebar = page.locator(".study .layout > aside")
        sidebar.get_by_role("searchbox").fill("nucleus size")
        expect(sidebar.locator("a.row b")).to_have_text(["Volume paper"])
        sidebar.get_by_role("searchbox").fill("")
        expect(sidebar.locator("a.row b")).to_have_count(2)
        general = page.get_by_role("searchbox", name="Search papers, datasets, files")
        general.fill("nuclear volume")
        general.press("Enter")
        expect(sidebar.locator("a.row b")).to_have_text(["Volume paper"])
        page.locator(".study header nav").get_by_role("link", name="Datasets 5").click()
        expect(sidebar.locator("a.row b")).to_have_text(["Volume table"])
        page.goto(
            root
            + "#section=papers&record=metadata.yaml&entry=urn:paper:volume&view=datasets"
        )
        page.locator(".study .subtabs").get_by_role("link", name="Terms 2").click()
        expect(page.locator(".split .record-terms")).to_contain_text("Measured in 3D.")
        page.goto(root + "#section=terms&term=keyword%2Fmorphometry")
        expect(page.get_by_role("combobox", name="Keyword")).to_have_value(
            "keyword/morphometry"
        )
        expect(prop).to_have_value("")
        prop.select_option("urn:volume")
        expect(papers.locator(".result-title")).to_have_text(["Volume paper"])
        expect(datasets.locator(".result-title")).to_have_count(0)
