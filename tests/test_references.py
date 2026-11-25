import datetime
import json

import pytest
import yaml
from test_viewer import follow, html, open_viewer

from shacl_py.bibliography import import_bibliography, read_export
from shacl_py.cli import main
from shacl_py.sources import doi_identifier

TODAY = datetime.date(2026, 11, 25)

CSL = [
    {
        "id": "chang2025",
        "title": "Cytoplasmic ribosomes on mitochondria",
        "author": [{"given": "Ya-Ting", "family": "Chang"}, {"literal": "Lab Group"}],
        "issued": {"date-parts": [[2025, 3]]},
        "container-title": "Journal of Cell Biology",
        "DOI": "10.1083/JCB.202407110",
        "keyword": "cryo-ET, mitochondria",
    },
    {
        "id": "allegretti2020",
        "title": "In-cell architecture of the nuclear pore",
        "author": [{"given": "Matteo", "family": "Allegretti"}],
        "issued": {"date-parts": [[2020]]},
        "container-title": "Nature",
        "DOI": "10.1038/s41586-020-2670-5",
    },
    {"title": "Unidentified note"},
]

BIBTEX = r"""
@comment{exported by Better BibTeX}
@article{allegretti2020,
  title = {In-cell architecture of the {nuclear} pore},
  author = {Allegretti, Matteo and Zimmerli, Christian E.},
  journal = "Nature",
  year = 2020,
  doi = {10.1038/s41586-020-2670-5},
  keywords = {cryo-ET; nuclear pore},
}
"""


def project(tmp_path):
    (tmp_path / "references").mkdir()
    (tmp_path / "references/library.json").write_text(json.dumps(CSL))
    (tmp_path / "metadata.yaml").write_text(
        """# Project catalogue
catalogue:
  project: {pid: 'urn:test:project', title: Project}
  includes: [papers.yaml, references.yaml]
"""
    )
    (tmp_path / "papers.yaml").write_text(
        """publications:
- pid: https://doi.org/10.1083/jcb.202407110
  title: Old working title  # curated comment
  source_url: https://doi.org/10.1083/jcb.202407110
  keywords: [curated]
  local_folder: .
  dataset_links: [{dataset: 'urn:test:data', role: describes}]
- pid: urn:test:curated
  title: Curated paper outside the bibliography
  local_folder: .
datasets:
- pid: urn:test:data
  title: Tomograms
"""
    )
    (tmp_path / "references.yaml").write_text("publications: []\n")
    return tmp_path


def test_normal_doi():
    assert doi_identifier("https://dx.doi.org/10.1000/ABC") == "10.1000/abc"
    assert doi_identifier("doi: 10.1000/x") == "10.1000/x"
    assert doi_identifier("urn:test:x") is None


def test_bibtex_export(tmp_path):
    path = tmp_path / "library.bib"
    path.write_text(BIBTEX)
    (entry,) = read_export(path)
    assert entry == {
        "key": "allegretti2020",
        "title": "In-cell architecture of the nuclear pore",
        "authors": ["Matteo Allegretti", "Christian E. Zimmerli"],
        "year": "2020",
        "journal": "Nature",
        "doi": "10.1038/s41586-020-2670-5",
        "keywords": ["cryo-ET", "nuclear pore"],
    }


def test_import_updates_bibliographic_fields_only(tmp_path):
    root = project(tmp_path)
    report = import_bibliography(
        root, "references/library.json", into="references.yaml", today=TODAY
    )
    assert report["updated"] == ["https://doi.org/10.1083/jcb.202407110"]
    assert report["added"] == ["https://doi.org/10.1038/s41586-020-2670-5"]
    assert report["skipped"] == ["Unidentified note"]

    text = (root / "papers.yaml").read_text()
    assert "# curated comment" in text
    paper = yaml.safe_load(text)["publications"][0]
    assert paper["title"] == "Cytoplasmic ribosomes on mitochondria"
    assert paper["author_names"] == ["Ya-Ting Chang", "Lab Group"]
    assert paper["keywords"] == ["curated"]
    assert paper["dataset_links"] == [{"dataset": "urn:test:data", "role": "describes"}]
    assert {a["predicate"]: a["value"] for a in paper["attributes"]} == {
        "https://schema.org/datePublished": "2025",
        "https://schema.org/isPartOf": "Journal of Cell Biology",
    }
    assert paper["bibliography"] == {
        "file": "references/library.json",
        "key": "chang2025",
        "imported": "2026-11-25",
    }

    (added,) = yaml.safe_load((root / "references.yaml").read_text())["publications"]
    assert added["pid"] == "https://doi.org/10.1038/s41586-020-2670-5"
    assert "dataset_links" not in added
    assert main(["validate", str(root)]) == 0

    # A second run with the same export changes nothing.
    before = {p: (root / p).read_text() for p in ("papers.yaml", "references.yaml")}
    later = datetime.date(2026, 12, 1)
    again = import_bibliography(root, "references/library.json", today=later)
    assert again["added"] == again["updated"] == []
    assert {p: (root / p).read_text() for p in before} == before


