from __future__ import annotations

import json

from evalproof.cli import main


def write_config(root, artifacts: str) -> None:
    (root / "evalproof.yaml").write_text(
        "similarity:\n  threshold: 0.7\n" + artifacts,
        encoding="utf-8",
    )


def scan_json(root):
    output = root / "report.json"
    result = main(["scan", str(root), "--json", "--output", str(output)])
    return result, json.loads(output.read_text(encoding="utf-8"))


def test_internal_near_duplicates_are_grouped_and_evidence_is_bounded(tmp_path):
    write_config(
        tmp_path,
        "artifacts:\n  - path: train.jsonl\n    roles: [training_dataset]\n",
    )
    rows = [
        '{"prompt": "Machine learning evaluation sample about feature extraction."}',
        '{"prompt": "Machine learning evaluation samples about feature extraction."}',
        '{"prompt": "Machine learning evaluation sample about feature extraction!"}',
        '{"prompt": "Machine learning evaluation sample about feature extraction?"}',
    ]
    (tmp_path / "train.jsonl").write_text("\n".join(rows) + "\n", encoding="utf-8")

    result, report = scan_json(tmp_path)

    assert result == 0
    findings = [
        item
        for item in report["findings"]
        if item["rule_id"] == "contamination.duplicate_train_near_duplicate"
    ]
    assert len(findings) == 1
    evidence = findings[0]["evidence"]
    assert evidence["artifact_paths"] == ["train.jsonl"]
    assert evidence["near_duplicate_pair_count"] >= 3
    assert evidence["affected_row_count"] == 4
    assert len(evidence["sample_pairs"]) <= 20
    assert evidence["evidence_truncated"] is False
    assert "snippet" not in json.dumps(evidence).lower()


def test_train_eval_near_duplicates_remain_one_finding_per_evaluation_row(tmp_path):
    write_config(
        tmp_path,
        "artifacts:\n"
        "  - path: train.jsonl\n"
        "    roles: [training_dataset]\n"
        "  - path: eval.jsonl\n"
        "    roles: [evaluation_dataset]\n",
    )
    (tmp_path / "train.jsonl").write_text(
        '{"prompt": "The model evaluates retrieval quality for customer support cases."}\n'
        '{"prompt": "The model evaluates retrieval quality for customer support case."}\n',
        encoding="utf-8",
    )
    (tmp_path / "eval.jsonl").write_text(
        '{"prompt": "The model evaluates retrieval quality for customer support cases!"}\n'
        '{"prompt": "The model evaluates retrieval quality for customer support cases?"}\n',
        encoding="utf-8",
    )

    result, report = scan_json(tmp_path)

    assert result == 1
    findings = [
        item
        for item in report["findings"]
        if item["rule_id"] == "contamination.train_eval_near_duplicate"
    ]
    assert len(findings) == 2
    for finding in findings:
        evidence = finding["evidence"]
        assert evidence["overlap_count"] >= 1
        assert len(evidence["matched_training_records"]) <= 20
        assert evidence["evidence_truncated"] is False
        assert "snippet" not in json.dumps(evidence).lower()


def test_sensitive_values_are_grouped_by_artifact_and_detector(tmp_path):
    write_config(
        tmp_path,
        "artifacts:\n  - path: eval.jsonl\n    roles: [evaluation_dataset]\n",
    )
    (tmp_path / "eval.jsonl").write_text(
        '{"text": "first@example.com second@example.com api_key=1234567890abcdef"}\n'
        '{"text": "third@example.com phone +90 555 123 4567"}\n',
        encoding="utf-8",
    )

    result, report = scan_json(tmp_path)

    assert result == 0
    findings = [
        item
        for item in report["findings"]
        if item["rule_id"] == "contamination.sensitive_value_exposure"
    ]
    assert {item["evidence"]["detector_type"] for item in findings} == {"email", "api_key", "phone"}
    assert len(findings) == 3
    for finding in findings:
        evidence = finding["evidence"]
        assert evidence["exposure_count"] >= 1
        assert evidence["distinct_value_count"] >= 1
        assert len(evidence["sample_locations"]) <= 20
        assert len(evidence["redacted_values"]) <= 20
        assert evidence["evidence_truncated"] is False
        assert "first@example.com" not in json.dumps(evidence)
        assert "snippet" not in json.dumps(evidence).lower()


def test_high_volume_evidence_is_truncated_deterministically(tmp_path):
    write_config(
        tmp_path,
        "artifacts:\n  - path: train.jsonl\n    roles: [training_dataset]\n",
    )
    rows = [
        '{"prompt": "A shared benchmark prompt about retrieval quality and evaluation."}'
    ]
    rows.extend(
        '{{"prompt": "A shared benchmark prompt about retrieval quality and evaluation {}."}}'.format(i)
        for i in range(1, 30)
    )
    (tmp_path / "train.jsonl").write_text("\n".join(rows) + "\n", encoding="utf-8")

    first_result, first_report = scan_json(tmp_path)
    second_result, second_report = scan_json(tmp_path)

    assert first_result == second_result == 0
    first = [
        item
        for item in first_report["findings"]
        if item["rule_id"] == "contamination.duplicate_train_near_duplicate"
    ][0]
    second = [
        item
        for item in second_report["findings"]
        if item["rule_id"] == "contamination.duplicate_train_near_duplicate"
    ][0]
    assert first["evidence"]["evidence_truncated"] is True
    assert len(first["evidence"]["sample_pairs"]) == 20
    assert first["fingerprint"] == second["fingerprint"]
    assert first["evidence"] == second["evidence"]

def test_internal_near_duplicates_group_across_training_artifacts(tmp_path):
    write_config(
        tmp_path,
        "artifacts:\n"
        "  - path: train_a.jsonl\n"
        "    roles: [training_dataset]\n"
        "  - path: train_b.jsonl\n"
        "    roles: [training_dataset]\n",
    )
    (tmp_path / "train_a.jsonl").write_text(
        '{"prompt": "Shared training retrieval quality example for evaluation."}\n',
        encoding="utf-8",
    )
    (tmp_path / "train_b.jsonl").write_text(
        '{"prompt": "Shared training retrieval quality example for evaluations."}\n',
        encoding="utf-8",
    )

    result, report = scan_json(tmp_path)

    assert result == 0
    findings = [
        item
        for item in report["findings"]
        if item["rule_id"] == "contamination.duplicate_train_near_duplicate"
    ]
    assert len(findings) == 1
    evidence = findings[0]["evidence"]
    assert evidence["artifact_paths"] == ["train_a.jsonl", "train_b.jsonl"]
    assert evidence["near_duplicate_pair_count"] == 1
    assert evidence["affected_row_count"] == 2