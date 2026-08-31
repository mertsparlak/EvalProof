from __future__ import annotations

import hashlib
import json
import shutil
from pathlib import Path

from evalproof.cli import main


def write_config(root: Path, body: str) -> None:
    (root / "evalproof.yaml").write_text(body, encoding="utf-8")


def scan_json(root: Path) -> dict:
    output = root.parent / f"{root.name}-report.json"
    ret = main(["scan", str(root), "--json", "--output", str(output)])
    assert output.exists()
    report = json.loads(output.read_text(encoding="utf-8"))
    report["_return_code"] = ret
    return report


def findings_by_rule(report: dict, rule_id: str) -> list[dict]:
    return [finding for finding in report["findings"] if finding["rule_id"] == rule_id]


def jsonl_fingerprint(rows: list[dict]) -> str:
    canonical_rows = [json.dumps(row, sort_keys=True, separators=(",", ":"), ensure_ascii=False) for row in rows]
    digest = hashlib.sha256("\n".join(canonical_rows).encode("utf-8")).hexdigest()
    return f"sha256:{digest}"


def test_fingerprint_match_does_not_compare_result_to_unrelated_dataset(tmp_path):
    train_rows = [{"prompt": "train-only"}]
    eval_rows = [{"prompt": "eval-only"}]
    write_config(
        tmp_path,
        """
artifacts:
  - path: train.jsonl
    roles: [training_dataset]
  - path: eval.jsonl
    roles: [evaluation_dataset]
  - path: result.json
    roles: [evaluation_result]
""".lstrip(),
    )
    (tmp_path / "train.jsonl").write_text("{" + '"prompt":"train-only"' + "}\n", encoding="utf-8")
    (tmp_path / "eval.jsonl").write_text("{" + '"prompt":"eval-only"' + "}\n", encoding="utf-8")
    eval_fp = jsonl_fingerprint(eval_rows)
    (tmp_path / "result.json").write_text(
        json.dumps(
            {
                "model_id": "demo",
                "generation_parameters": {},
                "prompt_version": "p1",
                "dataset_fingerprint": eval_fp,
                "metric_name": "accuracy",
                "metric_threshold": 0.8,
                "timestamp": "2026-01-01T00:00:00Z",
            }
        ),
        encoding="utf-8",
    )

    report = scan_json(tmp_path)

    assert findings_by_rule(report, "contamination.fingerprint_mismatch") == []


def test_fingerprint_mismatch_emits_one_result_centered_finding(tmp_path):
    write_config(
        tmp_path,
        """
artifacts:
  - path: train.jsonl
    roles: [training_dataset]
  - path: eval.jsonl
    roles: [evaluation_dataset]
  - path: result.json
    roles: [evaluation_result]
""".lstrip(),
    )
    (tmp_path / "train.jsonl").write_text('{"prompt":"train-only"}\n', encoding="utf-8")
    (tmp_path / "eval.jsonl").write_text('{"prompt":"eval-only"}\n', encoding="utf-8")
    (tmp_path / "result.json").write_text(
        json.dumps(
            {
                "model_id": "demo",
                "generation_parameters": {},
                "prompt_version": "p1",
                "dataset_fingerprint": "sha256:" + "0" * 64,
                "metric_name": "accuracy",
                "metric_threshold": 0.8,
                "timestamp": "2026-01-01T00:00:00Z",
            }
        ),
        encoding="utf-8",
    )

    report = scan_json(tmp_path)

    findings = findings_by_rule(report, "contamination.fingerprint_mismatch")
    assert len(findings) == 1
    assert findings[0]["locations"] == [{"role": "primary", "path": "result.json"}]
    assert findings[0]["evidence"]["candidate_artifact_paths"] == ["eval.jsonl", "train.jsonl"]


def test_sample_alignment_detects_count_and_id_mismatch_without_positional_fallback(tmp_path):
    eval_rows = [{"id": "a", "prompt": "one"}, {"id": "b", "prompt": "two"}]
    write_config(
        tmp_path,
        """
artifacts:
  - path: eval.jsonl
    roles: [evaluation_dataset]
  - path: result.json
    roles: [evaluation_result]
""".lstrip(),
    )
    (tmp_path / "eval.jsonl").write_text("\n".join(json.dumps(row) for row in eval_rows) + "\n", encoding="utf-8")
    (tmp_path / "result.json").write_text(
        json.dumps(
            {
                "dataset_fingerprint": jsonl_fingerprint(eval_rows),
                "samples": [{"sample_id": "a", "score": 1.0}, {"sample_id": "c", "score": 0.0}],
            }
        ),
        encoding="utf-8",
    )

    report = scan_json(tmp_path)

    findings = findings_by_rule(report, "evaluation.sample_alignment_mismatch")
    assert len(findings) == 1
    finding = findings[0]
    assert finding["severity"] == "high"
    assert finding["confidence"] == "confirmed"
    assert set(finding["evidence"]["mismatch_types"]) == {"missing_ids", "unexpected_ids"}
    assert finding["evidence"]["missing_ids"] == ["sha256:" + hashlib.sha256(b"b").hexdigest()]
    assert finding["evidence"]["unexpected_ids"] == ["sha256:" + hashlib.sha256(b"c").hexdigest()]
    assert finding["evidence"]["dataset_count"] == 2
    assert finding["evidence"]["result_count"] == 2


