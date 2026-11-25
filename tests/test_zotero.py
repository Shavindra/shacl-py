import io
import json
from urllib.parse import parse_qs, urlsplit

import pytest
import yaml
from test_references import project
from test_viewer import follow, html, open_viewer

from shacl_py import zotero
from shacl_py.bibliography import import_bibliography
from shacl_py.cli import main


@pytest.fixture(autouse=True)
def clear_zotero_environment(monkeypatch):
    for name in ("ZOTERO_COLLECTION", "ZOTERO_WEB_LIBRARY", "ZOTERO_API_KEY"):
        monkeypatch.delenv(name, raising=False)


def item(key, title, doi="", *, library=42, group=False):
    csl = {
        "id": "export-key",
        "title": title,
        "DOI": doi,
        "author": [{"literal": "Imaging Group"}],
    }
    return {
        "key": key,
        "library": {"type": "group" if group else "user", "id": library},
        "data": {"itemType": "journalArticle", "tags": [{"tag": "microscopy"}]},
        "csljson": csl if group else json.dumps([csl]),
    }


def api(monkeypatch, items, *, names=("Cell sim",)):
    collections = [
        {"key": f"C{i:07}", "data": {"name": name}} for i, name in enumerate(names)
    ]
    calls = []

    def request(req, timeout):
        url = urlsplit(req.full_url)
        params = parse_qs(url.query)
        calls.append((url, params, req))
        assert req.get_method() == "GET"
        if url.path.endswith("/collections"):
            rows = collections
        else:
            assert url.path.endswith("/collections/C0000000/items/top")
            rows = items
        start, limit = int(params["start"][0]), int(params["limit"][0])
        res = io.BytesIO(json.dumps(rows[start : start + limit]).encode())
        res.headers = {"Total-Results": str(len(rows)), "Last-Modified-Version": "6"}
        return res

    monkeypatch.setattr(zotero, "urlopen", request)
    monkeypatch.setattr(zotero, "PAGE_SIZE", 1)
    return calls


def test_desktop_import_preserves_export_and_curated_records(tmp_path, monkeypatch):
    root = project(tmp_path)
    import_bibliography(root, "references/library.json", into="references.yaml")
    items = [
        item("CCCCAAAA", "Updated title", "10.1083/JCB.202407110"),
        item("BBBBDDDD", "Paper without DOI"),
        {"key": "AAAA0000", "data": {"itemType": "note"}},
    ]
    calls = api(monkeypatch, items)
    monkeypatch.setenv("ZOTERO_API_KEY", "unit-test-only")
    options = {"into": "references.yaml"}
    original = (root / "references.yaml").read_bytes()
    dry = zotero.import_zotero(root, "Cell sim", dry_run=True, **options)
    assert len(dry["added"]) == len(dry["updated"]) == 1
    assert (root / "references.yaml").read_bytes() == original
    saved = zotero.import_zotero(root, "C0000000", **options)
    (pid,) = saved["added"]
    paper = yaml.safe_load((root / "papers.yaml").read_text())["publications"][0]
    assert paper["bibliography"]["key"] == "chang2025"
    assert paper["bibliography"]["zotero_items"] == ["users/42/items/CCCCAAAA"]
    assert paper["keywords"] == ["curated"] and paper["dataset_links"]
    ref = next(
        p
        for p in yaml.safe_load((root / "references.yaml").read_text())["publications"]
        if p["pid"] == pid
    )
    assert ref["keywords"] == ["microscopy"] and not ref.get("dataset_links")
    assert not zotero.import_zotero(root, "cell SIM", **options)["files"]
    # A user can move the same reference into a reviewed paper catalogue before it gets a DOI.
    refs = yaml.safe_load((root / "references.yaml").read_text())
    refs["publications"].remove(ref)
    (root / "references.yaml").write_text(yaml.safe_dump(refs))
    curated = yaml.safe_load((root / "papers.yaml").read_text())
    curated["publications"].append({**ref, "local_folder": "."})
    curated["reviews"] = [{"publication": pid, "notes": "Keep this review"}]
    (root / "papers.yaml").write_text(yaml.safe_dump(curated))
    items[1] = item("BBBBDDDD", "Final title", "10.1000/final")
    assert zotero.import_zotero(root, "Cell sim", **options)["updated"] == [pid]
    curated = yaml.safe_load((root / "papers.yaml").read_text())
    assert curated["publications"][-1]["source_url"] == "https://doi.org/10.1000/final"
    assert curated["reviews"][0]["publication"] == pid
    import_bibliography(root, "references/library.json", **options)
    assert yaml.safe_load((root / "papers.yaml").read_text())["publications"][0][
        "bibliography"
    ]["zotero_items"] == ["users/42/items/CCCCAAAA"]
    assert all(
        url.hostname == "127.0.0.1" and "Zotero-api-key" not in req.unredirected_hdrs
        for url, _, req in calls
    )
    assert any(q["start"] == ["2"] for _, q, _ in calls)


