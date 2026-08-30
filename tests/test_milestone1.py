"""Unit tests for Milestone 1: Core Models, Configuration, and Discovery."""

import json
import os
from pathlib import Path
import tempfile
import pytest

from evalproof.finding import (
    Finding,
    Location,
    Diagnostic,
    DiagnosticSeverity,
    DiagnosticCode,
    Severity,
    Confidence,
    canonical_json_dumps,
)
from evalproof.config import (
    Config,
    ConfigError,
    load_config,
    parse_and_validate_config_dict,
    DEFAULT_INCLUDES,
    DEFAULT_EXCLUDES,
    DEFAULT_FAIL_ON,
)
from evalproof.discovery import discover_files, glob_to_regex, is_pattern_matched


def test_canonical_json_dumps():
    data = {"b": 2, "a": 1, "c": [3, 1, 2], "d": True, "e": None}
    serialized = canonical_json_dumps(data)
    assert serialized == '{"a":1,"b":2,"c":[3,1,2],"d":true,"e":null}'


def test_finding_fingerprint_determinism():
    loc1 = Location(role="source", path="data/train.jsonl", row=12)
    loc2 = Location(role="target", path="data/eval.jsonl", row=4)

    finding1 = Finding(
        rule_id="contamination.train_eval_overlap",
        severity=Severity.CRITICAL.value,
        confidence=Confidence.CONFIRMED.value,
        title="Train/eval overlap detected",
        message="A record appears in both training and evaluation datasets.",
        impact="Evaluation results may be inflated.",
        recommendation="Remove overlapping records.",
        locations=[loc1, loc2],
        evidence={"normalized_record_hash": "sha256:1234567890abcdef"},
    )

    finding2 = Finding(
        rule_id="contamination.train_eval_overlap",
        severity=Severity.CRITICAL.value,
        confidence=Confidence.CONFIRMED.value,
        title="Train/eval overlap detected",
        message="A record appears in both training and evaluation datasets.",
        impact="Evaluation results may be inflated.",
        recommendation="Remove overlapping records.",
        locations=[loc1, loc2],
        evidence={"normalized_record_hash": "sha256:1234567890abcdef"},
    )

    assert finding1.fingerprint.startswith("sha256:")
    assert finding1.fingerprint == finding2.fingerprint


def test_diagnostic_model():
    diag = Diagnostic(
        severity=DiagnosticSeverity.WARNING.value,
        code=DiagnosticCode.ARTIFACT_PARSE_FAILED.value,
        message="Failed to parse JSONL.",
        path="data/eval.jsonl",
        row=5,
    )
    d_dict = diag.to_dict()
    assert d_dict["severity"] == "warning"
    assert d_dict["code"] == "artifact.parse_failed"
    assert d_dict["path"] == "data/eval.jsonl"
    assert d_dict["row"] == 5


def test_config_defaults():
    cfg = Config()
    assert cfg.include == DEFAULT_INCLUDES
    assert cfg.exclude == DEFAULT_EXCLUDES
    assert cfg.fail_on == DEFAULT_FAIL_ON
    assert cfg.limits.max_file_mb == 100
    assert cfg.limits.max_rows_per_artifact == 250000


def test_config_parsing_valid():
    yaml_data = {
        "include": ["data/**"],
        "exclude": [".git/**"],
        "artifacts": [
            {"path": "data/train.jsonl", "roles": ["training_dataset"]},
        ],
        "rules": {
            "disabled": ["contamination.rag_answer_leakage"],
            "severity": {"contamination.train_eval_overlap": "critical"},
        },
        "ci": {"fail_on": "critical"},
        "limits": {"max_file_mb": 100, "max_rows_per_artifact": 500000},
    }
    cfg = parse_and_validate_config_dict(yaml_data)
    assert cfg.include == ["data/**"]
    assert cfg.artifacts[0].path == "data/train.jsonl"
    assert cfg.artifacts[0].roles == ["training_dataset"]
    assert cfg.disabled_rules == ["contamination.rag_answer_leakage"]
    assert cfg.rule_severities["contamination.train_eval_overlap"] == "critical"
    assert cfg.fail_on == "critical"
    assert cfg.limits.max_file_mb == 100
    assert cfg.limits.max_rows_per_artifact == 500000


def test_config_invalid_top_level_key():
    with pytest.raises(ConfigError, match="Invalid top-level key"):
        parse_and_validate_config_dict({"unknown_key": 123})


def test_config_invalid_role():
    with pytest.raises(ConfigError, match="Invalid artifact role"):
        parse_and_validate_config_dict({
            "artifacts": [{"path": "a.json", "roles": ["invalid_role"]}]
        })


def test_config_invalid_severity():
    with pytest.raises(ConfigError, match="Invalid severity"):
        parse_and_validate_config_dict({
            "rules": {"severity": {"rule.id": "super_critical"}}
        })


def test_discovery_file_matching():
    assert is_pattern_matched("data/train.jsonl", ["data/*"])
    assert is_pattern_matched(".git/HEAD", [".git/**"])
    assert not is_pattern_matched("src/main.py", ["data/*"])


def test_discovery_include_exclude_precedence():
    with tempfile.TemporaryDirectory() as tmp_dir:
        tmp_path = Path(tmp_dir)
        # Create test directory structure
        (tmp_path / "data").mkdir()
        (tmp_path / ".git").mkdir()
        (tmp_path / "data" / "train.jsonl").write_text("{}\n", encoding="utf-8")
        (tmp_path / "data" / "eval.jsonl").write_text("{}\n", encoding="utf-8")
        (tmp_path / ".git" / "config").write_text("[core]\n", encoding="utf-8")
        (tmp_path / "node_modules").mkdir()
        (tmp_path / "node_modules" / "foo.js").write_text("", encoding="utf-8")

        cfg = Config(
            include=["**/*"],
            exclude=[".git/**", "node_modules/**"],
        )

        discovered = discover_files(str(tmp_path), cfg)
        assert discovered == ["data/eval.jsonl", "data/train.jsonl"]
