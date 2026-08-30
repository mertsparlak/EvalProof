from __future__ import annotations

import json

import pytest
import yaml

import evalproof.cli as cli
from evalproof.artifact import create_artifact_from_file
from evalproof.config import parse_and_validate_config_dict
from evalproof.project_index import ProjectIndex

RULE_ID = "rag.chunk_id_collision"


def write_project(root, files, roles=None, limits=None):
    config = {
        "artifacts": [
            {"path": path, "roles": roles or ["rag_document"]} for path in files
        ],
        "similarity": {"enabled": False},
    }
    if limits:
        config["limits"] = limits
    (root / "evalproof.yaml").write_text(yaml.safe_dump(config), encoding="utf-8")
    for path, rows in files.items():
        (root / path).write_text(
            "".join(json.dumps(row, ensure_ascii=False) + "\n" for row in rows),
            encoding="utf-8",
        )
    return config


def scan(root):
    output = root.parent / (root.name + "-collision-report.json")
    ret = cli.main(["scan", str(root), "--rules", RULE_ID, "--json", "--output", str(output)])
    assert ret in {0, 1}, "selected collision rule must be registered and scan successfully"
    return ret, json.loads(output.read_text(encoding="utf-8"))


def test_collision_is_confirmed_high_bounded_and_redacted_without_eval(tmp_path):
    write_project(tmp_path, {"rag.jsonl": [
        {"chunk_id": "private-chunk-key", "text": "Private first passage."},
        {"chunk_id": " private-chunk-key ", "text": "Private second passage."},
    ]})
    ret, report = scan(tmp_path)
    assert ret == 1
    assert report["scan"]["rules"]["ids"] == [RULE_ID]
    assert len(report["findings"]) == 1
    finding = report["findings"][0]
    assert finding["rule_id"] == RULE_ID
    assert (finding["severity"], finding["confidence"]) == ("high", "confirmed")
    evidence = finding["evidence"]
    assert evidence["artifact_path"] == "rag.jsonl"
    assert evidence["chunk_id_field"] == "chunk_id"
    assert evidence["record_count"] == 2
    assert evidence["distinct_content_count"] == 2
    assert evidence["evidence_truncated"] is False
    assert {r["row"] for r in evidence["sample_records"]} == {1, 2}
    assert len({r["content_hash"] for r in evidence["sample_records"]}) == 2
    assert finding["fingerprint"].startswith("sha256:")
    for raw in ["private-chunk-key", "Private first passage.", "Private second passage."]:
        assert raw not in json.dumps(report)


@pytest.mark.parametrize("id_field", ["id", "doc_id", "document_id", "context_id", "source_id"])
def test_parent_and_generic_ids_do_not_define_chunk_identity(tmp_path, id_field):
    write_project(tmp_path, {"rag.jsonl": [
        {id_field: "parent", "chunk_id": "a", "text": "First passage."},
        {id_field: "parent", "chunk_id": "b", "text": "Second passage."},
        {id_field: "parent", "text": "Third passage."},
    ]})
    ret, report = scan(tmp_path)
    assert ret == 0
    assert report["findings"] == []


def test_separate_files_are_separate_id_namespaces(tmp_path):
    write_project(tmp_path, {
        "first.jsonl": [{"chunk_id": "one", "text": "First corpus."}],
        "second.jsonl": [{"chunk_id": "one", "text": "Second corpus."}],
    })
    ret, report = scan(tmp_path)
    assert ret == 0
    assert report["findings"] == []


def test_same_id_same_normalized_content_is_not_collision(tmp_path):
    write_project(tmp_path, {"rag.jsonl": [
        {"chunk_id": "same", "text": "Same passage."},
        {"chunk_id": " same ", "content": " Same\r\n passage. "},
    ]})
    assert scan(tmp_path)[1]["findings"] == []


@pytest.mark.parametrize("bad_id", [None, "", "  ", True, False, [], {}, float("nan"), float("inf")])
def test_invalid_chunk_ids_abstain(tmp_path, bad_id):
    write_project(tmp_path, {"rag.jsonl": [
        {"chunk_id": bad_id, "text": "One"},
        {"chunk_id": bad_id, "text": "Two"},
    ]})
    assert scan(tmp_path)[1]["findings"] == []


def test_empty_nested_and_unsupported_content_abstains(tmp_path):
    write_project(tmp_path, {"rag.jsonl": [
        {"chunk_id": "same", "text": ""},
        {"chunk_id": "same", "text": None},
        {"chunk_id": "same", "text": ["not a string"]},
        {"chunk_id": "same", "metadata": {"text": "nested"}},
        {"metadata": {"chunk_id": "same"}, "text": "nested ID"},
        {"chunk_id": "same", "text": "Only usable passage"},
    ]})
    assert scan(tmp_path)[1]["findings"] == []


