import pytest
import yaml

from shacl_py.cli import main
from shacl_py.records import load_records, project_files


def make_files(folder, paths):
    for relative in paths:
        path = folder / relative
        path.parent.mkdir(parents=True, exist_ok=True)
        path.touch()


def tab_paths(root):
    records, errors = load_records(root)
    assert not errors and len(records) == 1
    return [
        {row["Relative path"] for row in rows} for rows in project_files(records[0])
    ]


def test_default_tabs_for_an_existing_record(tmp_path):
    make_files(
        tmp_path,
        [
            "data/raw/first.xlsx",
            "data/raw/second.XLSX",
            "data/output/.gitkeep",
            ".studyminimeta.yaml",
            "README.md",
            "analyse.py",
            "notebooks/results.ipynb",
            ".git/objects/private.csv",
        ],
    )
    assert main(["init", str(tmp_path)]) == 0
    assert tab_paths(tmp_path) == [
        {"data/raw/first.xlsx", "data/raw/second.XLSX"},
        {".studyminimeta.yaml", "README.md", "metadata.yaml"},
    ]


def test_generate_custom_rules_preserves_curated_record(tmp_path):
    project = tmp_path / "instruments"
    folder = project / "acquisition"
    make_files(
        folder,
        [
            "signals/run.bin",
            "signals/sub/next.bin",
            "signals/.gitkeep",
            "calibration.txt",
            "signals/README.txt",
            "draft.xlsx",
        ],
    )
    original = """# Curator's record
pid: urn:example:instrument
display_label: "Instrument 1"
local_folder: acquisition
review_status: useful  # checked in person
editorial_notes: [Retain calibration]
"""
    path = project / "metadata.yaml"
    path.write_text(original)
    args = [
        "generate",
        str(tmp_path),
        "--data-glob",
        "signals/**",
        "--data-glob",
        "calibration.txt",
        "--dataset-glob",
        "**/README.txt",
    ]
    assert main(args) == 0
    updated = path.read_text()
    data = yaml.safe_load(updated)
    assert data == yaml.safe_load(original) | {
        "data_file_patterns": ["signals/**", "calibration.txt"],
        "dataset_file_patterns": ["**/README.txt"],
    }
    assert "# Curator's record" in updated and "# checked in person" in updated
    assert tab_paths(project) == [
        {"signals/run.bin", "signals/sub/next.bin", "calibration.txt"},
        {"signals/README.txt"},
    ]
    assert main(args) == 0 and path.read_text() == updated
    assert main(["generate", str(tmp_path)]) == 0 and path.read_text() == updated
    assert main(["generate", str(project), "--single", "--data-glob", "*.xlsx"]) == 0
    assert tab_paths(project) == [{"draft.xlsx"}, {"signals/README.txt"}]


@pytest.mark.parametrize(
    "pattern", ["../*.csv", "a/../b", "/tmp/**", "C:/raw/*", r"raw\*", " "]
)
def test_invalid_patterns_rejected_before_writing(tmp_path, pattern, capsys):
    folder = tmp_path / "project"
    folder.mkdir()
    assert main(["generate", str(tmp_path), "--data-glob", pattern]) != 0
    assert "data_file_patterns" in capsys.readouterr().err
    assert not (folder / "metadata.yaml").exists()


def test_init_imports_rules_and_validate_checks_hand_edits(tmp_path):
    (tmp_path / "project.json").write_text('{"data_file_patterns": ["**/*.dat"]}')
    make_files(tmp_path, ["data.dat", "guide.rst"])
    assert main(["init", str(tmp_path), "--dataset-glob", "guide.rst"]) == 0
    assert tab_paths(tmp_path) == [{"data.dat"}, {"guide.rst"}]
    path = tmp_path / "metadata.yaml"
    record = yaml.safe_load(path.read_text())
    record["data_file_patterns"] = []
    path.write_text(yaml.safe_dump(record))
    assert tab_paths(tmp_path) == [set(), {"guide.rst"}]
    record["data_file_patterns"] = "**/*.csv"
    path.write_text(yaml.safe_dump(record))
    records, errors = load_records(tmp_path)
    assert not records and str(path) in errors[0] and "data_file_patterns" in errors[0]
