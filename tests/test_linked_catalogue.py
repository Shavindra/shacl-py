import json
import shutil
from pathlib import Path
from unittest.mock import patch

import pytest
import yaml
from streamlit.testing.v1 import AppTest

from shacl_py.catalogue import SCHEMAS, validate_catalogue
from shacl_py.cli import main
from shacl_py.files import grouped_files
from shacl_py.metadata_io import MetadataFile, save_metadata
from shacl_py.records import load_records
from shacl_py.study import validate_study

EXAMPLE = Path(__file__).resolve().parents[1] / "examples/coastal-survey"


def graph_at(root):
    return yaml.safe_load((root / "metadata.yaml").read_text())["catalogue"]


def read_tree(root):
    return {
        p.relative_to(root): p.read_bytes()
        for p in root.rglob("*")
        if p.is_file() and not p.is_symlink()
    }


def test_setup_preserves_edits_and_validates_pair(tmp_path):
    folder = tmp_path / "arbitrary [folder]"
    folder.mkdir()
    (folder / "extensionless").touch()
    study = tmp_path / ".studyminimeta.yaml"
    original = """# Curated description
study:
  name: My research
dataset:
  name: Repository data
  keyword: [example]
  description: Curated description.
person: {}
"""
    study.write_text(original)
    args = ["setup", str(tmp_path), "--no-input", "--data-folder", folder.name]
    assert main(args) == 0
    assert "# Curated description" in study.read_text()
    assert yaml.safe_load(study.read_text())["dataset"]["keyword"] == ["example"]
    project = graph_at(tmp_path)["project"]
    assert project["title"] == "My research"
    assert project["description"] == "Curated description."
    assert grouped_files(tmp_path, project)[0][1][0]["Filename"] == "extensionless"
    path = tmp_path / "metadata.yaml"
    path.write_text("# My catalogue\n" + path.read_text())
    state = read_tree(tmp_path)
    assert main(args) == main(["validate", str(tmp_path)]) == 0
    assert read_tree(tmp_path) == state
    assert main([*args, "--title", "Updated"]) == 0
    assert "# My catalogue" in path.read_text()
    result = yaml.safe_load(study.read_text())
    assert result["study"]["name"] == "Updated"
    assert result["dataset"]["name"] == "Repository data"
    assert graph_at(tmp_path)["project"]["pid"] == project["pid"]


def test_legacy_root_preserved(tmp_path):
    assert main(["init", str(tmp_path)]) == 0
    path = tmp_path / "metadata.yaml"
    path.write_text("# Custom\n" + path.read_text())
    legacy = yaml.safe_load(path.read_text())
    assert main(["setup", str(tmp_path), "--no-input"]) == 0
    document = yaml.safe_load(path.read_text())
    graph = document.pop("catalogue")
    assert document == legacy and "# Custom" in path.read_text()
    assert graph["project"]["pid"] == legacy["pid"]
    assert len(load_records(tmp_path)[0]) == 1


def test_import_curated_study_and_legacy_paper(tmp_path):
    paper = tmp_path / "reviews/study-one"
    (paper / "data/raw/run 1").mkdir(parents=True)
    (paper / "notebooks").mkdir()
    (paper / "data/output").mkdir()
    (paper / "README.md").write_text(
        "# Review notes\n\nPaper ID: demo, metadata is in .studyminimeta.yaml"
    )
    (paper / "data/raw/run 1/output").touch()
    (paper / "data/output/plot.svg").touch()
    (paper / "notebooks/analysis.ipynb").touch()
    assert main(["init", str(paper)]) == 0
    path = paper / "metadata.yaml"
    path.write_text(path.read_text().replace("unreviewed", "useful  # manual review"))
    (paper / ".studyminimeta.yaml").write_text("""
dataset:
  name: Curated dataset
  description: Recorded measurements.
  location: https://example.org/data
  author: [researcher]
person:
  researcher: {given_name: Example, last_name: Author}
publication:
  - {title: Actual publication title, doi: 10.1234/paper, author: [researcher]}
""")
    original = read_tree(paper)
    args = [
        "setup",
        str(tmp_path),
        "--template",
        "paper-review",
        "--papers-folder",
        "reviews",
        "--no-input",
    ]
    assert main(args) == 0
    graph = graph_at(tmp_path)
    (pub,) = graph["publications"]
    (dataset,) = graph["datasets"]
    assert pub["title"] == "Actual publication title" and "description" not in pub
    assert pub["source_url"] == "https://doi.org/10.1234/paper"
    assert dataset["source_url"] == "https://example.org/data"
    assert dataset["description"] == "Recorded measurements."
    assert dataset["author_names"] == pub["author_names"] == ["Example Author"]
    assert graph["reviews"] == [{"publication": pub["pid"], "status": "useful"}]
    assert [g["label"] for g, _ in grouped_files(tmp_path, pub)] == [
        "Review notes",
        "Notebooks",
        "Raw data",
        "Analysis outputs",
    ]
    assert grouped_files(tmp_path, dataset)[0][1][0]["Relative path"] == "run 1/output"
    assert len(load_records(tmp_path)[0]) == 1
    state = read_tree(tmp_path)
    assert main(args) == 0
    assert state == read_tree(tmp_path) and read_tree(paper) == original


