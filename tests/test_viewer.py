import json
import shutil
from pathlib import Path
from unittest.mock import patch

import pytest
import yaml
from streamlit.testing.v1 import AppTest

from shacl_py.cli import main
from shacl_py.records import SCHEMAS, discover, load_records, project_files

EXAMPLES = Path(__file__).resolve().parents[1] / "examples"


@pytest.fixture
def root(tmp_path):
    shutil.copytree(EXAMPLES, tmp_path, dirs_exist_ok=True)
    return tmp_path


def test_discovery_and_schema(root):
    records, errors = load_records(root)
    assert not errors
    assert len(records) == 1
    assert records[0].data["display_label"] == "Example paper project"
    ignored = root / ".git" / "metadata.yaml"
    ignored.parent.mkdir()
    ignored.write_text("bad")
    assert len(discover(root)) == 1
    schema = json.loads((SCHEMAS / "paper.schema.json").read_text())
    assert "Paper" in schema["$defs"]


@pytest.mark.parametrize(
    "field,value",
    [
        ("review_status", "invalid"),
        ("display_label", ""),
        ("pid", "not an identifier"),
        ("source_url", "javascript:alert(1)"),
        ("local_folder", "/tmp"),
        ("local_folder", "../../../../.."),
        ("local_folder", "missing"),
        ("description", 42),
    ],
)
def test_invalid_fields(root, field, value):
    path = discover(root)[0]
    data = yaml.safe_load(path.read_text())
    data[field] = value
    path.write_text(yaml.safe_dump(data))
    records, errors = load_records(root)
    assert not records
    assert errors and str(path) in errors[0]


@pytest.mark.parametrize("content", ["[bad", "null", "- list", "unknown: value"])
def test_malformed_metadata(root, content):
    discover(root)[0].write_text(content)
    assert load_records(root)[1]


def test_duplicates_and_symlinks(root):
    source = discover(root)[0]
    other = root / "another"
    other.mkdir()
    shutil.copy(source, other / "metadata.yaml")
    assert "duplicate pid" in load_records(root)[1][0]
    (other / "metadata.yaml").unlink()
    (other / "metadata.yaml").symlink_to(source)
    assert "regular local file" in load_records(root)[1][0]


def test_annex_unavailable_and_no_directory_traversal(root):
    paper = load_records(root)[0][0]
    missing = paper.folder / "data/raw/missing.csv"
    missing.symlink_to("../../../.git/annex/objects/missing")
    (paper.folder / "data/raw/loop").symlink_to(paper.folder, target_is_directory=True)
    rows, _ = project_files(paper)
    assert (
        next(row for row in rows if row["Filename"] == "missing.csv")["Availability"]
        == "Unavailable"
    )
    assert len(rows) == 2


def test_cli_init_validate_and_no_overwrite(tmp_path, capsys):
    paper = tmp_path / "paper"
    assert main(["init", str(paper)]) == 0
    original = (paper / "metadata.yaml").read_bytes()
    assert main(["init", str(paper)]) == 1
    assert (paper / "metadata.yaml").read_bytes() == original
    assert main(["validate", str(tmp_path)]) == 0
    assert main(["validate", str(tmp_path / "missing")]) == 1
    assert "not a directory" in capsys.readouterr().err


def test_serve_arguments(root):
    with patch("shacl_py.cli.subprocess.call", return_value=0) as call:
        assert main(["serve", str(root), "--port", "8510"]) == 0
    args, kwargs = call.call_args
    assert "--server.address=127.0.0.1" in args[0]
    assert "--server.port=8510" in args[0]
    assert kwargs["env"]["SHACL_PY_ROOT"] == str(root)


def test_homepage_navigation_search_and_readonly(root, monkeypatch):
    monkeypatch.setenv("SHACL_PY_ROOT", str(root))
    before = {
        p.relative_to(root): p.read_bytes() for p in root.rglob("*") if p.is_file()
    }
    app = AppTest.from_file(str(SCHEMAS.parent / "app.py")).run()
    assert not app.exception
    assert app.subheader[0].value == "Example paper project"
    app.text_input[0].set_value("no matches").run()
    assert app.info[0].value == "No matching projects."
    app.text_input[0].set_value("").run()
    app.button[0].click().run()
    assert not app.exception
    assert app.header[0].value == "Example paper project"
    assert [tab.label for tab in app.tabs] == ["Data files", "Dataset"]
    assert app.tabs[0].dataframe[0].value["Relative path"].tolist() == [
        "data/raw/example.csv"
    ]
    assert "metadata.yaml" in app.tabs[1].dataframe[0].value["Relative path"].tolist()
    app.button[0].click().run()
    assert not app.exception
    after = {
        p.relative_to(root): p.read_bytes() for p in root.rglob("*") if p.is_file()
    }
    assert before == after


def test_generate_preserves_overrides_and_adds_new_papers(tmp_path):
    first = tmp_path / "paper-one"
    first.mkdir()
    (first / "README.md").write_text(
        "# First paper\n\nObserved shapes.\nDOI: 10.1234/demo\n"
    )
    assert main(["generate", str(tmp_path)]) == 0
    metadata = first / "metadata.yaml"
    data = yaml.safe_load(metadata.read_text())
    assert data["display_label"] == "First paper"
    assert data["source_url"] == "https://doi.org/10.1234/demo"
    data.update(review_status="useful", editorial_notes=["My notes"])
    custom = yaml.safe_dump(data)
    metadata.write_text(custom)
    (tmp_path / "paper-two").mkdir()
    assert main(["generate", str(tmp_path)]) == 0
    assert metadata.read_text() == custom
    records, errors = load_records(tmp_path)
    assert not errors and len(records) == 2


def test_paper_json_overrides_extracted_metadata(tmp_path):
    paper = tmp_path / "example"
    paper.mkdir()
    (paper / "metalad.json").write_text(
        json.dumps(
            {"extracted_metadata": {"title": "Extracted", "doi": "10.1234/demo"}}
        )
    )
    (paper / "paper.json").write_text(
        json.dumps({"display_label": "Curated", "pid": "urn:example:paper"})
    )
    assert main(["generate", str(tmp_path)]) == 0
    records, errors = load_records(tmp_path)
    assert not errors
    data = records[0].data
    assert (data["display_label"], data["pid"], data["source_url"]) == (
        "Curated",
        "urn:example:paper",
        "https://doi.org/10.1234/demo",
    )


def test_generate_queries_metalad_for_dataset(tmp_path):
    config = tmp_path / ".datalad/config"
    config.parent.mkdir()
    config.touch()
    papers = tmp_path / "papers"
    folder = papers / "paper-a"
    folder.mkdir(parents=True)
    (folder / "README.md").write_text("# Fallback")
    entry = {
        "type": "file",
        "path": "papers/paper-a/project.json",
        "extracted_metadata": {
            "title": "Stored title",
            "doi": "10.1234/test",
            "data_file_patterns": ["signals/**/*.dat"],
        },
    }
    with patch("shacl_py.cli.subprocess.run") as query:
        query.return_value.returncode = 0
        query.return_value.stdout = json.dumps(entry)
        assert main(["generate", str(papers)]) == 0
        assert query.call_args.args[0][-4:] == ["meta-dump", "-d", str(tmp_path), "-r"]
    records, errors = load_records(papers)
    assert not errors and records[0].data["display_label"] == "Stored title"
    assert records[0].data["data_file_patterns"] == ["signals/**/*.dat"]