def test_sample_alignment_ignores_reordered_explicit_ids(tmp_path):
    eval_rows = [{"id": "a", "prompt": "one"}, {"id": "b", "prompt": "two"}]
    write_config(
        tmp_path,
        """
artifacts:
  - path: eval.jsonl
    roles: [evaluation_dataset]
  - path: result.json
    roles: [evaluation_result]
""".lstrip(),
    )
    (tmp_path / "eval.jsonl").write_text("\n".join(json.dumps(row) for row in eval_rows) + "\n", encoding="utf-8")
    (tmp_path / "result.json").write_text(
        json.dumps(
            {
                "dataset_fingerprint": jsonl_fingerprint(eval_rows),
                "samples": [{"id": "b", "score": 0.0}, {"id": "a", "score": 1.0}],
            }
        ),
        encoding="utf-8",
    )

    report = scan_json(tmp_path)

    assert findings_by_rule(report, "evaluation.sample_alignment_mismatch") == []


def test_sample_alignment_detects_trusted_count_mismatch_without_ids(tmp_path):
    eval_rows = [{"prompt": "one"}, {"prompt": "two"}]
    write_config(
        tmp_path,
        """
artifacts:
  - path: eval.jsonl
    roles: [evaluation_dataset]
  - path: result.json
    roles: [evaluation_result]
""".lstrip(),
    )
    (tmp_path / "eval.jsonl").write_text("\n".join(json.dumps(row) for row in eval_rows) + "\n", encoding="utf-8")
    (tmp_path / "result.json").write_text(
        json.dumps({"dataset_fingerprint": jsonl_fingerprint(eval_rows), "samples": [{"score": 1.0}]}),
        encoding="utf-8",
    )

    report = scan_json(tmp_path)

    finding = findings_by_rule(report, "evaluation.sample_alignment_mismatch")[0]
    assert finding["evidence"]["mismatch_types"] == ["count_mismatch"]
    assert finding["evidence"]["dataset_count"] == 2
    assert finding["evidence"]["result_count"] == 1


def test_label_inconsistency_detects_conflicting_targets_and_respects_context(tmp_path):
    write_config(
        tmp_path,
        """
artifacts:
  - path: eval.jsonl
    roles: [evaluation_dataset]
""".lstrip(),
    )
    (tmp_path / "eval.jsonl").write_text(
        "\n".join(
            [
                json.dumps({"prompt": "same", "answer": "first", "context": "A"}),
                json.dumps({"prompt": "same", "answer": "second", "context": "A"}),
                json.dumps({"prompt": "same", "answer": "third", "context": "B"}),
            ]
        )
        + "\n",
        encoding="utf-8",
    )

    report = scan_json(tmp_path)

    findings = findings_by_rule(report, "dataset.label_inconsistency")
    assert len(findings) == 1
    finding = findings[0]
    assert finding["severity"] == "high"
    assert finding["confidence"] == "confirmed"
    assert finding["evidence"]["conflicting_target_count"] == 2
    assert finding["evidence"]["row_locations"] == [
        {"path": "eval.jsonl", "row": 1},
        {"path": "eval.jsonl", "row": 2},
    ]
    assert all("raw" not in key for key in finding["evidence"])


def test_metric_out_of_bounds_requires_explicit_scale_and_known_metric(tmp_path):
    write_config(
        tmp_path,
        """
artifacts:
  - path: result.json
    roles: [evaluation_result]
""".lstrip(),
    )
    (tmp_path / "result.json").write_text(
        json.dumps(
            {
                "metrics": {
                    "accuracy": {"value": 1.2, "bounds": [0, 1]},
                    "accuracy_percent": {"value": 1.5, "unit": "percent"},
                    "ambiguous_accuracy": {"value": 1.2},
                    "custom_score": {"value": 9, "bounds": [0, 1]},
                }
            }
        ),
        encoding="utf-8",
    )

    report = scan_json(tmp_path)

    findings = findings_by_rule(report, "evaluation.metric_out_of_bounds")
    assert len(findings) == 1
    finding = findings[0]
    assert finding["severity"] == "high"
    assert finding["confidence"] == "confirmed"
    assert finding["evidence"]["metric_name"] == "accuracy"
    assert finding["evidence"]["observed_value"] == 1.2
    assert finding["evidence"]["accepted_bounds"] == [0, 1]
