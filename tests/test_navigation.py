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
