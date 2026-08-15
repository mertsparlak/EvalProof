from __future__ import annotations

import json
from pathlib import Path

from evalproof.cli import main


def scan_json(root: Path, *extra_args: str) -> tuple[int, dict]:
    output = root.parent / f"{root.name}-report.json"
    ret = main(["scan", str(root), "--json", "--output", str(output), *extra_args])
    assert output.exists()
    return ret, json.loads(output.read_text(encoding="utf-8"))


def findings_by_rule(report: dict, rule_id: str) -> list[dict]:
    return [finding for finding in report["findings"] if finding["rule_id"] == rule_id]


def write_config(root: Path, body: str) -> None:
    (root / "evalproof.yaml").write_text(body, encoding="utf-8")


def assert_rule_contract(finding: dict, severity: str, confidence: str, evidence_keys: set[str]) -> None:
    assert finding["severity"] == severity
    assert finding["confidence"] == confidence
    assert evidence_keys.issubset(finding["evidence"])
    assert finding["impact"]
    assert finding["recommendation"]
    assert finding["fingerprint"].startswith("sha256:")


def test_exact_overlap_and_duplicate_evidence_contracts(tmp_path):
    write_config(
        tmp_path,
        """
artifacts:
  - path: train.jsonl
    roles: [training_dataset]
  - path: eval.jsonl
    roles: [evaluation_dataset]
""".lstrip(),
    )
    (tmp_path / "train.jsonl").write_text('{"prompt":"same"}\n{"prompt":"train dup"}\n{"prompt":"train dup"}\n', encoding="utf-8")
    (tmp_path / "eval.jsonl").write_text('{"prompt":"same"}\n{"prompt":"eval dup"}\n{"prompt":"eval dup"}\n', encoding="utf-8")

    ret, report = scan_json(tmp_path)

    assert ret == 1
    assert_rule_contract(
        findings_by_rule(report, "contamination.train_eval_overlap")[0],
        "critical",
        "confirmed",
        {"training_artifact", "training_row", "evaluation_artifact", "evaluation_row", "normalized_record_hash", "overlap_count"},
    )
    assert_rule_contract(
        findings_by_rule(report, "contamination.duplicate_eval_sample")[0],
        "high",
        "confirmed",
        {"artifact_path", "duplicate_row_locations", "normalized_record_hash", "duplicate_count"},
    )
    assert_rule_contract(
        findings_by_rule(report, "contamination.duplicate_train_sample")[0],
        "medium",
        "confirmed",
        {"artifact_path", "duplicate_row_locations", "normalized_record_hash", "duplicate_count"},
    )


def test_near_duplicate_evidence_contracts_and_exact_duplicate_guard(tmp_path):
    write_config(
        tmp_path,
        """
similarity:
  threshold: 0.7
artifacts:
  - path: train.jsonl
    roles: [training_dataset]
  - path: eval.jsonl
    roles: [evaluation_dataset]
""".lstrip(),
    )
    (tmp_path / "train.jsonl").write_text(
        '{"prompt":"Exact shared row should be exact only."}\n'
        '{"prompt":"The Apollo program landed humans on the Moon in 1969."}\n'
        '{"prompt":"Training near duplicate phrase for internal check."}\n'
        '{"prompt":"Training near duplicate phrases for internal check!"}\n',
        encoding="utf-8",
    )
    (tmp_path / "eval.jsonl").write_text(
        '{"prompt":"Exact shared row should be exact only."}\n'
        '{"prompt":"The Apollo program put humans on the Moon in 1969."}\n'
        '{"prompt":"Evaluation near duplicate phrase for internal check."}\n'
        '{"prompt":"Evaluation near duplicate phrases for internal check!"}\n',
        encoding="utf-8",
    )

    ret, report = scan_json(tmp_path, "--fail-on", "critical")

    assert ret == 1
    train_eval_near = findings_by_rule(report, "contamination.train_eval_near_duplicate")
    assert train_eval_near
    assert all(f["evidence"].get("similarity_score") < 1.0 for f in train_eval_near)
    assert_rule_contract(
        train_eval_near[0],
        "high",
        "likely",
        {"training_artifact", "training_row", "evaluation_artifact", "evaluation_row", "similarity_score", "configured_threshold"},
    )
    assert_rule_contract(
        findings_by_rule(report, "contamination.duplicate_eval_near_duplicate")[0],
        "medium",
        "likely",
        {"artifact_path", "evaluation_row", "duplicate_row", "similarity_score", "configured_threshold"},
    )
    assert_rule_contract(
        findings_by_rule(report, "contamination.duplicate_train_near_duplicate")[0],
        "low",
        "likely",
        {"artifact_path", "training_row", "duplicate_row", "similarity_score", "configured_threshold"},
    )


def test_near_duplicate_threshold_below_match_does_not_emit(tmp_path):
    write_config(
        tmp_path,
        """
similarity:
  threshold: 0.95
artifacts:
  - path: train.jsonl
    roles: [training_dataset]
  - path: eval.jsonl
    roles: [evaluation_dataset]
""".lstrip(),
    )
    (tmp_path / "train.jsonl").write_text('{"prompt":"The quick brown fox jumps over the lazy dog."}\n', encoding="utf-8")
    (tmp_path / "eval.jsonl").write_text('{"prompt":"The quick brown fox jumps over a lazy dog."}\n', encoding="utf-8")

    ret, report = scan_json(tmp_path)

    assert ret == 0
    assert findings_by_rule(report, "contamination.train_eval_near_duplicate") == []


