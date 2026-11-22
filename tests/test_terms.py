import pytest

from shacl_py.catalogue import validate_catalogue

size = {"id": "urn:term:size", "label": "Size"}
volume = {"id": "urn:term:volume", "label": "Volume", "broader": size["id"]}


@pytest.mark.parametrize(
    ("definitions", "assignment", "error"),
    [
        ([size, size], {}, "duplicate term"),
        ([volume], {}, "unknown broader term"),
        ([dict(size, broader=volume["id"]), volume], {}, "cyclic broader terms"),
        ([size], {"term": volume["id"]}, "unknown index_terms term"),
        (
            [size],
            {"term": size["id"], "subject": "urn:missing"},
            "unknown index_terms subject",
        ),
    ],
)
def test_invalid_vocabulary_and_assignments(tmp_path, definitions, assignment, error):
    graph = {"project": {"pid": "urn:project", "term_vocabulary": definitions}}
    if assignment:
        graph["datasets"] = [{"pid": "urn:dataset", "index_terms": [assignment]}]
    with pytest.raises(ValueError, match=error):
        validate_catalogue(graph, tmp_path)
