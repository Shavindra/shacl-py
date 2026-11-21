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


def relationships(graph):
    return {(s.label, p, t.label) for s, p, t in graph.edges}


def test_only_papers_datasets_and_declared_labels_form_the_network(tmp_path):
    for folder in ("one", "two"):
        path = tmp_path / folder
        path.mkdir()
        (path / "project.json").write_text(
            json.dumps(
                {
                    "@graph": [
                        {
                            "@type": "ScholarlyArticle",
                            "name": f"Paper {folder}",
                            "isBasedOn": {"@id": "sample"},
                            "author": [{"@id": "person"}, {"@id": "sample"}],
                            "labels": ["Imaging", " Imaging ", ""],
                            "schema:keywords": {"@set": [{"@value": "Live & fixed"}]},
                        },
                        {
                            "@type": "Dataset",
                            "@id": "sample",
                            "name": f"Data {folder}",
                            "keywords": "Imaging",
                        },
                        {
                            "@type": "Person",
                            "@id": "person",
                            "name": "Ada Lane",
                            "labels": "Microscopist",
                        },
                        {
                            "@type": "Method",
                            "name": "Microscopy",
                            "labels": "Acquisition",
                        },
                    ]
                }
            )
        )
    graph = graph_from(tmp_path)
    assert [(n.kind, n.label) for n in graph.nodes if n.kind == "Label"] == [
        ("Label", "Imaging"),
        ("Label", "Live & fixed"),
    ]
    assert len(graph.nodes) == 6
    assert relationships(graph) == {
        edge
        for name in ("one", "two")
        for edge in (
            (f"Paper {name}", "isBasedOn", f"Data {name}"),
            (f"Paper {name}", "Labelled", "Imaging"),
            (f"Paper {name}", "Labelled", "Live & fixed"),
            (f"Data {name}", "Labelled", "Imaging"),
        )
    }
    assert not graph_from(tmp_path, query="Ada Lane").nodes
    shared = graph_from(tmp_path, label="Live & fixed")
    assert shared.focus.label == "Live & fixed"
    assert {node.label for node in shared.nodes} == {
        "Live & fixed",
        "Paper one",
        "Paper two",
    }
    assert shared.focus.route == {"section": "graph", "label": "Live & fixed"}
    assert len(shared.network_data()["edges"]) == 2


def test_graph_unions_links_and_keywords_from_duplicate_publications(tmp_path):
    (tmp_path / "metadata.yaml").write_text(
        "catalogue:\n"
        "  project: {pid: 'urn:root', title: Project}\n"
        "  publications: [{pid: 'urn:paper', title: Paper, source_url: 'https://doi.org/10.1234/EXAMPLE', "
        "dataset_links: [{dataset: 'urn:data', role: reuses}]}]\n"
        "  datasets: [{pid: 'urn:data', title: Readings}]\n"
        "  reviews: [{publication: 'urn:paper', outputs: ['urn:data']}]\n"
    )
    (tmp_path / ".studyminimeta.yaml").write_text(
        "publication: [{title: Second title, doi: 10.1234/example, author: [a], keyword: [Imaging]}]\n"
        "person: {a: {given_name: Ada, last_name: Lane}}\n"
    )
    (tmp_path / "project.json").write_text(
        json.dumps(
            {
                "@graph": [
                    {
                        "@type": "Note",
                        "name": "Citation note",
                        "citation": {"@id": "urn:paper"},
                    },
                    {
                        "@type": "Article",
                        "name": "Earlier paper",
                        "@reverse": {
                            "citation": {"@id": "https://doi.org/10.1234/EXAMPLE"}
                        },
                    },
                    {
                        "@type": "Dataset",
                        "name": "Isolated dataset",
                        "display_label": "Display text",
                    },
                ]
            }
        )
    )
    graph = graph_from(tmp_path, query="second title")
    assert {n.label for n in graph.nodes} == {
        "Paper",
        "Readings",
        "Imaging",
        "Earlier paper",
    }
    assert relationships(graph) == {
        ("Paper", "Reuses", "Readings"),
        ("Paper", "Output", "Readings"),
        ("Paper", "Labelled", "Imaging"),
        ("Paper", "citation", "Earlier paper"),
    }
    isolated = graph_from(tmp_path, query="DISPLAY TEXT")
    assert [n.kind for n in isolated.nodes] == ["Dataset"]
    assert not isolated.edges
    assert not graph_from(tmp_path, label="unknown").nodes
