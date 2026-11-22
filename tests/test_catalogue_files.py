import pytest
import yaml

from shacl_py.cli import main
from shacl_py.records import load_records


def test_linked_files_are_one_catalogue_and_edits_keep_their_owner(tmp_path):
    root = tmp_path / "metadata.yaml"
    folder = tmp_path / "papers" / "survey"
    folder.mkdir(parents=True)
    paper = folder / "catalogue.yaml"
    data = tmp_path / "datasets.yaml"
    root.write_text(
        "catalogue:\n  project: {pid: 'urn:test:project'}\n  includes:\n"
        "  - papers/survey/catalogue.yaml\n  - datasets.yaml\n"
    )
    paper.write_text(
        "publications:\n- pid: urn:test:paper\n  local_folder: papers/survey\n"
        "  dataset_links:\n  - {dataset: 'urn:test:data', role: reuses}\n"
    )
    data.write_text("datasets:\n- pid: urn:test:data\n")
    before = root.read_bytes(), data.read_bytes()
    assert main(["validate", str(root)]) == 0
    records, errors = load_records(tmp_path)
    assert not errors
    assert len(records) == 1
    assert (
        records[0].graph["publications"][0]["dataset_links"][0]["dataset"]
        == "urn:test:data"
    )

    args = [
        "add-datasets",
        "--project",
        str(tmp_path),
        "--paper",
        "papers/survey",
        "--dataset",
        "New observations",
        "https://example.org/data",
    ]
    assert main(args) == 0
    updated = paper.read_bytes()
    part = yaml.safe_load(updated)
    assert part["datasets"][0]["title"] == "New observations"
    assert (
        part["publications"][0]["dataset_links"][-1]["dataset"]
        == part["datasets"][0]["pid"]
    )
    assert main(args) == 0
    assert paper.read_bytes() == updated
    assert (root.read_bytes(), data.read_bytes()) == before
    assert main(["setup", str(tmp_path), "--title", "Renamed", "--no-input"]) == 0
    assert yaml.safe_load(root.read_bytes())["catalogue"] == {
        "project": {"pid": "urn:test:project", "title": "Renamed"},
        "includes": ["papers/survey/catalogue.yaml", "datasets.yaml"],
    }

    data.write_text("datasets:\n- pid: urn:test:paper\n")
    assert "duplicate pid" in load_records(tmp_path)[1][0]


@pytest.mark.parametrize(
    ("includes", "error"),
    [
        (["missing.yaml"], "missing.yaml"),
        (["../other.yaml"], "relative path"),
        (["metadata.yaml"], "self-referencing"),
        (["part.yaml", "./part.yaml"], "repeated"),
        ("part.yaml", "must be a list"),
    ],
)
def test_invalid_catalogue_include_reports_its_path(tmp_path, includes, error):
    (tmp_path / "part.yaml").write_text("publications: []\n")
    (tmp_path / "metadata.yaml").write_text(
        yaml.safe_dump(
            {"catalogue": {"project": {"pid": "urn:test:p"}, "includes": includes}}
        )
    )
    records, errors = load_records(tmp_path)
    assert not records
    assert error in errors[0]