def test_rag_answer_leakage_positive_and_negative_guards(tmp_path):
    write_config(
        tmp_path,
        """
artifacts:
  - path: eval.jsonl
    roles: [evaluation_dataset]
  - path: rag.md
    roles: [rag_document]
""".lstrip(),
    )
    (tmp_path / "eval.jsonl").write_text(
        '{"prompt":"leaked","answer":"The hidden answer is documented in retrieval."}\n'
        '{"prompt":"trivial","answer":"yes"}\n'
        '{"prompt":"no canonical answer","expected_output":"The hidden answer is documented in retrieval."}\n',
        encoding="utf-8",
    )
    (tmp_path / "rag.md").write_text("The hidden answer is documented in retrieval.", encoding="utf-8")

    ret, report = scan_json(tmp_path)

    assert ret == 1
    rag_findings = findings_by_rule(report, "contamination.rag_answer_leakage")
    assert len(rag_findings) == 1
    assert_rule_contract(
        rag_findings[0],
        "high",
        "likely",
        {"evaluation_artifact", "evaluation_row", "answer_field", "rag_artifact", "matched_normalized_text"},
    )
    assert rag_findings[0]["evidence"]["evaluation_row"] == 1


def test_repro_and_fingerprint_rules_only_emit_with_objective_evidence(tmp_path):
    write_config(
        tmp_path,
        """
artifacts:
  - path: results/missing.json
    roles: [evaluation_result]
  - path: results/comparable.json
    roles: [evaluation_result]
  - path: results/no_fingerprint.json
    roles: [evaluation_result]
  - path: eval.jsonl
    roles: [evaluation_dataset]
""".lstrip(),
    )
    (tmp_path / "results").mkdir()
    (tmp_path / "eval.jsonl").write_text('{"prompt":"sample"}\n', encoding="utf-8")
    (tmp_path / "results" / "missing.json").write_text('{"model_id":"demo"}', encoding="utf-8")
    (tmp_path / "results" / "comparable.json").write_text(
        '{"model_id":"demo","generation_parameters":{},"prompt_version":"p1","dataset_fingerprint":"sha256:wrong",'
        '"metric_name":"accuracy","metric_threshold":0.8,"timestamp":"2026-01-01T00:00:00Z"}',
        encoding="utf-8",
    )
    (tmp_path / "results" / "no_fingerprint.json").write_text(
        '{"model_id":"demo","generation_parameters":{},"prompt_version":"p1","dataset_version":"v1",'
        '"metric_name":"accuracy","metric_threshold":0.8,"timestamp":"2026-01-01T00:00:00Z"}',
        encoding="utf-8",
    )

    ret, report = scan_json(tmp_path)

    assert ret == 1
    missing = findings_by_rule(report, "contamination.missing_repro_metadata")
    assert len(missing) == 1
    assert_rule_contract(missing[0], "high", "confirmed", {"result_artifact", "missing_metadata_fields"})
    mismatch = findings_by_rule(report, "contamination.fingerprint_mismatch")
    assert len(mismatch) == 1
    assert_rule_contract(
        mismatch[0],
        "high",
        "confirmed",
        {"result_artifact", "referenced_fingerprint", "candidate_artifact_paths", "artifact_type"},
    )
    assert mismatch[0]["locations"][0]["path"] == "results/comparable.json"


def test_prompt_and_sensitive_heuristics_are_actionable_and_do_not_fail_default_ci(tmp_path):
    write_config(
        tmp_path,
        """
artifacts:
  - path: prompts/unsafe.md
    roles: [prompt_template]
  - path: prompts/safe.md
    roles: [prompt_template]
  - path: eval.jsonl
    roles: [evaluation_dataset]
""".lstrip(),
    )
    (tmp_path / "prompts").mkdir()
    (tmp_path / "prompts" / "unsafe.md").write_text("System\n\n{{ context }}\n\nQuestion: {{ question }}", encoding="utf-8")
    (tmp_path / "prompts" / "safe.md").write_text("BEGIN CONTEXT\n{{ context }}\nEND CONTEXT", encoding="utf-8")
    (tmp_path / "eval.jsonl").write_text(
        '{"prompt":"email support@example.com"}\n'
        '{"prompt":"short fixture api_key = short"}\n',
        encoding="utf-8",
    )

    ret, report = scan_json(tmp_path)

    assert ret == 0
    prompt_findings = findings_by_rule(report, "contamination.untrusted_context_interpolation")
    assert len(prompt_findings) == 1
    assert prompt_findings[0]["locations"][0]["path"] == "prompts/unsafe.md"
    assert_rule_contract(prompt_findings[0], "medium", "heuristic", {"prompt_artifact", "variable_name", "line_number", "snippet"})
    sensitive_findings = findings_by_rule(report, "contamination.sensitive_value_exposure")
    assert len(sensitive_findings) == 1
    assert sensitive_findings[0]["evidence"]["detector_type"] == "email"
    assert_rule_contract(sensitive_findings[0], "medium", "heuristic", {"artifact_path", "detector_type", "exposure_count", "distinct_value_count", "sample_locations", "redacted_values", "evidence_truncated"})
    assert "support@example.com" not in json.dumps(sensitive_findings[0])


def test_malformed_artifacts_emit_diagnostics_not_contamination_findings(tmp_path):
    write_config(
        tmp_path,
        """
artifacts:
  - path: eval.jsonl
    roles: [evaluation_dataset]
""".lstrip(),
    )
    (tmp_path / "eval.jsonl").write_text('{bad json}\n', encoding="utf-8")

    ret, report = scan_json(tmp_path)

    assert ret == 0
    assert report["findings"] == []
    assert {diagnostic["code"] for diagnostic in report["diagnostics"]} == {"artifact.row_parse_failed"}