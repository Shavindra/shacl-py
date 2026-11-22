import pytest

from shacl_py.catalogue import validate_catalogue

size = {"id": "urn:term:size", "label": "Size"}
volume = {"id": "urn:term:volume", "label": "Volume", "broader": size["id"]}
nucleus = {
    "id": "urn:nucleus",
    "label": "Nucleus",
    "role": "subject",
    "category": "Compartment",
}


@pytest.mark.parametrize(
    ("definitions", "assignment", "error"),
    [
        ([size, size], {}, "duplicate term"),
        ([volume], {}, "unknown broader term"),
        ([dict(size, broader=volume["id"]), volume], {}, "cyclic broader terms"),
        ([size], {"term": volume["id"]}, "unknown index_terms term"),
        ([nucleus], {"property": nucleus["id"]}, "is a subject, used as property"),
        (
            [dict(size, role="property")],
            {"subject": size["id"]},
            "is a property, used as subject",
        ),
        ([size], {"term": size["id"], "property": size["id"]}, "index_terms"),
        ([size], {"note": "Table 1"}, "index_terms"),
        (
            [nucleus, dict(volume, role="property", broader=nucleus["id"])],
            {},
            "different roles",
        ),
        (
            [dict(size, role="property"), volume],
            {"subject": volume["id"]},
            "is a property, used as subject",
        ),
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
