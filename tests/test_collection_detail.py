import base64

import yaml
from test_viewer import follow, html, open_viewer

from shacl_py.collection import load_collections
from shacl_py.collection_view import detail_view


def project(root):
    settings = root / ".shacl-py"
    settings.mkdir()
    view = {
        "starred": "flag",
        "terms": {"field": "codes", "label": "Site", "definition": "definition"},
        "variants": {
            "field": "surveys",
            "id_field": "sample",
            "group_field": "campaign",
            "label_field": "label",
            "label": "Campaign",
            "plural": "campaigns",
            "context_fields": ["season"],
        },
        "overview": ["depth"],
        "references": "citations",
        "images": "photos",
        "unassigned_references": "unassigned",
        "sections": [
            {
                "field": "notes",
                "label": "Shared notes",
                "lookup": {"table": "notes", "id_field": "id"},
            }
        ],
    }
    (settings / "config.yaml").write_text(
        yaml.safe_dump(
            {
                "collections": {
                    "sites": {
                        "data": "sites.yaml",
                        "schema": "schema.json",
                        "records": "sites",
                        "presentation": view,
                    }
                }
            }
        )
    )
    (root / "schema.json").write_text('{"type":"object","required":["sites"]}')
    photo = {"kind": "Image", "path": "site.png", "alt_text": "The harbour"}
    (root / "site.png").write_bytes(
        base64.b64decode(
            "iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAQAAAC1HAwCAAAAC0lEQVR42mP8/x8AAwMCAO+jU1sAAAAASUVORK5CYII="
        )
    )
    citation = {"citation": "Survey report", "doi": "10.1234/Survey"}
    west = {
        "id": "west",
        "name": "Harbour",
        "flag": True,
        "codes": ["site:1"],
        "photos": [photo],
        "notes": ["n"],
        "surveys": [
            {
                "sample": "winter",
                "campaign": "north",
                "label": "North",
                "season": "Winter",
                "depth": 0,
                "citations": [citation],
                "photos": [{"kind": "Map", "url": "https://example.org/map.png"}],
            },
            {
                "sample": "spring",
                "campaign": "north",
                "label": "North",
                "season": "Spring",
                "depth": 5,
            },
        ],
    }
    other = {
        "id": "east",
        "name": "East harbour",
        "codes": ["site:1"],
        "surveys": [
            {"sample": "summer", "campaign": "south", "label": "South", "depth": 6}
        ],
    }
    document = {
        "sites": [
            west,
            other,
            {"id": "a", "name": "Inlet"},
            {"id": "b", "name": "Bay"},
        ],
        "notes": [
            {"id": "n", "text": "Source note", "citations": [{"doi": "10.1234/linked"}]}
        ],
        "unassigned": [
            citation,
            {"citation": "Another entry", "url": "https://doi.org/10.1234/survey"},
        ],
    }
    (root / "sites.yaml").write_text(yaml.safe_dump(document, sort_keys=False))
    return document


def test_grouped_view_and_scope(tmp_path):
    project(tmp_path)
    collections, errors, _ = load_collections(tmp_path)
    assert not errors
    c = collections[0]
    d = detail_view(c, {})
    assert [g.name for g in d["shown"]] == ["Harbour", "Bay", "Inlet"]
    assert [v.name for v in d["tabs"]] == ["North", "South"]
    assert [v.key for v in d["variant_records"]] == ["winter", "spring"]
    assert d["overview"] == [("depth", 0)]
    assert d["sections"][0][1][0]["text"] == "Source note"
    assert d["images"][0]["preview"].startswith("data:image/png;base64,")
    assert d["images"][0]["scope"] == "Shared"
    assert d["images"][1]["preview"] == "https://example.org/map.png"
    assert d["references"][0]["href"] == "https://doi.org/10.1234/Survey"
    spring = detail_view(c, {"entry": "west", "variant": "spring", "view": "raw"})
    assert not spring["references"] and spring["overview"] == [("depth", 5)]
    assert yaml.safe_load(spring["raw"])["sample"] == "spring"
    assert len(yaml.safe_load(spring["full_record"])["surveys"]) == 2
    assert detail_view(c, {"entry": "west", "variant": "absent"})["missing_variant"]
    for term in ("SITE:1", "East harbour", "10.1234/sUrVeY", "10.1234/linked"):
        assert [g.entry for g in detail_view(c, {"filter": term})["shown"]] == ["west"]
    assert len(detail_view(c, {"tag": "starred"})["shown"]) == 1
    assert not detail_view(c, {"entry": "a"})["tabs"]
    refs = detail_view(c, {"panel": "unassigned"})["reference_page"]
    assert refs["distinct"] == 1 and len(refs["rows"]) == 2
    assert all(
        r["occurrences"] == 2 and r["cited_by"] == [("Harbour", "west", "winter")]
        for r in refs["rows"]
    )


def test_duplicate_variant_ids_fail_validation(tmp_path):
    data = project(tmp_path)
    data["sites"][0]["surveys"][1]["sample"] = "winter"
    (tmp_path / "sites.yaml").write_text(yaml.safe_dump(data))
    collections, errors, _ = load_collections(tmp_path)
    assert not collections and "duplicate record ID 'winter'" in errors[0]


def test_detail_navigation_keeps_the_selected_record(tmp_path, monkeypatch):
    project(tmp_path)
    page = open_viewer(tmp_path, monkeypatch)
    follow(page, "sites")
    overview = html(page).split("<main>")[1]
    assert "Harbour</h1>" in overview and 'alt="The harbour"' in overview
    assert 'src="https://example.org/map.png"' in overview
    assert "Source note" in overview and ">Winter<" in overview
    follow(page, "spring")
    assert ">Spring<" in html(page) and "No references attached." in html(page)
    follow(page, "Raw metadata")
    assert "<pre>sample: spring" in html(page)
    follow(page, "South")
    assert "<pre>sample: summer" in html(page)
    follow(page, "Unassigned references")
    assert "1 distinct DOI across 2 entries" in html(page)
    assert "DOI appears 2×" in html(page) and "Also cited by" in html(page)
    follow(page, "Harbour")
    assert "variant=winter" in page.session_state["fragment"]
    assert 'href="https://doi.org/10.1234/Survey"' in html(page)
