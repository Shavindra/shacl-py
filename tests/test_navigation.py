import os
import socket
import subprocess
import sys
import time
from importlib.resources import files
from pathlib import Path
from urllib.error import URLError
from urllib.parse import parse_qsl, urlsplit
from urllib.request import urlopen

import pytest
from playwright.sync_api import expect, sync_playwright


@pytest.fixture
def viewer_url():
    example = Path(__file__).resolve().parents[1] / "examples/coastal-survey"
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
        env=os.environ | {"SHACL_PY_ROOT": str(example)},
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
