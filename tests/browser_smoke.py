"""Exercise the installed viewer in Chromium at desktop and phone widths."""

import os
import shutil
import signal
import subprocess
import sys
import time
from pathlib import Path
from tempfile import TemporaryDirectory
from urllib.error import URLError
from urllib.request import urlopen

from playwright.sync_api import sync_playwright

EXAMPLE = Path(__file__).resolve().parents[1] / "examples/coastal-survey"


def check(browser, width, height, output):
    page = browser.new_page(viewport={"width": width, "height": height})
    page.goto("http://127.0.0.1:18501")
    page.get_by_role("heading", name="Coastal survey", exact=True).wait_for()
    page.screenshot(path=output / f"project-{width}.png")
    assert page.evaluate("document.documentElement.scrollWidth") <= width
    page.get_by_role("button", name="Shoreline field survey").click()
    page.get_by_role("heading", name="Notebooks", exact=True).wait_for()
    page.screenshot(path=output / f"paper-{width}.png")
    page.get_by_role("tab", name="Datasets", exact=True).click()
    page.get_by_role("button", name="Mean reading per station").click()
    page.get_by_role("heading", name="Derived from", exact=True).wait_for()
    page.get_by_role("button", name="Station readings").click()
    page.get_by_role("heading", name="Station readings", exact=True).wait_for()
    page.get_by_role("tab", name="Documentation and metadata").click()
    assert not page.locator('[data-testid="stException"]').count()
    page.close()


def main(cli, output):
    output.mkdir(parents=True, exist_ok=True)
    # Use a disposable copy and verify setup/serving from outside the source tree.
    with TemporaryDirectory() as temp:
        project = Path(temp) / "example"
        shutil.copytree(EXAMPLE, project)
        before = {p: p.read_bytes() for p in project.rglob("*") if p.is_file()}
        process = subprocess.Popen(
            [cli, "serve", project, "--port", "18501"], cwd=temp, start_new_session=True
        )
        try:
            for _ in range(100):
                try:
                    with urlopen(
                        "http://127.0.0.1:18501/_stcore/health", timeout=1
                    ) as response:
                        if response.status == 200:
                            break
                except URLError:
                    if process.poll() is not None:
                        raise RuntimeError(
                            "Viewer exited before it was ready"
                        ) from None
                time.sleep(0.2)
            else:
                raise RuntimeError("Viewer did not start")
            with sync_playwright() as driver:
                browser = driver.chromium.launch(
                    executable_path=os.getenv("CHROME_BIN")
                )
                for width, height in ((1280, 900), (390, 844)):
                    check(browser, width, height, output)
                browser.close()
        finally:
            if process.poll() is None:
                os.killpg(process.pid, signal.SIGTERM)
            process.wait(timeout=15)
        assert before == {p: p.read_bytes() for p in project.rglob("*") if p.is_file()}


if __name__ == "__main__":
    main(sys.argv[1], Path(sys.argv[2]))