def test_web_library_scopes_keys_and_rejects_bad_pages(tmp_path, monkeypatch):
    root = project(tmp_path)
    rows = [item("BBBBDDDD", "First paper", library=12, group=True)]
    calls = api(monkeypatch, rows)
    monkeypatch.setenv("ZOTERO_API_KEY", "unit-test-only")
    opts = [
        "--project",
        str(root),
        "--collection",
        "Cell sim",
        "--into",
        "references.yaml",
    ]
    assert main(["import-zotero", "--web-library", "groups/12", *opts]) == 0
    assert all(
        u.hostname == "api.zotero.org"
        and req.unredirected_hdrs["Zotero-api-key"] == "unit-test-only"
        for u, _, req in calls
    )
    rows[:] = [item("BBBBDDDD", "Another library", library=22, group=True)]
    assert main(["import-zotero", "--web-library", "groups/22", *opts]) == 0
    papers = yaml.safe_load((root / "references.yaml").read_text())["publications"]
    assert len({p["pid"] for p in papers}) == 2
    assert {p["bibliography"]["zotero_items"][0] for p in papers} == {
        "groups/12/items/BBBBDDDD",
        "groups/22/items/BBBBDDDD",
    }
    original = (root / "references.yaml").read_bytes()
    rows[0] = item("BBBBDDDD", "Must not get written", library=22, group=True)
    rows.append(rows[0])
    with pytest.raises(ValueError, match="repeated Zotero key"):
        zotero.import_zotero(
            root, "Cell sim", into="references.yaml", web_library="groups/22"
        )
    assert (root / "references.yaml").read_bytes() == original


def test_duplicate_collection_names_require_a_key(tmp_path, monkeypatch):
    root = project(tmp_path)
    api(monkeypatch, [], names=("Cell sim", "Cell sim"))
    with pytest.raises(ValueError, match="C0000000, C0000001"):
        zotero.import_zotero(root, "Cell sim")
    with pytest.raises(ValueError, match="No Zotero collection"):
        zotero.import_zotero(root, "Wrong name")


def test_env_file_and_overrides(tmp_path, monkeypatch, capsys):
    root = project(tmp_path)
    config = root / "configuration.env"
    config.write_text(
        'ZOTERO_COLLECTION="Cell sim"\nZOTERO_WEB_LIBRARY=groups/12\nZOTERO_API_KEY=private-unit-test\n'
    )
    args = [
        "import-zotero",
        "--project",
        str(root),
        "--into",
        "references.yaml",
        "--dry-run",
    ]
    calls = api(monkeypatch, [item("AAAAAAAA", "Example", library=12, group=True)])
    assert main(args) == 0
    assert calls[-1][2].unredirected_hdrs["Zotero-api-key"] == "private-unit-test"
    assert "private-unit-test" not in str(capsys.readouterr())
    assert "private-unit-test" not in (root / "references.yaml").read_text()

    monkeypatch.setenv("ZOTERO_COLLECTION", "A different name")
    monkeypatch.setenv("ZOTERO_API_KEY", "environment-unit-test")
    assert main(args) == 1
    assert "A different name" in capsys.readouterr().err
    assert main([*args, "--collection", "Cell sim"]) == 0
    assert calls[-1][2].unredirected_hdrs["Zotero-api-key"] == "environment-unit-test"
    calls = api(monkeypatch, [item("AAAAAAAA", "Example")])
    assert main([*args, "--collection", "Cell sim", "--desktop"]) == 0
    assert (
        calls[-1][0].hostname == "127.0.0.1"
        and "Zotero-api-key" not in calls[-1][2].unredirected_hdrs
    )


def test_missing_configuration_fails_before_network_or_writes(
    tmp_path, monkeypatch, capsys
):
    root = project(tmp_path)
    calls = api(monkeypatch, [])
    (root / "references/configuration.env").write_text("ZOTERO_COLLECTION=Subfolder\n")
    assert main(["import-zotero", "--project", str(root)]) == 1
    assert "configuration.env" in capsys.readouterr().err
    assert not calls


def test_existing_csl_identifier_links_without_a_doi(tmp_path, monkeypatch):
    root = project(tmp_path)
    (root / "references/library.json").write_text(
        json.dumps(
            [
                {
                    "id": "http://zotero.org/users/local/abc123/items/AAAABBBB",
                    "citation-key": "prior",
                    "title": "Initial",
                }
            ]
        )
    )
    (pid,) = import_bibliography(
        root, "references/library.json", into="references.yaml"
    )["added"]
    row = item("AAAABBBB", "Updated", library=0)
    row["csljson"] = json.dumps(
        [
            {
                "id": "http://zotero.org/users/local/abc123/items/AAAABBBB",
                "title": "Updated",
            }
        ]
    )
    api(monkeypatch, [row])
    report = zotero.import_zotero(root, "Cell sim", into="references.yaml")
    assert report["updated"] == [pid] and not report["added"]


def test_duplicate_zotero_items_with_one_doi_share_a_reference(tmp_path, monkeypatch):
    root = project(tmp_path)
    api(
        monkeypatch,
        [
            item("AAAA1111", "Earlier title", "10.1000/common"),
            item("BBBB2222", "Published title", "10.1000/common"),
        ],
    )
    opts = {"into": "references.yaml"}
    report = zotero.import_zotero(root, "Cell sim", **opts)
    assert (
        report["added"] == ["https://doi.org/10.1000/common"] and not report["updated"]
    )
    (paper,) = yaml.safe_load((root / "references.yaml").read_text())["publications"]
    assert paper["bibliography"]["zotero_items"] == [
        "users/42/items/AAAA1111",
        "users/42/items/BBBB2222",
    ]
    again = zotero.import_zotero(root, "Cell sim", **opts)
    assert again["unchanged"] == [paper["pid"]] and not again["files"]
    page = open_viewer(root, monkeypatch)
    follow(page, "Published title")
    assert "No datasets linked" in html(page)
