from __future__ import annotations

import json

from evalproof.cli import main


RULE_ID = "rag.empty_or_corrupted_document"


def write_config(root, rag_name: str = "rag.jsonl") -> None:
    (root / "evalproof.yaml").write_text(
        "artifacts:\n"
        "  - path: eval.jsonl\n"
        "    roles: [evaluation_dataset]\n"
        f"  - path: {rag_name}\n"
        "    roles: [rag_document]\n"
        "similarity:\n"
        "  enabled: false\n",
        encoding="utf-8",
    )


def scan_rule(root):
    output = root.parent / "empty-rag-report.json"
    result = main(["scan", str(root), "--json", "--output", str(output), "--rules", RULE_ID])
    return result, json.loads(output.read_text(encoding="utf-8"))


def test_empty_rag_record_reports_without_raw_content(tmp_path):
    write_config(tmp_path)
    (tmp_path / "eval.jsonl").write_text('{"doc_id":"doc-1","prompt":"question"}\n', encoding="utf-8")
    (tmp_path / "rag.jsonl").write_text('{"id":"doc-1","text":"   "}\n', encoding="utf-8")

    result, report = scan_rule(tmp_path)

    assert result == 0
    findings = [item for item in report["findings"] if item["rule_id"] == RULE_ID]
    assert len(findings) == 1
    finding = findings[0]
    assert finding["severity"] == "medium"
    assert finding["confidence"] == "confirmed"
    assert finding["evidence"]["empty_record_count"] == 1
    assert finding["evidence"]["content_fields"] == ["text"]
    assert "doc-1" not in json.dumps(finding)
    assert "   " not in json.dumps(finding)


def test_empty_rag_artifact_reports_only_when_evaluation_artifact_exists(tmp_path):
    write_config(tmp_path, rag_name="rag.md")
    (tmp_path / "eval.jsonl").write_text('{"prompt":"question"}\n', encoding="utf-8")
    (tmp_path / "rag.md").write_text("   \n", encoding="utf-8")

    result, report = scan_rule(tmp_path)

    assert result == 0
    findings = [item for item in report["findings"] if item["rule_id"] == RULE_ID]
    assert len(findings) == 1
    assert findings[0]["evidence"]["state"] == "empty"
    assert findings[0]["evidence"]["observed_text_length"] == 0


def test_empty_rag_rule_is_silent_without_evaluation_artifact(tmp_path):
    (tmp_path / "evalproof.yaml").write_text(
        "artifacts:\n"
        "  - path: rag.jsonl\n"
        "    roles: [rag_document]\n",
        encoding="utf-8",
    )
    (tmp_path / "rag.jsonl").write_text("\n", encoding="utf-8")

    output = tmp_path.parent / "empty-rag-report.json"
    result = main(["scan", str(tmp_path), "--json", "--output", str(output), "--rules", RULE_ID])
    report = json.loads(output.read_text(encoding="utf-8"))

    assert result == 0
    assert [item for item in report["findings"] if item["rule_id"] == RULE_ID] == []


def test_empty_rag_rule_abstains_on_partial_index(tmp_path):
    write_config(tmp_path)
    (tmp_path / "eval.jsonl").write_text('{"prompt":"question"}\n', encoding="utf-8")
    (tmp_path / "rag.jsonl").write_text(
        '{"id":"doc-1","text":"usable"}\n'
        '{"id":"doc-2","text":"broken"\n',
        encoding="utf-8",
    )

    result, report = scan_rule(tmp_path)

    assert result == 0
    assert [item for item in report["findings"] if item["rule_id"] == RULE_ID] == []
    assert any(item["code"] == "artifact.row_parse_failed" for item in report["diagnostics"])
