from __future__ import annotations

import json

from evalproof.cli import main


RULE_ID = "dataset.partial_sample_id_coverage"


def write_config(root, role: str = "evaluation_dataset", extra: str = "") -> None:
    (root / "evalproof.yaml").write_text(
        "artifacts:\n"
        "  - path: eval.jsonl\n"
        f"    roles: [{role}]\n"
        + extra,
        encoding="utf-8",
    )


def scan_rule(root):
    output = root.parent / "partial-id-report.json"
    result = main(["scan", str(root), "--json", "--output", str(output), "--rules", RULE_ID])
    return result, json.loads(output.read_text(encoding="utf-8"))


def test_partial_sample_id_coverage_reports_missing_rows_without_raw_ids(tmp_path):
    write_config(tmp_path)
    (tmp_path / "eval.jsonl").write_text(
        '{"id":"case-1","prompt":"first"}\n'
        '{"prompt":"missing id"}\n'
        '{"sample_id":"case-2","prompt":"second"}\n'
        '{"record_id":"   ","prompt":"blank id"}\n',
        encoding="utf-8",
    )

    result, report = scan_rule(tmp_path)

    assert result == 0
    findings = [item for item in report["findings"] if item["rule_id"] == RULE_ID]
    assert len(findings) == 1
    finding = findings[0]
    assert finding["severity"] == "medium"
    assert finding["confidence"] == "confirmed"
    assert finding["evidence"]["artifact_path"] == "eval.jsonl"
    assert finding["evidence"]["row_count"] == 4
    assert finding["evidence"]["identified_count"] == 2
    assert finding["evidence"]["missing_id_count"] == 2
    assert finding["evidence"]["coverage_ratio"] == 0.5
    assert finding["evidence"]["sample_id_fields"] == ["id", "sample_id"]
    assert finding["evidence"]["missing_row_locations"] == [
        {"path": "eval.jsonl", "row": 2},
        {"path": "eval.jsonl", "row": 4},
    ]
    assert finding["evidence"]["evidence_truncated"] is False
    assert "case-1" not in json.dumps(finding)
    assert "case-2" not in json.dumps(finding)


def test_partial_sample_id_coverage_ignores_fully_identified_and_unidentified_artifacts(tmp_path):
    write_config(tmp_path)
    (tmp_path / "eval.jsonl").write_text(
        '{"id":"case-1","prompt":"first"}\n'
        '{"sample_id":"case-2","prompt":"second"}\n',
        encoding="utf-8",
    )

    result, report = scan_rule(tmp_path)

    assert result == 0
    assert [item for item in report["findings"] if item["rule_id"] == RULE_ID] == []


def test_partial_sample_id_coverage_abstains_when_index_is_partial(tmp_path):
    write_config(tmp_path)
    (tmp_path / "eval.jsonl").write_text(
        '{"id":"case-1","prompt":"first"}\n'
        '{"prompt":"malformed"}\n'
        '{"id":"case-3","prompt":"third"}\n',
        encoding="utf-8",
    )
    text = (tmp_path / "eval.jsonl").read_text(encoding="utf-8")
    (tmp_path / "eval.jsonl").write_text(
        text.replace('{"prompt":"malformed"}', '{"prompt":"malformed"'),
        encoding="utf-8",
    )

    result, report = scan_rule(tmp_path)

    assert result == 0
    assert [item for item in report["findings"] if item["rule_id"] == RULE_ID] == []
    assert any(item["code"] == "artifact.row_parse_failed" for item in report["diagnostics"])


def test_partial_sample_id_coverage_supports_benchmark_artifacts_and_is_deterministic(tmp_path):
    write_config(tmp_path, role="benchmark_dataset")
    (tmp_path / "eval.jsonl").write_text(
        '{"example_id":"case-1","prompt":"first"}\n'
        '{"prompt":"missing"}\n',
        encoding="utf-8",
    )

    first_result, first_report = scan_rule(tmp_path)
    second_result, second_report = scan_rule(tmp_path)
    for report in (first_report, second_report):
        report["scan"]["started_at"] = "<timestamp>"
        report["scan"]["completed_at"] = "<timestamp>"

    assert first_result == second_result == 0
    assert first_report == second_report
    finding = [item for item in first_report["findings"] if item["rule_id"] == RULE_ID][0]
    assert finding["evidence"]["sample_id_fields"] == ["example_id"]


def test_partial_sample_id_coverage_ignores_artifact_with_no_ids(tmp_path):
    write_config(tmp_path)
    (tmp_path / "eval.jsonl").write_text(
        '{"prompt":"first"}\n'
        '{"prompt":"second"}\n',
        encoding="utf-8",
    )

    result, report = scan_rule(tmp_path)

    assert result == 0
    assert [item for item in report["findings"] if item["rule_id"] == RULE_ID] == []