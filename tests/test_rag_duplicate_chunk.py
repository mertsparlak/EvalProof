from __future__ import annotations

import json

from evalproof.cli import main


RULE_ID = "rag.duplicate_chunk_in_corpus"


def write_config(root, include_eval: bool = True) -> None:
    evaluation = "  - path: eval.jsonl\n    roles: [evaluation_dataset]\n" if include_eval else ""
    (root / "evalproof.yaml").write_text(
        "artifacts:\n"
        + evaluation
        + "  - path: rag.jsonl\n"
        "    roles: [rag_document]\n"
        "similarity:\n"
        "  enabled: false\n",
        encoding="utf-8",
    )


def scan_rule(root):
    output = root.parent / "duplicate-rag-report.json"
    result = main(["scan", str(root), "--json", "--output", str(output), "--rules", RULE_ID])
    return result, json.loads(output.read_text(encoding="utf-8"))


def test_duplicate_rag_chunks_report_normalized_exact_matches_without_raw_content(tmp_path):
    write_config(tmp_path)
    (tmp_path / "eval.jsonl").write_text('{"prompt":"question"}\n', encoding="utf-8")
    (tmp_path / "rag.jsonl").write_text(
        '{"id":"doc-a","chunk":"Same chunk text."}\n'
        '{"id":"doc-b","chunk":" Same   chunk\\ntext. "}\n'
        '{"id":"doc-c","chunk":"Different chunk."}\n',
        encoding="utf-8",
    )

    result, report = scan_rule(tmp_path)

    assert result == 0
    findings = [item for item in report["findings"] if item["rule_id"] == RULE_ID]
    assert len(findings) == 1
    finding = findings[0]
    assert finding["severity"] == "medium"
    assert finding["confidence"] == "confirmed"
    assert finding["evidence"]["duplicate_count"] == 2
    assert finding["evidence"]["content_fields"] == ["chunk"]
    assert finding["evidence"]["artifact_paths"] == ["rag.jsonl"]
    assert finding["evidence"]["row_locations"] == [
        {"path": "rag.jsonl", "row": 1, "field": "chunk"},
        {"path": "rag.jsonl", "row": 2, "field": "chunk"},
    ]
    assert "Same chunk text." not in json.dumps(finding)
    assert "doc-a" not in json.dumps(finding)


def test_duplicate_rag_chunks_ignore_near_duplicates_and_unsupported_values(tmp_path):
    write_config(tmp_path)
    (tmp_path / "eval.jsonl").write_text('{"prompt":"question"}\n', encoding="utf-8")
    (tmp_path / "rag.jsonl").write_text(
        '{"chunk":"The same concept."}\n'
        '{"chunk":"The same concepts."}\n'
        '{"chunk":["The same concept."]}\n'
        '{"metadata":{"chunk":"The same concept."}}\n',
        encoding="utf-8",
    )

    result, report = scan_rule(tmp_path)

    assert result == 0
    assert [item for item in report["findings"] if item["rule_id"] == RULE_ID] == []


def test_duplicate_rag_chunks_are_silent_without_evaluation_artifact(tmp_path):
    write_config(tmp_path, include_eval=False)
    (tmp_path / "rag.jsonl").write_text(
        '{"chunk":"duplicate"}\n'
        '{"chunk":"duplicate"}\n',
        encoding="utf-8",
    )

    result, report = scan_rule(tmp_path)

    assert result == 0
    assert [item for item in report["findings"] if item["rule_id"] == RULE_ID] == []


def test_duplicate_rag_chunks_are_deterministic(tmp_path):
    write_config(tmp_path)
    (tmp_path / "eval.jsonl").write_text('{"prompt":"question"}\n', encoding="utf-8")
    (tmp_path / "rag.jsonl").write_text(
        '{"text":"duplicate"}\n'
        '{"text":"duplicate"}\n',
        encoding="utf-8",
    )

    first_result, first_report = scan_rule(tmp_path)
    second_result, second_report = scan_rule(tmp_path)
    for report in (first_report, second_report):
        report["scan"]["started_at"] = "<timestamp>"
        report["scan"]["completed_at"] = "<timestamp>"

    assert first_result == second_result == 0
    assert first_report == second_report