def test_setup_nested_project_writes_study_at_dataset_root(tmp_path):
    (tmp_path / ".datalad").mkdir()
    (tmp_path / ".datalad/config").touch()
    project = tmp_path / "one"
    project.mkdir()
    with patch("shacl_py.setup.stored_metadata", return_value={}):
        assert (
            main(["setup", str(project), "--title", "Nested project", "--no-input"])
            == 0
        )
    assert not (project / ".studyminimeta.yaml").exists()
    assert (project / "metadata.yaml").exists()
    assert (
        "name"
        not in yaml.safe_load((tmp_path / ".studyminimeta.yaml").read_text())["dataset"]
    )


def test_prompts_make_shared_and_derived_records(tmp_path, monkeypatch):
    source = tmp_path / "observations"
    source.mkdir()
    output = tmp_path / "results"
    output.mkdir()
    (output / "result.csv").touch()
    (output / "preview.png").touch()
    (tmp_path / "method.ipynb").touch()
    answers = {
        "Paper to add": iter(["First paper", "Second paper", "Third paper", ""]),
        "Dataset this paper": iter(["Shared readings", "", "1", "", ""]),
        "Relationship": iter(["describes", "reuses"]),
        "Derived dataset to": iter(["My results", "", "", ""]),
        "Local dataset file": iter(["observations", "results/result.csv", ""]),
        "Source dataset number": iter(["1", ""]),
        "Notebook used": iter(["method.ipynb"]),
    }

    def reply(message):
        for label, values in answers.items():
            if message.startswith(label):
                return next(values)
        return ""

    monkeypatch.setattr("builtins.input", reply)
    assert main(["setup", str(tmp_path), "--template", "paper-review"]) == 0
    graph = graph_at(tmp_path)
    first, second, third = graph["publications"]
    source, derived = graph["datasets"]
    assert first["dataset_links"] == [{"dataset": source["pid"], "role": "describes"}]
    assert second["dataset_links"] == [{"dataset": source["pid"], "role": "reuses"}]
    assert not third.get("dataset_links")
    assert graph["reviews"][0]["outputs"] == [derived["pid"]]
    assert derived["source_datasets"] == [source["pid"]]
    assert derived["notebook_path"] == "method.ipynb"
    assert [
        r["Filename"] for _, rows in grouped_files(tmp_path, derived) for r in rows
    ] == ["result.csv"]


def test_setup_does_not_save_invalid_or_cancelled_input(tmp_path, monkeypatch, capsys):
    assert (
        main(["setup", str(tmp_path), "--data-folder", "../other", "--no-input"]) == 1
    )
    assert not read_tree(tmp_path)
    monkeypatch.setattr("builtins.input", lambda _: (_ for _ in ()).throw(EOFError()))
    assert main(["setup", str(tmp_path)]) == 1
    assert not read_tree(tmp_path)
    study = tmp_path / ".studyminimeta.yaml"
    study.write_text("person: {a: {given_name: Demo}}\n")
    assert main(["setup", str(tmp_path), "--no-input"]) == 1
    assert "last_name" in capsys.readouterr().err
    assert list(read_tree(tmp_path)) == [Path(".studyminimeta.yaml")]