def test_sample_alignment_detects_duplicate_ids(tmp_path):
    eval_rows = [{"id": "a", "prompt": "one"}, {"id": "b", "prompt": "two"}]
    write_config(
        tmp_path,
        """
artifacts:
  - path: eval.jsonl
    roles: [evaluation_dataset]
  - path: result.json
    roles: [evaluation_result]
""".lstrip(),
    )
    (tmp_path / "eval.jsonl").write_text("\n".join(json.dumps(row) for row in eval_rows) + "\n", encoding="utf-8")
    (tmp_path / "result.json").write_text(
        json.dumps(
            {
                "dataset_fingerprint": jsonl_fingerprint(eval_rows),
                "samples": [{"id": "a", "score": 1.0}, {"id": "a", "score": 0.0}],
            }
        ),
        encoding="utf-8",
    )

    report = scan_json(tmp_path)

    finding = findings_by_rule(report, "evaluation.sample_alignment_mismatch")[0]
    assert "duplicate_ids" in finding["evidence"]["mismatch_types"]
    assert finding["evidence"]["duplicate_result_ids"] == ["sha256:" + hashlib.sha256(b"a").hexdigest()]


def test_sample_alignment_requires_dataset_fingerprint(tmp_path):
    write_config(
        tmp_path,
        """
artifacts:
  - path: eval.jsonl
    roles: [evaluation_dataset]
  - path: result.json
    roles: [evaluation_result]
""".lstrip(),
    )
    (tmp_path / "eval.jsonl").write_text('{"prompt":"one"}\n{"prompt":"two"}\n', encoding="utf-8")
    (tmp_path / "result.json").write_text(
        json.dumps({"samples": [{"score": 1.0}]}),
        encoding="utf-8",
    )

    report = scan_json(tmp_path)

    assert findings_by_rule(report, "evaluation.sample_alignment_mismatch") == []
def test_trust_chain_findings_are_deterministic(tmp_path):
    eval_rows = [
        {"id": "a", "prompt": "same", "answer": "first"},
        {"id": "b", "prompt": "same", "answer": "second"},
    ]
    write_config(
        tmp_path,
        """
artifacts:
  - path: eval.jsonl
    roles: [evaluation_dataset]
  - path: result.json
    roles: [evaluation_result]
""".lstrip(),
    )
    (tmp_path / "eval.jsonl").write_text("\n".join(json.dumps(row) for row in eval_rows) + "\n", encoding="utf-8")
    (tmp_path / "result.json").write_text(
        json.dumps(
            {
                "dataset_fingerprint": jsonl_fingerprint(eval_rows),
                "samples": [{"id": "a", "score": 1.0}],
                "metrics": {"accuracy": {"value": 1.2, "bounds": [0, 1]}},
            }
        ),
        encoding="utf-8",
    )

    first = scan_json(tmp_path)
    second = scan_json(tmp_path)

    for report in (first, second):
        report["scan"].pop("started_at", None)
        report["scan"].pop("completed_at", None)
    assert first == second



def test_trust_chain_fixture_exercises_result_artifact_contract(tmp_path):
    source = Path(__file__).parent / "fixtures" / "trust_chain_project"
    root = tmp_path / "trust_chain_project"
    shutil.copytree(source, root)

    report = scan_json(root)
    rule_ids = {finding["rule_id"] for finding in report["findings"]}

    assert report["_return_code"] == 1
    assert "evaluation.sample_alignment_mismatch" in rule_ids
    assert "dataset.label_inconsistency" in rule_ids
    assert "evaluation.metric_out_of_bounds" in rule_ids

    alignment = findings_by_rule(report, "evaluation.sample_alignment_mismatch")
    assert len(alignment) == 1
    assert alignment[0]["evidence"]["result_artifact"] == "results/mismatch.json"
    assert set(alignment[0]["evidence"]["mismatch_types"]) == {"count_mismatch", "missing_ids", "unexpected_ids"}

    label = findings_by_rule(report, "dataset.label_inconsistency")
    assert len(label) == 1
    assert label[0]["evidence"]["row_locations"] == [
        {"path": "data/eval.jsonl", "row": 1},
        {"path": "data/eval.jsonl", "row": 2},
    ]

    metric = findings_by_rule(report, "evaluation.metric_out_of_bounds")
    assert len(metric) == 1
    assert metric[0]["evidence"]["result_artifact"] == "results/mismatch.json"
    assert metric[0]["evidence"]["metric_name"] == "accuracy"