@pytest.mark.parametrize("field", ["text", "content", "document", "body", "chunk", "page_content"])
def test_explicit_content_aliases_are_supported(tmp_path, field):
    write_project(tmp_path, {"rag.jsonl": [
        {"chunk_id": 7, field: "One"},
        {"chunk_id": "7", field: "Two"},
    ]})
    ret, report = scan(tmp_path)
    assert ret == 1
    assert {r["field"] for r in report["findings"][0]["evidence"]["sample_records"]} == {field}


def test_id_case_is_preserved_and_first_nonempty_content_alias_wins(tmp_path):
    write_project(tmp_path, {"rag.jsonl": [
        {"chunk_id": "A", "text": "Same", "content": "Different ignored value"},
        {"chunk_id": "A", "text": "Same", "content": "Another ignored value"},
        {"chunk_id": "a", "text": "Case sensitive"},
    ]})
    assert scan(tmp_path)[1]["findings"] == []


@pytest.mark.parametrize("role", ["training_dataset", "evaluation_dataset", "benchmark_dataset"])
def test_non_rag_roles_abstain(tmp_path, role):
    write_project(tmp_path, {"rag.jsonl": [
        {"chunk_id": "same", "text": "One"}, {"chunk_id": "same", "text": "Two"},
    ]}, roles=[role])
    assert scan(tmp_path)[1]["findings"] == []


def test_evidence_includes_conflict_even_after_many_identical_records(tmp_path):
    rows = [{"chunk_id": "same", "text": "Repeated passage"} for _ in range(30)]
    rows.append({"chunk_id": "same", "text": "Different passage"})
    write_project(tmp_path, {"rag.jsonl": rows})
    _, report = scan(tmp_path)
    finding = report["findings"][0]
    evidence = finding["evidence"]
    assert evidence["record_count"] == 31
    assert evidence["distinct_content_count"] == 2
    assert evidence["evidence_truncated"] is True
    assert len(evidence["sample_records"]) == 20
    assert len(finding["locations"]) == 20
    assert len({r["content_hash"] for r in evidence["sample_records"]}) == 2


@pytest.mark.parametrize("issue", ["row_limit", "parse_failure", "size_limit"])
def test_partial_artifacts_abstain(tmp_path, issue):
    limits = {"max_rows_per_artifact": 2} if issue == "row_limit" else None
    if issue == "size_limit":
        limits = {"max_file_mb": 1}
    write_project(tmp_path, {"rag.jsonl": [
        {"chunk_id": "same", "text": "One"},
        {"chunk_id": "same", "text": "Two"},
        {"chunk_id": "same", "text": "Three"},
    ]}, limits=limits)
    if issue == "parse_failure":
        with (tmp_path / "rag.jsonl").open("a", encoding="utf-8") as f:
            f.write("{bad json}\n")
    elif issue == "size_limit":
        (tmp_path / "rag.jsonl").write_text("x" * (1024 * 1024 + 1), encoding="utf-8")
    ret, report = scan(tmp_path)
    assert ret == 0
    assert report["findings"] == []
    assert report["diagnostics"]


def test_deterministic_across_traversal_order(tmp_path, monkeypatch):
    write_project(tmp_path, {
        "first.jsonl": [{"chunk_id": "one", "text": "One"}, {"chunk_id": "one", "text": "Two"}],
        "second.jsonl": [{"chunk_id": "two", "text": "Three"}, {"chunk_id": "two", "text": "Four"}],
    })
    first = scan(tmp_path)[1]
    discover = cli.discover_files
    monkeypatch.setattr(cli, "discover_files", lambda *args, **kw: list(reversed(discover(*args, **kw))))
    second = scan(tmp_path)[1]
    for report in (first, second):
        report["scan"].pop("started_at")
        report["scan"].pop("completed_at")
    assert first == second
    assert len(first["findings"]) == 2


def test_project_index_exposes_only_redacted_chunk_records(tmp_path):
    config_data = write_project(tmp_path, {"rag.jsonl": [
        {"chunk_id": "sensitive-ID", "text": "Private content"},
    ]})
    config = parse_and_validate_config_dict(config_data)
    index = ProjectIndex(config)
    index.build([create_artifact_from_file(str(tmp_path), "rag.jsonl", config)])
    records = index.get_rag_chunk_records()
    assert len(records) == 1
    record = records[0]
    assert record.artifact_path == "rag.jsonl"
    assert record.row_num == 1
    assert record.content_field == "text"
    assert record.chunk_id_hash.startswith("sha256:")
    assert record.content_hash.startswith("sha256:")
    assert "sensitive-ID" not in repr(record)
    assert "Private content" not in repr(record)
