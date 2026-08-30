from __future__ import annotations

import json
from pathlib import Path

from evalproof.cli import main


def scan_json(root: Path, *extra_args: str) -> tuple[int, dict]:
    output = root.parent / "dataset-integrity-report.json"
    ret = main(["scan", str(root), "--json", "--output", str(output), *extra_args])
    return ret, json.loads(output.read_text(encoding="utf-8"))


def write_config(root: Path, body: str) -> None:
    (root / "evalproof.yaml").write_text(body, encoding="utf-8")


def findings_by_rule(report: dict, rule_id: str) -> list[dict]:
    return [finding for finding in report["findings"] if finding["rule_id"] == rule_id]


def test_sample_id_collision_detects_duplicate_ids_without_raw_id_evidence(tmp_path):
    write_config(
        tmp_path,
        """
artifacts:
  - path: eval.jsonl
    roles: [evaluation_dataset]
""".lstrip(),
    )
    (tmp_path / "eval.jsonl").write_text(
        '{"sample_id":"case-1","prompt":"first"}\n'
        '{"sample_id":" case-1 ","prompt":"different"}\n',
        encoding="utf-8",
    )

    ret, report = scan_json(tmp_path, "--rules", "dataset.sample_id_collision")

    assert ret == 1
    findings = findings_by_rule(report, "dataset.sample_id_collision")
    assert len(findings) == 1
    finding = findings[0]
    assert finding["severity"] == "high"
    assert finding["confidence"] == "confirmed"
    assert finding["evidence"]["duplicate_count"] == 2
    assert finding["evidence"]["distinct_content_count"] == 2
    assert finding["evidence"]["sample_id_hash"].startswith("sha256:")
    assert "case-1" not in json.dumps(finding)


def test_sample_id_collision_is_scoped_to_each_artifact(tmp_path):
    write_config(
        tmp_path,
        """
artifacts:
  - path: eval_a.jsonl
    roles: [evaluation_dataset]
  - path: eval_b.jsonl
    roles: [evaluation_dataset]
""".lstrip(),
    )
    (tmp_path / "eval_a.jsonl").write_text('{"id":"1","prompt":"a"}\n', encoding="utf-8")
    (tmp_path / "eval_b.jsonl").write_text('{"id":"1","prompt":"b"}\n', encoding="utf-8")

    ret, report = scan_json(tmp_path, "--rules", "dataset.sample_id_collision")

    assert ret == 0
    assert findings_by_rule(report, "dataset.sample_id_collision") == []


def test_empty_evaluation_input_groups_only_explicitly_empty_canonical_fields(tmp_path):
    write_config(
        tmp_path,
        """
artifacts:
  - path: eval.jsonl
    roles: [evaluation_dataset]
""".lstrip(),
    )
    (tmp_path / "eval.jsonl").write_text(
        '{"prompt":"   "}\n'
        '{"question":null}\n'
        '{"input":"usable"}\n'
        '{"messages":[{"role":"user","content":"usable"}],"prompt":""}\n'
        '{"metadata":"no input field"}\n',
        encoding="utf-8",
    )

    ret, report = scan_json(tmp_path, "--rules", "dataset.empty_evaluation_input")

    assert ret == 1
    findings = findings_by_rule(report, "dataset.empty_evaluation_input")
    assert len(findings) == 1
    finding = findings[0]
    assert finding["severity"] == "high"
    assert finding["confidence"] == "confirmed"
    assert finding["evidence"]["affected_count"] == 2
    assert finding["evidence"]["row_locations"] == [{"path": "eval.jsonl", "row": 1}, {"path": "eval.jsonl", "row": 2}]
    assert "usable" not in json.dumps(finding)


def test_dataset_integrity_findings_are_deterministic(tmp_path):
    write_config(
        tmp_path,
        """
artifacts:
  - path: eval.jsonl
    roles: [evaluation_dataset]
""".lstrip(),
    )
    (tmp_path / "eval.jsonl").write_text(
        '{"id":"same","prompt":"first"}\n'
        '{"id":"same","prompt":"second"}\n'
        '{"prompt":" "}\n',
        encoding="utf-8",
    )

    reports = []
    for index in range(2):
        ret, report = scan_json(tmp_path, "--rules", "dataset.sample_id_collision,dataset.empty_evaluation_input")
        assert ret == 1
        report["scan"]["started_at"] = "<timestamp>"
        report["scan"]["completed_at"] = "<timestamp>"
        reports.append(report)

    assert reports[0] == reports[1]
