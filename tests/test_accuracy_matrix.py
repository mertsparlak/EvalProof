from __future__ import annotations

import json
import shutil
from pathlib import Path

import yaml

import evalproof.rules  # noqa: F401
from evalproof.cli import main
from evalproof.rule_engine import default_registry


FIXTURE_ROOT = Path(__file__).parent / "fixtures"
AUDIT_ROOT = FIXTURE_ROOT / "accuracy_audit"
MANIFEST_PATH = AUDIT_ROOT / "manifest.yaml"

FINDING_KEYS = {
    "rule_id",
    "severity",
    "confidence",
    "title",
    "message",
    "impact",
    "recommendation",
    "locations",
    "evidence",
    "fingerprint",
}


REQUIRED_EVIDENCE_KEYS = {
    "contamination.train_eval_overlap": {"training_artifact", "evaluation_artifact", "normalized_record_hash"},
    "contamination.train_eval_near_duplicate": {"training_artifact", "evaluation_artifact", "similarity_score", "configured_threshold", "matched_training_records", "evidence_truncated"},
    "contamination.duplicate_eval_sample": {"artifact_path", "duplicate_row_locations", "normalized_record_hash"},
    "contamination.duplicate_eval_near_duplicate": {"artifact_paths", "near_duplicate_pair_count", "affected_row_count", "max_similarity_score", "configured_threshold", "sample_pairs", "evidence_truncated"},
    "contamination.duplicate_train_sample": {"artifact_path", "duplicate_row_locations", "normalized_record_hash"},
    "contamination.duplicate_train_near_duplicate": {"artifact_paths", "near_duplicate_pair_count", "affected_row_count", "max_similarity_score", "configured_threshold", "sample_pairs", "evidence_truncated"},
    "contamination.rag_answer_leakage": {"evaluation_artifact", "evaluation_row", "answer_field", "rag_artifact"},
    "contamination.missing_repro_metadata": {"result_artifact", "missing_metadata_fields"},
    "contamination.fingerprint_mismatch": {"result_artifact", "referenced_fingerprint", "candidate_artifact_paths"},
    "evaluation.sample_alignment_mismatch": {"result_artifact", "dataset_artifact", "dataset_count", "result_count", "mismatch_types"},
    "dataset.label_inconsistency": {"artifact_paths", "normalized_input_hash", "input_field", "target_fields"},
    "evaluation.metric_out_of_bounds": {"result_artifact", "metric_name", "observed_value", "accepted_bounds", "field_path"},
    "rag.unreachable_context_id": {"evaluation_artifact", "evaluation_row", "missing_reference_count", "rag_artifact_paths", "searched_id_fields"},
    "contamination.untrusted_context_interpolation": {"prompt_artifact", "variable_name", "line_number"},
    "contamination.sensitive_value_exposure": {"artifact_path", "detector_type", "exposure_count", "distinct_value_count", "sample_locations", "redacted_values", "evidence_truncated"},
    "prompt.unresolved_placeholder": {"artifact_path", "row", "field", "input_hash", "syntax_classes", "detected_count"},
    "dataset.sample_id_collision": {"artifact_path", "sample_id_fields", "sample_id_hash", "row_locations"},
    "dataset.empty_evaluation_input": {"artifact_path", "affected_count", "input_fields", "row_locations", "row_hashes"},
    "dataset.partial_sample_id_coverage": {"artifact_path", "row_count", "identified_count", "missing_id_count", "coverage_ratio", "sample_id_fields", "missing_row_locations", "missing_row_hashes", "evidence_truncated"},
    "rag.empty_referenced_document": {"evaluation_artifact", "evaluation_row", "reference_fields", "empty_reference_count", "empty_reference_hashes", "rag_artifact_paths", "content_fields"},
}
def load_manifest() -> dict:
    return yaml.safe_load(MANIFEST_PATH.read_text(encoding="utf-8"))


def copy_case(tmp_path: Path, manifest: dict, case_name: str) -> Path:
    source = (AUDIT_ROOT / manifest["cases"][case_name]["path"]).resolve()
    target = tmp_path / case_name
    shutil.copytree(source, target, dirs_exist_ok=True)
    return target


def scan_case(tmp_path: Path, manifest: dict, case_name: str, rule_id: str) -> dict:
    root = copy_case(tmp_path, manifest, case_name)
    output = tmp_path / f"{case_name}-{rule_id.replace('.', '_')}.json"
    ret = main(
        [
            "scan",
            str(root),
            "--json",
            "--output",
            str(output),
            "--rules",
            rule_id,
        ]
    )
    assert output.exists()
    report = json.loads(output.read_text(encoding="utf-8"))
    report["_return_code"] = ret
    return report


