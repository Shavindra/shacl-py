import json

from shacl_py.browser import dataset_keys, items_from, publication_key
from shacl_py.graph import record_graph
from shacl_py.records import load_records


def graph_from(root, **scope):
    sources, errors = load_records(root)
    assert not errors
    items = list(items_from(sources, root))
    keys = dataset_keys(
        [i for i in items if i.is_publication], [i for i in items if i.is_dataset]
    )
    return record_graph(items, lambda i: keys.get(i, publication_key(i)), **scope)


def test_direct_links_keep_predicates_and_source_local_identifiers(tmp_path):
    for folder, title in (("one", "Ada"), ("two", "Bea")):
        path = tmp_path / folder
        path.mkdir()
        (path / ".studyminimeta.yaml").write_text(
            f"publication: [{{title: Paper {folder}, author: [a]}}]\n"
            f"person: {{a: {{given_name: {title}, last_name: Lane}}}}\n"
        )
    (tmp_path / "project.json").write_text(
        json.dumps(
            {
                "@graph": [
                    {
                        "@id": "urn:observation",
                        "name": "Observation",
                        "relations": {
                            "urn:instrument": {"display_label": "Microscope"}
                        },
                        "characterized_by": [
                            {"predicate": "ex:measuredWith", "object": "urn:instrument"}
                        ],
                        "ex:method": {
                            "@type": "Method",
                            "name": "Imaging",
                            "ex:instrument": {"@id": "urn:instrument"},
                        },
                        "notes": "urn:unrelated",
                    },
                    {"@id": "urn:unrelated", "name": "Unlinked record"},
                ]
            }
        )
    )
    graph = graph_from(tmp_path)
    assert len(graph.nodes) == 8
    assert {(s.label, p, t.label) for s, p, t in graph.edges} == {
        ("Paper one", "author", "Ada Lane"),
        ("Paper two", "author", "Bea Lane"),
        ("Observation", "relations", "Microscope"),
        ("Observation", "ex:measuredWith", "Microscope"),
        ("Observation", "ex:method", "Imaging"),
        ("Imaging", "ex:instrument", "Microscope"),
    }
    isolated = graph_from(tmp_path, query="UNLINKED")
    assert [i.label for i in isolated.nodes] == ["Unlinked record"]
    assert not isolated.edges


def test_graph_unions_links_from_duplicate_publications(tmp_path):
    (tmp_path / "metadata.yaml").write_text(
        "catalogue:\n"
        "  project: {pid: 'urn:root', title: Project}\n"
        "  publications: [{pid: 'urn:paper', title: Paper, source_url: 'https://doi.org/10.1234/EXAMPLE', "
        "dataset_links: [{dataset: 'urn:data', role: reuses}]}]\n"
        "  datasets: [{pid: 'urn:data', title: Readings}]\n"
        "  reviews: [{publication: 'urn:paper', outputs: ['urn:data']}]\n"
    )
    (tmp_path / ".studyminimeta.yaml").write_text(
        "publication: [{title: Second title, doi: 10.1234/example, author: [a]}]\n"
        "person: {a: {given_name: Ada, last_name: Lane}}\n"
    )
    (tmp_path / "project.json").write_text(
        json.dumps(
            {
                "@type": "Note",
                "name": "Citation note",
                "citation": {"@id": "https://doi.org/10.1234/EXAMPLE"},
            }
        )
    )
    graph = graph_from(tmp_path, query="second title")
    assert {i.label for i in graph.nodes} == {
        "Project",
        "Paper",
        "Readings",
        "Ada Lane",
        "Citation note",
    }
    assert {(s.label, p, t.label) for s, p, t in graph.edges} == {
        ("Project", "Lists", "Paper"),
        ("Paper", "Reuses", "Readings"),
        ("Paper", "Output", "Readings"),
        ("Paper", "author", "Ada Lane"),
        ("Citation note", "citation", "Paper"),
    }