def test_import_rejects_unlisted_target_and_dry_run_saves_nothing(tmp_path, capsys):
    root = project(tmp_path)
    before = (root / "papers.yaml").read_text()
    args = ["import-bib", "references/library.json", "--project", str(root)]
    assert main([*args, "--into", "other.yaml"]) == 1
    assert "not listed in catalogue.includes" in capsys.readouterr().err
    assert main([*args, "--dry-run"]) == 0
    assert "Added: 1" in capsys.readouterr().out
    assert (root / "papers.yaml").read_text() == before


def test_reference_list(tmp_path, monkeypatch):
    root = project(tmp_path)
    import_bibliography(
        root, "references/library.json", into="references.yaml", today=TODAY
    )
    page = open_viewer(root, monkeypatch)
    body = html(page)
    nav = body.split("<nav>")[1].split("</nav>")[0]
    assert "Reference list <small>2</small>" in nav
    assert "Papers <small>2</small>" in nav
    assert "<h1>Reference list</h1>" in body
    follow(page, "Papers")
    assert "In-cell architecture" not in html(page).split("<main")[0]

    follow(page, "Reference list")
    body = html(page)
    assert "references/library.json" in body
    assert "Chang et al." in body and "Journal of Cell Biology" in body
    assert "In-cell architecture of the nuclear pore" in body
    assert "Curated paper outside the bibliography" not in body

    follow(page, "In-cell architecture of the nuclear pore")
    drawer = html(page).split('class="drawer refdrawer"')[1]
    assert "No datasets linked" in drawer
    assert (
        "shacl-py add-datasets --paper https://doi.org/10.1038/s41586-020-2670-5"
        in drawer
    )
    assert "Open in Papers" not in drawer
    assert "10.1038/s41586-020-2670-5 ↗" in drawer

    follow(page, "Reference list")
    follow(page, "Cytoplasmic ribosomes on mitochondria")
    drawer = html(page).split('class="drawer refdrawer"')[1]
    assert "Tomograms" in drawer and "Describes" in drawer
    follow(page, "Open in Papers")
    assert "Tomograms</h2>" in html(page)


def test_key_only_reference_gains_doi_without_losing_review(tmp_path):
    root = project(tmp_path)
    export = root / "references/library.json"
    row = {"id": "stable", "title": "Initial title"}
    export.write_text(json.dumps([row]))
    kwargs = {"into": "references.yaml", "today": TODAY}
    (pid,) = import_bibliography(root, "references/library.json", **kwargs)["added"]
    assert pid.startswith("urn:uuid:")
    target = root / "references.yaml"
    saved = yaml.safe_load(target.read_text())
    saved["reviews"] = [{"publication": pid, "notes": "Keep these notes"}]
    target.write_text(yaml.safe_dump(saved))
    export.write_text(
        json.dumps([{**row, "title": "Published title", "DOI": "10.1000/FINAL"}])
    )
    report = import_bibliography(root, "references/library.json", **kwargs)
    assert report["updated"] == [pid] and report["added"] == []
    saved = yaml.safe_load(target.read_text())
    (paper,) = saved["publications"]
    assert paper["source_url"] == "https://doi.org/10.1000/final"
    assert saved["reviews"] == [{"publication": pid, "notes": "Keep these notes"}]
    assert import_bibliography(root, "references/library.json", **kwargs)[
        "unchanged"
    ] == [pid]
    export.write_text(json.dumps([{**row, "DOI": "10.1083/JCB.202407110"}]))
    before = target.read_bytes()
    with pytest.raises(ValueError, match="Ambiguous bibliography match"):
        import_bibliography(root, "references/library.json", **kwargs)
    assert target.read_bytes() == before


def test_real_bibtex_names_and_macros(tmp_path):
    path = tmp_path / "library.bib"
    path.write_text(r"""@string{journalname = "Example Journal"}
@article(example, title = {The {DNA} study}, author = {{Imaging and Data Group} and de la Cruz, Jr, Ana}, journal=journalname, year=2025)""")
    (paper,) = read_export(path)
    assert paper["authors"] == ["Imaging and Data Group", "Ana de la Cruz, Jr"]
    assert paper["journal"] == "Example Journal"
    assert paper["title"] == "The DNA study"
