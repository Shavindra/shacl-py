import json
import shutil

import pytest
import yaml

from shacl_py.cli import main
from shacl_py.collection import CONFIG, load_collections
from shacl_py.records import load_records


@pytest.fixture
def bundle(tmp_path):
    template = tmp_path / "station-template"
    template.mkdir()
    (template / "template.yaml").write_text(
        "id: stations\ntitle: Survey stations\nschema: stations.json\n"
        "example: example.yaml\nlinkml: stations.linkml.yaml\nrecords: sites\n"
        "id_field: code\nlabel_field: label\nfield_labels: {depth: Depth (m)}\n"
    )
    (template / "stations.linkml.yaml").write_text("name: stations\n")
    (template / "example.yaml").write_text("sites: [{code: A, label: Harbour}]\n")
    (template / "stations.json").write_text(
        json.dumps(
            {
                "$schema": "https://json-schema.org/draft/2020-12/schema",
                "type": "object",
                "required": ["sites"],
                "properties": {
                    "sites": {"type": "array", "items": {"$ref": "#/$defs/site"}},
                    "year": {"type": "integer"},
                },
                "$defs": {
                    "site": {
                        "type": "object",
                        "required": ["code", "label"],
                        "properties": {"depth": {"type": "number"}},
                    }
                },
            }
        )
    )
    return template


def test_external_template_preserves_data_and_can_be_reused(tmp_path, bundle):
    project = tmp_path / "project"
    (project / ".shacl-py").mkdir(parents=True)
    config = project / CONFIG
    config.write_text("# identity\napp_name: Survey\n")
    data = project / "sites.yaml"
    original = "# measured sites\nsites: [{code: B, label: Marsh}]\n"
    data.write_text(original)
    args = ["setup", str(project), "--template", str(bundle), "--data", "sites.yaml"]
    assert main(args) == 0
    saved = config.read_text()
    assert "# identity" in saved and "app_name: Survey" in saved
    assert main(args) == 0
    assert config.read_text() == saved and data.read_text() == original
    assert not (project / "metadata.yaml").exists()
    installed = project / ".shacl-py/templates/stations"
    assert {p.name for p in installed.iterdir()} == {p.name for p in bundle.iterdir()}
    shutil.rmtree(bundle)
    assert main(["validate", str(project)]) == 0
    assert main(["validate", str(data)]) == 0
    settings = yaml.safe_load(saved)
    settings["collections"]["east"] = {
        "template": ".shacl-py/templates/stations/template.yaml",
        "title": "East coast",
        "data": "east.yaml",
    }
    config.write_text(yaml.safe_dump(settings, sort_keys=False))
    (project / "east.yaml").write_text("sites: [{code: B, label: Beach}]")
    collections, errors, _ = load_collections(project)
    assert not errors
    assert [(c.title, c.entries["B"]["label"]) for c in collections] == [
        ("Survey stations", "Marsh"),
        ("East coast", "Beach"),
    ]


def test_template_seeds_only_missing_data(tmp_path, bundle):
    project = tmp_path / "survey"
    project.mkdir()
    installed = bundle.rename(project / "station-template")
    (installed / "example.yaml").rename(installed / "metadata.yaml")
    manifest = installed / "template.yaml"
    manifest.write_text(manifest.read_text().replace("example.yaml", "metadata.yaml"))
    assert main(["setup", str(project), "--template", str(installed)]) == 0
    assert (project / "collections/stations.yaml").read_bytes() == (
        installed / "metadata.yaml"
    ).read_bytes()
    assert not (project / ".shacl-py/templates").exists()
    assert main(["validate", str(project)]) == 0


@pytest.mark.parametrize(
    ("data", "error"),
    [
        ("sites: [{code: B, label: Marsh, depth: deep}]", "$.sites[0].depth"),
        ("sites: []\nyear: past", "$.year"),
        ("sites: [{code: B, label: Marsh}, {code: B, label: Beach}]", "duplicate ID"),
        ("sites: [{code: [], label: Marsh}]", "record [0].code"),
        ("sites: [{code: B, label: 17}]", "record [0].label"),
    ],
)
def test_invalid_existing_data_is_reported_before_install(
    tmp_path, bundle, capsys, data, error
):
    project = tmp_path / "survey"
    project.mkdir()
    (project / "sites.yaml").write_text(data)
    assert (
        main(["setup", str(project), "--template", str(bundle), "--data", "sites.yaml"])
        == 1
    )
    message = capsys.readouterr().err
    assert str(project / "sites.yaml") in message and error in message
    assert not (project / ".shacl-py").exists()
    assert (project / "sites.yaml").read_text() == data


def test_direct_schema_and_partial_failure(tmp_path):
    (tmp_path / ".shacl-py").mkdir()
    (tmp_path / CONFIG).write_text(
        "collections:\n  a: {data: project.json, schema: types.json}\n"
        "  bad: {data: ../elsewhere.yaml, schema: types.json}\n"
    )
    (tmp_path / "project.json").write_text('[{"id": 0, "name": "Zero"}]')
    (tmp_path / "types.json").write_text('{"type": "array"}')
    collections, errors, _ = load_collections(tmp_path)
    assert list(collections[0].entries) == ["0"]
    assert len(errors) == 1 and "project-relative" in errors[0]
    assert main(["validate", str(tmp_path)]) == 1
    assert main(["validate", str(tmp_path / "project.json")]) == 0
    (tmp_path / CONFIG).write_text(
        "collections: {a: {data: project.json, schema: types.json}}"
    )
    sources, errors = load_records(tmp_path)
    assert len(sources) == 1 and not errors
    (tmp_path / "types.json").write_text(
        '{"$ref":"https://example.invalid/unknown.json"}'
    )
    assert main(["validate", str(tmp_path / "project.json")]) == 1


def test_bundled_compartments_template_installs_by_name(tmp_path):
    from shacl_py.collection import bundled_templates

    assert "compartments" in bundled_templates()
    project = tmp_path / "project"
    project.mkdir()
    assert main(["setup", str(project), "--template", "compartments"]) == 0
    installed = project / ".shacl-py/templates/compartments"
    assert (installed / "template.yaml").is_file()
    assert (installed / "compartments.schema.json").is_file()
    assert (project / "collections/compartments.yaml").is_file()
    assert main(["validate", str(project)]) == 0
