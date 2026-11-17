import json
from pathlib import Path
from unittest.mock import patch

import pytest
import yaml
from streamlit.testing.v1 import AppTest

from shacl_py.catalogue import SCHEMAS
from shacl_py.cli import main
from shacl_py.native import MetadataSource
from shacl_py.records import load_records


def snapshot(folder):
    return {
        p.relative_to(folder): p.read_bytes() for p in folder.rglob("*") if p.is_file()
    }


def test_readme_is_only_a_listed_file(tmp_path, monkeypatch):
    paper = tmp_path / "collection/record-123"
    paper.mkdir(parents=True)
    review = "# Notes on the experiment\n\nA reviewer's opinion.\nDOI: 10.1234/other\n"
    (paper / "README.md").write_text(review)
    (tmp_path / "README.md").write_text(review)
    open_file = Path.open

    def open_source(path, *args, **kwargs):
        assert path.name != "README.md", "metadata code read review notes"
        return open_file(path, *args, **kwargs)

    monkeypatch.setattr(Path, "open", open_source)
    assert load_records(tmp_path) == ([], [])
    args = [
        "setup",
        str(tmp_path),
        "--template",
        "paper-review",
        "--papers-folder",
        "collection",
        "--no-input",
    ]
    assert main(args) == 0
    graph = yaml.safe_load((tmp_path / "metadata.yaml").read_text())["catalogue"]
    (paper_record,) = graph["publications"]
    for record in (graph["project"], paper_record):
        assert {"title", "display_label", "description", "source_url"}.isdisjoint(
            record
        )
    assert paper_record["file_groups"] == [
        {"label": "Review notes", "paths": ["README.md"]}
    ]
    monkeypatch.setenv("SHACL_PY_ROOT", str(tmp_path))
    page = AppTest.from_file(str(SCHEMAS.parent / "app.py")).run()
    page.tabs[0].button[0].click().run()
    assert not page.exception and page.title[0].value == paper_record["pid"]


def test_study_file_direct_and_previously_saved_title(tmp_path, monkeypatch):
    (tmp_path / "README.md").write_text("# Misleading heading")
    study = tmp_path / ".studyminimeta.yaml"
    study.write_text("""dataset:
  name: Collected readings
publication:
  - {title: First declared paper, doi: 10.1234/first}
  - {title: Second declared paper, doi: 10.1234/second}
person: {}
""")
    before = snapshot(tmp_path)
    records, errors = load_records(tmp_path)
    assert not errors and len(records) == 1
    assert records[0].content == yaml.safe_load(study.read_text())
    assert [kind for kind, _ in records[0].entries] == [
        "Dataset",
        "Publication",
        "Publication",
    ]
    assert main(["validate", str(study)]) == 0
    monkeypatch.setenv("SHACL_PY_ROOT", str(tmp_path))
    page = AppTest.from_file(str(SCHEMAS.parent / "app.py")).run()
    assert not page.exception
    assert {"Collected readings", "First declared paper", "Second declared paper"} <= {
        m.value for m in page.markdown
    }
    assert before == snapshot(tmp_path)

    catalogue = tmp_path / "metadata.yaml"
    catalogue.write_text(
        "pid: 'urn:example:old'\ndisplay_label: Review folder heading\nlocal_folder: .\nreview_status: unreviewed\n"
    )
    assert load_records(tmp_path)[0][0].content == records[0].content
    catalogue.write_text(
        "catalogue: {project: {pid: 'urn:example:project', title: Saved title}}\n"
    )
    assert load_records(tmp_path)[0][0].data["title"] == "Saved title"
    assert load_records(study)[0][0].content == records[0].content
    assert snapshot(tmp_path) == before | {
        Path("metadata.yaml"): catalogue.read_bytes()
    }


def test_multiple_articles_leave_title_unset_on_import(tmp_path):
    paper = tmp_path / "sources/paper"
    paper.mkdir(parents=True)
    (paper / "project.json").write_text('{"title": "Project name"}')
    (paper / "metalad.json").write_text(
        json.dumps(
            {
                "extracted_metadata": {
                    "name": "Metadata collection",
                    "@graph": [
                        {"@type": "ScholarlyArticle", "headline": "First paper"},
                        {"@type": "ScholarlyArticle", "headline": "Second paper"},
                    ],
                }
            }
        )
    )
    assert (
        main(
            [
                "setup",
                str(tmp_path),
                "--template",
                "paper-review",
                "--papers-folder",
                "sources",
                "--no-input",
            ]
        )
        == 0
    )
    (paper_record,) = yaml.safe_load((tmp_path / "metadata.yaml").read_text())[
        "catalogue"
    ]["publications"]
    assert "title" not in paper_record


