import itertools

from evalproof.project_index import RAG_CONTENT_FIELD_ALIASES


def test_shared_state_preserves_existing_truth_table():
    from evalproof.project_index import inspect_rag_content_state
    from evalproof.rules.empty_referenced_document import EmptyReferencedDocumentRule
    values = [None, "", " \t\n", "private text", 0, False, [], {}, ["private text"]]
    for left, right in itertools.product(values, repeat=2):
        row = {"content": right, "text": left}
        expected = "nonempty" if any(isinstance(value, str) and value.strip() for value in [left, right]) else (
            "empty" if all(value is None or isinstance(value, str) and not value.strip() for value in [left, right]) else None)
        fields, state = inspect_rag_content_state(row)
        assert fields == ("text", "content")
        assert state == expected
        assert EmptyReferencedDocumentRule._content_state(row) == expected


def test_shared_state_abstains_on_missing_or_nested_fields():
    from evalproof.project_index import inspect_rag_content_state
    for row in [None, [], "", {}, {"metadata": {"text": ""}}]:
        assert inspect_rag_content_state(row) == ((), None)
    for field in RAG_CONTENT_FIELD_ALIASES:
        assert inspect_rag_content_state({field: None}) == ((field,), "empty")
