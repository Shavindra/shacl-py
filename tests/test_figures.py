import shutil

import pytest
import yaml
from test_viewer import EXAMPLE, follow, html, open_viewer

from shacl_py.catalogue import validate_catalogue


def test_paper_figures_and_related_data(tmp_path, monkeypatch):
    root = tmp_path / "example"
    shutil.copytree(EXAMPLE, root)
    metadata = root / "metadata.yaml"
    document = yaml.safe_load(metadata.read_text())
    paper = document["catalogue"]["publications"][0]
    paper["figure_source"] = "Field survey supplement"
    paper["figures"] = [
        {
            "label": "Fig. 1",
            "title": "Station comparison",
            "panels": "a–b",
            "highlighted": True,
            "related_datasets": ["urn:example:means"],
        }
    ]
    paper["paper_images"] = [
        {
            "from_figure": "Fig. 1b",
            "caption": "Southern station",
            "url": "https://example.org/station.png",
        }
    ]
    metadata.write_text(yaml.safe_dump(document))
    page = open_viewer(root, monkeypatch)
    body = html(follow(page, "Figures 1"))
    for value in (
        "Field survey supplement",
        "Station comparison",
        "Key figure",
        "a–b",
        "No image available",
        "Images from the paper",
        "Southern station",
        "Fig. 1b",
        'src="https://example.org/station.png"',
    ):
        assert value in body
    body = html(follow(page, "Mean reading per station"))
    assert "station-means.csv" in body
    page.session_state["fragment"] = (
        "record=metadata.yaml&entry=urn:example:protocol&view=figures"
    )
    body = html(page.run())
    assert "No figures recorded for this paper." in body
    assert "Images from the paper" not in body

    paper["figures"][0]["related_datasets"] = ["urn:missing"]
    with pytest.raises(ValueError, match="unknown dataset urn:missing"):
        validate_catalogue(document["catalogue"], root)
