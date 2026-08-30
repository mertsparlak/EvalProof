from __future__ import annotations

import json
from pathlib import Path

from evalproof.cli import main


def scan_json(root: Path, *extra_args: str) -> tuple[int, dict]:
    output = root.parent / "rag-empty-report.json"
    ret = main(["scan", str(root), "--json", "--output", str(output), *extra_args])
    return ret, json.loads(output.read_text(encoding="utf-8"))


def write_config(root: Path, body: str) -> None:
    (root / "evalproof.yaml").write_text(body, encoding="utf-8")


def findings_by_rule(report: dict, rule_id: str) -> list[dict]:
    return [finding for finding in report["findings"] if finding["rule_id"] == rule_id]


def test_empty_referenced_rag_document_is_reported_without_raw_id_or_content(tmp_path):
    write_config(
        tmp_path,
        """
artifacts:
  - path: eval.jsonl
    roles: [evaluation_dataset]
  - path: rag.jsonl
    roles: [rag_document]
""".lstrip(),
    )
    (tmp_path / "eval.jsonl").write_text(
        '{"doc_id":"empty-doc","retrieved_context_ids":["full-doc"]}\n',
        encoding="utf-8",
    )
    (tmp_path / "rag.jsonl").write_text(
        '{"id":"empty-doc","text":"  "}\n'
        '{"id":"full-doc","content":"A complete document."}\n',
        encoding="utf-8",
    )

    ret, report = scan_json(tmp_path, "--rules", "rag.empty_referenced_document")

    assert ret == 1
    findings = findings_by_rule(report, "rag.empty_referenced_document")
    assert len(findings) == 1
    finding = findings[0]
    assert finding["severity"] == "high"
    assert finding["confidence"] == "confirmed"
    assert finding["evidence"]["empty_reference_count"] == 1
    assert finding["evidence"]["empty_reference_hashes"][0].startswith("sha256:")
    assert "empty-doc" not in json.dumps(finding)
    assert "complete document" not in json.dumps(finding)


def test_empty_rag_reference_is_not_reported_when_a_matching_record_has_content(tmp_path):
    write_config(
        tmp_path,
        """
artifacts:
  - path: eval.jsonl
    roles: [evaluation_dataset]
  - path: rag.jsonl
    roles: [rag_document]
""".lstrip(),
    )
    (tmp_path / "eval.jsonl").write_text('{"context_id":"doc-1"}\n', encoding="utf-8")
    (tmp_path / "rag.jsonl").write_text(
        '{"id":"doc-1","text":""}\n'
        '{"id":"doc-1","text":"usable content"}\n',
        encoding="utf-8",
    )

    ret, report = scan_json(tmp_path, "--rules", "rag.empty_referenced_document")

    assert ret == 0
    assert findings_by_rule(report, "rag.empty_referenced_document") == []


def test_unreferenced_empty_rag_document_and_unknown_content_shape_are_ignored(tmp_path):
    write_config(
        tmp_path,
        """
artifacts:
  - path: eval.jsonl
    roles: [evaluation_dataset]
  - path: rag.jsonl
    roles: [rag_document]
""".lstrip(),
    )
    (tmp_path / "eval.jsonl").write_text('{"prompt":"no context reference"}\n', encoding="utf-8")
    (tmp_path / "rag.jsonl").write_text(
        '{"id":"unused","text":""}\n'
        '{"id":"unknown","metadata":{"content":""}}\n',
        encoding="utf-8",
    )

    ret, report = scan_json(tmp_path, "--rules", "rag.empty_referenced_document")

    assert ret == 0
    assert findings_by_rule(report, "rag.empty_referenced_document") == []


def test_empty_rag_reference_finding_is_deterministic(tmp_path):
    write_config(
        tmp_path,
        """
artifacts:
  - path: eval.jsonl
    roles: [evaluation_dataset]
  - path: rag.jsonl
    roles: [rag_document]
""".lstrip(),
    )
    (tmp_path / "eval.jsonl").write_text('{"doc_id":"doc-1"}\n', encoding="utf-8")
    (tmp_path / "rag.jsonl").write_text('{"id":"doc-1","body":""}\n', encoding="utf-8")

    reports = []
    for _ in range(2):
        ret, report = scan_json(tmp_path, "--rules", "rag.empty_referenced_document")
        assert ret == 1
        report["scan"]["started_at"] = "<timestamp>"
        report["scan"]["completed_at"] = "<timestamp>"
        reports.append(report)

    assert reports[0] == reports[1]