def test_write_detects_a_concurrent_update_and_rolls_back(tmp_path, monkeypatch):
    a, b = (MetadataFile.read(tmp_path / name) for name in ("a.yaml", "b.yaml"))
    a.data["title"] = b.data["title"] = "first"
    save_metadata(a, b)
    a, b = MetadataFile.read(a.path), MetadataFile.read(b.path)
    a.data["title"] = b.data["title"] = "second"
    old_b = b.path.read_text()
    b.path.write_text("# Edited while prompting\n" + old_b)
    original = read_tree(tmp_path)
    with pytest.raises(ValueError, match="changed during setup"):
        save_metadata(a, b)
    assert read_tree(tmp_path) == original
    b = MetadataFile.read(b.path)
    b.data["title"] = "second"
    replace = Path.replace

    def fail_second(path, target):
        if target == b.path:
            raise OSError("failed write")
        return replace(path, target)

    monkeypatch.setattr(Path, "replace", fail_second)
    with pytest.raises(OSError):
        save_metadata(a, b)
    assert read_tree(tmp_path) == original


@pytest.fixture
def coastal(tmp_path):
    shutil.copytree(EXAMPLE, tmp_path, dirs_exist_ok=True)
    return tmp_path


@pytest.mark.parametrize(
    "damage",
    [
        "unknown paper",
        "unknown dataset",
        "source cycle",
        "duplicate ID",
        "escape",
        "wrong type",
    ],
)
def test_linked_validation_reports_field_and_file(coastal, damage, capsys):
    path = coastal / "metadata.yaml"
    graph = graph_at(coastal)
    if damage == "unknown paper":
        graph["reviews"][0]["publication"] = "urn:bad:missing"
    elif damage == "unknown dataset":
        graph["publications"][0]["dataset_links"][0]["dataset"] = "urn:bad:missing"
    elif damage == "source cycle":
        graph["datasets"][0]["source_datasets"] = [graph["datasets"][1]["pid"]]
    elif damage == "duplicate ID":
        graph["project"]["pid"] = graph["publications"][0]["pid"]
    elif damage == "escape":
        graph["publications"][0]["file_groups"][0]["paths"] = ["../../../outside"]
    else:
        graph["datasets"][0]["file_groups"][0]["paths"] = "wrong"
    path.write_text(yaml.safe_dump({"catalogue": graph}))
    assert main(["validate", str(coastal)]) == 1
    assert str(path) in capsys.readouterr().err


def test_declared_groups_handle_annex_without_following_directories(coastal):
    graph = graph_at(coastal)
    paper = graph["publications"][0]
    base = coastal / paper["local_folder"]
    raw = base / "data/raw"
    (raw / "missing").symlink_to("../../../.git/annex/objects/missing")
    (raw / ".gitkeep").touch()
    (raw / "loop").symlink_to(base, target_is_directory=True)
    rows = {g["label"]: rows for g, rows in grouped_files(coastal, paper)}
    assert {r["Filename"]: r["Availability"] for r in rows["Raw data"]} == {
        "readings.csv": "Available",
        "missing": "Unavailable",
    }
    paper["file_groups"][0]["paths"] = ["data/raw/loop/notebooks"]
    with pytest.raises(ValueError, match="symlink"):
        validate_catalogue(graph, coastal)


def test_real_studyminimeta_converter_accepts_generated_file(tmp_path):
    from datalad_metalad.extractors.studyminimeta.ldcreator import LDCreator

    assert (
        main(["setup", str(tmp_path), "--title", "Recorded study", "--no-input"]) == 0
    )
    path = tmp_path / ".studyminimeta.yaml"
    result = LDCreator("dataset-id", "commit", path.name).create_ld_from_spec(
        yaml.safe_load(path.read_text())
    )
    assert result.success
    assert (
        next(
            d["name"]
            for d in result.json_ld_object["@graph"]
            if d.get("@type") == "Dataset"
        )
        == graph_at(tmp_path)["project"]["title"]
    )
    with pytest.raises(ValueError, match="dataset.author"):
        validate_study({"dataset": {"author": "name"}, "person": {}}, path)