def test_accuracy_manifest_covers_every_registered_rule():
    manifest = load_manifest()
    registered_ids = {rule.id for rule in default_registry.get_all_rules()}
    manifest_ids = set(manifest["rules"])

    assert manifest_ids == registered_ids
    assert len(manifest_ids) == 20


def test_registered_rules_have_positive_and_negative_cases(tmp_path):
    manifest = load_manifest()

    for rule_id, contract in manifest["rules"].items():
        positive = scan_case(tmp_path / "positive", manifest, contract["positive"], rule_id)
        positive_findings = [
            finding for finding in positive["findings"] if finding["rule_id"] == rule_id
        ]

        assert positive_findings, f"{rule_id} did not emit in positive case"
        for finding in positive_findings:
            assert set(finding) == FINDING_KEYS
            assert finding["confidence"] == contract["confidence"]
            assert finding["evidence"]
            assert REQUIRED_EVIDENCE_KEYS[rule_id] <= set(finding["evidence"])
            assert finding["locations"]
            assert finding["impact"]
            assert finding["recommendation"]
            assert finding["fingerprint"].startswith("sha256:")

        negative = scan_case(tmp_path / "negative", manifest, contract["negative"], rule_id)
        assert [
            finding for finding in negative["findings"] if finding["rule_id"] == rule_id
        ] == [], f"{rule_id} emitted in negative case"
        assert negative["_return_code"] == 0

        if "abstention" in contract:
            abstention = scan_case(
                tmp_path / "abstention",
                manifest,
                contract["abstention"],
                rule_id,
            )
            assert [
                finding
                for finding in abstention["findings"]
                if finding["rule_id"] == rule_id
            ] == [], f"{rule_id} emitted without applicability evidence"
            assert abstention["_return_code"] == 0


def test_accuracy_matrix_preserves_heuristic_ci_behavior(tmp_path):
    manifest = load_manifest()

    for rule_id, contract in manifest["rules"].items():
        if contract["confidence"] != "heuristic":
            continue

        report = scan_case(tmp_path, manifest, contract["positive"], rule_id)
        findings = [finding for finding in report["findings"] if finding["rule_id"] == rule_id]

        assert findings
        assert all(finding["severity"] in {"medium", "low"} for finding in findings)
        assert report["_return_code"] == 0


def test_accuracy_matrix_keeps_sensitive_values_out_of_reports(tmp_path):
    manifest = load_manifest()
    checks = [
        ("contaminated", "contamination.sensitive_value_exposure", "sk-test-1234567890abcdef"),
        ("heuristic", "contamination.sensitive_value_exposure", "support@example.com"),
    ]

    for case_name, rule_id, forbidden_value in checks:
        report = scan_case(tmp_path, manifest, case_name, rule_id)
        assert forbidden_value not in json.dumps(report["findings"])


def test_supported_text_and_structured_formats_index_cleanly(tmp_path):
    manifest = load_manifest()
    root = copy_case(tmp_path, manifest, "formats")
    output = tmp_path / "formats.json"

    ret = main(
        [
            "scan",
            str(root),
            "--json",
            "--output",
            str(output),
            "--rules",
            "dataset.empty_evaluation_input",
        ]
    )

    assert ret == 0
    report = json.loads(output.read_text(encoding="utf-8"))
    assert report["findings"] == []
    assert report["diagnostics"] == []

    by_path = {artifact["path"]: artifact for artifact in report["scan"]["artifacts"]}
    for path in [
        "data.json",
        "data.jsonl",
        "data.csv",
        "data.yaml",
        "data.toml",
        "prompt.md",
        "notes.txt",
    ]:
        assert by_path[path]["index_status"] == "indexed"
        assert by_path[path]["diagnostic_codes"] == []


def test_accuracy_matrix_report_is_deterministic(tmp_path):
    manifest = load_manifest()
    first = scan_case(tmp_path / "first", manifest, "identity_rag", "rag.empty_referenced_document")
    second = scan_case(tmp_path / "second", manifest, "identity_rag", "rag.empty_referenced_document")

    first.pop("_return_code")
    second.pop("_return_code")
    for report in (first, second):
        report["scan"]["started_at"] = "<timestamp>"
        report["scan"]["completed_at"] = "<timestamp>"

    assert first == second
