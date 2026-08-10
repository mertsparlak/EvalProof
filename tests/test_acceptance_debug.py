"""Temporary acceptance test for debugging contamination finding emission and role detection."""

import json
from pathlib import Path
import tempfile
import pytest

from evalproof.cli import main
from evalproof.artifact import detect_heuristic_roles, create_artifact_from_file
from evalproof.config import Config, load_config
from evalproof.discovery import discover_files
from evalproof.project_index import ProjectIndex
from evalproof.rule_engine import ScanContext, execute_rules, default_registry
from evalproof.rules import register_mvp_rules


def test_acceptance_train_eval_overlap_emitted():
    """Acceptance Test 1: Two tiny JSONL files (train.jsonl and eval.jsonl) with identical sample."""
    with tempfile.TemporaryDirectory() as tmp_dir:
        p = Path(tmp_dir)
        sample = '{"prompt": "What is the capital of France?", "answer": "Paris"}\n'
        (p / "train.jsonl").write_text(sample, encoding="utf-8")
        (p / "eval.jsonl").write_text(sample, encoding="utf-8")

        # Execute scan via CLI
        out_json_path = p / "report.json"
        ret = main(["scan", tmp_dir, "--json", "--output", str(out_json_path)])

        assert out_json_path.exists()
        report = json.loads(out_json_path.read_text(encoding="utf-8"))

        # Verify contamination.train_eval_overlap is emitted
        findings = report["findings"]
        rule_ids = [f["rule_id"] for f in findings]
        assert "contamination.train_eval_overlap" in rule_ids
        assert ret == 1  # Exit code 1 for critical finding


def test_acceptance_duplicate_eval_sample_emitted():
    """Acceptance Test 2: Tiny evaluation JSONL file with duplicate samples."""
    with tempfile.TemporaryDirectory() as tmp_dir:
        p = Path(tmp_dir)
        content = (
            '{"prompt": "What is the capital of France?", "answer": "Paris"}\n'
            '{"prompt": "What is the capital of France?", "answer": "Paris"}\n'
        )
        (p / "test.jsonl").write_text(content, encoding="utf-8")

        out_json_path = p / "report.json"
        ret = main(["scan", tmp_dir, "--json", "--output", str(out_json_path)])

        assert out_json_path.exists()
        report = json.loads(out_json_path.read_text(encoding="utf-8"))

        findings = report["findings"]
        rule_ids = [f["rule_id"] for f in findings]
        assert "contamination.duplicate_eval_sample" in rule_ids
        assert ret == 1  # Exit code 1 for high finding


def test_role_detection_validation_jsonl():
    """Question 4 Check: Role detection for train.jsonl, validation.jsonl, and test.jsonl."""
    train_roles = detect_heuristic_roles("train.jsonl", "jsonl")
    test_roles = detect_heuristic_roles("test.jsonl", "jsonl")
    val_roles = detect_heuristic_roles("validation.jsonl", "jsonl")

    assert "training_dataset" in train_roles
    assert "evaluation_dataset" in test_roles
    # Check if validation.jsonl is classified as evaluation_dataset or unknown
    print(f"DEBUG: validation.jsonl roles => {val_roles}")