def test_linked_views_and_read_only_navigation(coastal, monkeypatch):
    monkeypatch.setenv("SHACL_PY_ROOT", str(coastal))
    before = read_tree(coastal)
    app = AppTest.from_file(str(SCHEMAS.parent / "app.py")).run()
    assert not app.exception
    assert app.title[0].value == "Coastal survey"
    assert [tab.label for tab in app.tabs] == ["Papers", "Datasets", "Files"]
    app.text_input[0].set_value("useful").run()
    assert [b.label for b in app.tabs[0].button] == ["Shoreline field survey"]
    app.tabs[0].button[0].click().run()
    assert [tab.label for tab in app.tabs] == ["Files", "Datasets"]
    assert [h.value for h in app.tabs[0].subheader] == [
        "Review notes",
        "Notebooks",
        "Raw data",
        "Analysis outputs",
    ]
    assert app.tabs[0].dataframe[1].value["Filename"].tolist() == ["summary.ipynb"]
    app.tabs[1].button[1].click().run()
    assert app.title[0].value == "Mean reading per station"
    assert [tab.label for tab in app.tabs] == [
        "Data files",
        "Documentation and metadata",
    ]
    next(b for b in app.button if b.label == "Station readings").click().run()
    assert len(app.expander[0].button) == 2
    assert not app.exception
    assert read_tree(coastal) == before


def test_metalad_json_ld_defaults_and_file_specific_yaml_errors(tmp_path):
    payload = {
        "extracted_metadata": {
            "@graph": [{"@type": "Dataset", "name": "Station network"}]
        }
    }
    (tmp_path / "metalad.json").write_text(json.dumps(payload))
    assert main(["setup", str(tmp_path), "--no-input"]) == 0
    assert graph_at(tmp_path)["project"]["title"] == "Station network"
    (tmp_path / ".studyminimeta.yaml").write_text("person: false\n")
    assert main(["validate", str(tmp_path)]) == 1


def test_unlocked_annex_pointer_and_large_file_listing(coastal, monkeypatch):
    (coastal / ".git").mkdir()
    pub = graph_at(coastal)["publications"][0]
    raw = coastal / pub["local_folder"] / "data/raw"
    pointer = raw / "unavailable"
    pointer.write_bytes(b"/annex/objects/SHA256-s1--0123456789\r\n")
    (raw / "actual-data").write_bytes(b"/annex/objects/example\nextra ordinary text\n")
    # A sparse large input must be listed using stat alone.
    large = raw / "large"
    with large.open("wb") as stream:
        stream.truncate(1_000_000_000)
    normal_open = Path.open

    def reject_large(path, *args, **kwargs):
        assert path != large
        return normal_open(path, *args, **kwargs)

    monkeypatch.setattr(Path, "open", reject_large)
    rows = {
        row["Filename"]: row["Availability"]
        for group, files in grouped_files(coastal, pub)
        if group["label"] == "Raw data"
        for row in files
    }
    assert rows == {
        "unavailable": "Unavailable",
        "actual-data": "Available",
        "readings.csv": "Available",
        "large": "Available",
    }


def test_repair_moved_folder_and_yaml_keyword_title(tmp_path):
    original = tmp_path / "before"
    original.mkdir()
    args = ["setup", str(tmp_path), "--no-input", "--title", "On", "--data-folder"]
    assert main([*args, "before"]) == 0
    original.rename(tmp_path / "after")
    assert main([*args, "after"]) == 0
    project = graph_at(tmp_path)["project"]
    assert project["title"] == "On"
    assert project["file_groups"][0]["paths"] == ["after"]


def test_distinct_paper_and_dataset_in_metalad_export(tmp_path):
    folder = tmp_path / "collection/p1"
    folder.mkdir(parents=True)
    payload = {
        "extracted_metadata": {
            "@graph": [
                {
                    "@type": "Dataset",
                    "name": "Measurements",
                    "url": "https://example.org/dataset",
                },
                {
                    "@list": [
                        {
                            "@type": "ScholarlyArticle",
                            "headline": "Research article",
                            "sameAs": "10.1234/paper",
                        }
                    ]
                },
            ]
        }
    }
    (folder / "metalad.json").write_text(json.dumps(payload))
    assert (
        main(
            [
                "setup",
                str(tmp_path),
                "--template",
                "paper-review",
                "--papers-folder",
                "collection",
                "--no-input",
            ]
        )
        == 0
    )
    pub = graph_at(tmp_path)["publications"][0]
    assert (pub["title"], pub["source_url"]) == (
        "Research article",
        "https://doi.org/10.1234/paper",
    )
