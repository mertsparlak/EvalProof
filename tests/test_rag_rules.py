from __future__ import annotations

import json
from pathlib import Path

from evalproof.cli import main


def scan_json(root: Path) -> dict:
    output = root.parent / f"{root.name}-report.json"
    ret = main(["scan", str(root), "--json", "--output", str(output)])
    report = json.loads(output.read_text(encoding="utf-8"))
    report["_return_code"] = ret
    return report


def write_config(root: Path, body: str) -> None:
    (root / "evalproof.yaml").write_text(body, encoding="utf-8")


def findings_by_rule(report: dict, rule_id: str) -> list[dict]:
    return [finding for finding in report["findings"] if finding["rule_id"] == rule_id]


def test_unreachable_context_id_reports_missing_scalar_and_list_references(tmp_path):
    write_config(
        tmp_path,
        """
artifacts:
  - path: eval.jsonl
    roles: [evaluation_dataset]
  - path: corpus.jsonl
    roles: [rag_document]
""".lstrip(),
    )
    (tmp_path / "eval.jsonl").write_text(
        "\n".join(
            [
                json.dumps({"id": "case-1", "context_id": "doc-a"}),
                json.dumps({"id": "case-2", "retrieved_context_ids": ["doc-a", "doc-missing", "DOC-B"]}),
            ]
        )
        + "\n",
        encoding="utf-8",
    )
    (tmp_path / "corpus.jsonl").write_text(
        "\n".join([json.dumps({"doc_id": "doc-a"}), json.dumps({"doc_id": "doc-b"})]) + "\n",
        encoding="utf-8",
    )

    report = scan_json(tmp_path)

    findings = findings_by_rule(report, "rag.unreachable_context_id")
    assert len(findings) == 1
    finding = findings[0]
    assert finding["severity"] == "high"
    assert finding["confidence"] == "confirmed"
    assert finding["locations"] == [{"role": "primary", "path": "eval.jsonl", "row": 2}]
    assert finding["evidence"]["reference_fields"] == ["retrieved_context_ids"]
    assert finding["evidence"]["missing_reference_count"] == 2
    assert "doc-missing" not in json.dumps(finding)
    assert "DOC-B" not in json.dumps(finding)


def test_unreachable_context_id_ignores_nested_and_unidentified_artifacts(tmp_path):
    write_config(
        tmp_path,
        """
artifacts:
  - path: eval.jsonl
    roles: [evaluation_dataset]
  - path: corpus.jsonl
    roles: [rag_document]
""".lstrip(),
    )
    (tmp_path / "eval.jsonl").write_text(
        json.dumps({"retrieval": {"context_id": "not-observed"}, "prompt": "context_id=not-observed"}) + "\n",
        encoding="utf-8",
    )
    (tmp_path / "corpus.jsonl").write_text(json.dumps({"metadata": {"doc_id": "doc-a"}}) + "\n", encoding="utf-8")

    report = scan_json(tmp_path)

    assert findings_by_rule(report, "rag.unreachable_context_id") == []


def test_unreachable_context_id_is_deterministic_and_silent_without_rag_artifacts(tmp_path):
    write_config(
        tmp_path,
        """
artifacts:
  - path: eval.jsonl
    roles: [evaluation_dataset]
""".lstrip(),
    )
    (tmp_path / "eval.jsonl").write_text(json.dumps({"doc_id": "missing"}) + "\n", encoding="utf-8")

    first = scan_json(tmp_path)
    second = scan_json(tmp_path)
    for report in (first, second):
        report["scan"].pop("started_at", None)
        report["scan"].pop("completed_at", None)

    assert findings_by_rule(first, "rag.unreachable_context_id") == []
    assert first == second