def test_legacy_command_reads_declared_publication_title(tmp_path):
    (tmp_path / ".studyminimeta.yaml").write_text(
        "publication: [{title: Recorded title, doi: '10.1234/title'}]\nperson: {}\n"
    )
    (tmp_path / "README.md").write_text("# Something else")
    assert main(["init", str(tmp_path)]) == 0
    record = yaml.safe_load((tmp_path / "metadata.yaml").read_text())
    assert record["display_label"] == "Recorded title"
    assert record["source_url"] == "https://doi.org/10.1234/title"


def test_typed_metadata_files_and_search(tmp_path, monkeypatch):
    item = tmp_path / "metadata.yaml"
    item.write_text("pid: 'urn:example:instrument'\ntitle: Instrument settings\n")
    sub = tmp_path / "notes"
    sub.mkdir()
    path = sub / "paper.json"
    path.write_text(
        json.dumps({"title": "Explicit paper title", "keywords": ["trial"]})
    )
    before = snapshot(tmp_path)
    records, errors = load_records(tmp_path)
    assert not errors and all(isinstance(r, MetadataSource) for r in records)
    assert {r.label for r in records} == {"Instrument settings", "Explicit paper title"}
    monkeypatch.setenv("SHACL_PY_ROOT", str(tmp_path))
    page = AppTest.from_file(str(SCHEMAS.parent / "app.py")).run()
    page.text_input[0].set_value("Explicit").run()
    page.button[0].click().run()
    assert not page.exception and page.title[0].value == "Explicit paper title"
    assert json.loads(page.json[0].value)["keywords"] == ["trial"]
    assert snapshot(tmp_path) == before
    item.write_text("pid: 'urn:example:instrument'\nunknown_slot: invalid\n")
    assert str(item) in load_records(tmp_path)[1][0]


def test_live_metalad_and_export_keep_distinct_entities(tmp_path):
    (tmp_path / ".datalad").mkdir()
    (tmp_path / ".datalad/config").touch()
    payload = {
        "@graph": [
            {"@type": "Dataset", "name": "Stored data"},
            {"@list": [{"@type": "ScholarlyArticle", "headline": "Stored paper"}]},
        ]
    }
    exported = {
        "type": "dataset",
        "extractor_name": "example",
        "extracted_metadata": payload,
    }
    ignored = {
        "type": "file",
        "path": "README.md",
        "extracted_metadata": {"title": "Review notes"},
    }
    with patch(
        "datalad.api.meta_dump",
        side_effect=lambda **_: iter([{"metadata": exported}, {"metadata": ignored}]),
    ):
        records, errors = load_records(tmp_path)
        assert not errors and records[0].content == [exported]
        (tmp_path / "metalad.json").write_text(json.dumps(exported))
        file_record = load_records(tmp_path)[0][0]
        assert file_record.entries == records[0].entries
        assert load_records(tmp_path, metalad=True)[0][0].content == [exported]
        assert main(["validate", str(tmp_path), "--metalad"]) == 0


def test_view_real_store_without_metadata_files(tmp_path, monkeypatch):
    from datalad.api import create, meta_add

    monkeypatch.setenv("GIT_CONFIG_COUNT", "2")
    for i, (key, value) in enumerate(
        (("user.name", "Viewer test"), ("user.email", "test@example.org"))
    ):
        monkeypatch.setenv(f"GIT_CONFIG_KEY_{i}", key)
        monkeypatch.setenv(f"GIT_CONFIG_VALUE_{i}", value)
    root = tmp_path / "observations"
    dataset = create(path=str(root), annex=False, result_renderer="disabled")
    meta_add(
        {
            "type": "dataset",
            "dataset_id": dataset.id,
            "dataset_version": dataset.repo.get_hexsha(),
            "extractor_name": "example",
            "extractor_version": "1",
            "extraction_parameter": {},
            "extraction_time": 1700000000.0,
            "agent_name": "Viewer test",
            "agent_email": "test@example.org",
            "extracted_metadata": {
                "@graph": [
                    {"@type": "Dataset", "name": "Observations"},
                    {"@type": "ScholarlyArticle", "headline": "Measured process"},
                ]
            },
        },
        dataset=dataset,
        result_renderer="disabled",
    )
    before = snapshot(root)
    monkeypatch.setenv("SHACL_PY_ROOT", str(root))
    page = AppTest.from_file(str(SCHEMAS.parent / "app.py")).run()
    assert not page.exception and {"Observations", "Measured process"} <= {
        m.value for m in page.markdown
    }
    assert snapshot(root) == before


@pytest.mark.parametrize(
    "name,contents",
    [
        ("metalad.json", "invalid JSON"),
        (".studyminimeta.yaml", "dataset: invalid"),
        ("project.json", "123"),
        ("paper.json", "[1]"),
    ],
)
def test_invalid_source_reports_file(tmp_path, name, contents):
    path = tmp_path / name
    path.write_text(contents)
    assert str(path) in load_records(tmp_path)[1][0]
    assert main(["validate", str(path)]) == 1
