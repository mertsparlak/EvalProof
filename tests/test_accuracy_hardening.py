"""Regression tests for calibrated detector false-positive boundaries."""

import json
from pathlib import Path

from evalproof.artifact import ArtifactOverride, create_artifact_from_file
from evalproof.config import Config, SimilarityConfig
from evalproof.project_index import ProjectIndex
from evalproof.rule_engine import ScanContext, execute_rules


def _scan_findings(tmp_path: Path, filename: str, config: Config):
    artifact = create_artifact_from_file(tmp_path, filename, config)
    index = ProjectIndex(config)
    index.build([artifact])
    context = ScanContext(
        scan_root=tmp_path,
        config=config,
        artifacts={filename: artifact},
        project_index=index,
    )
    findings, _ = execute_rules(context)
    return findings


def test_phone_detector_rejects_arithmetic_shape_and_accepts_formatted_phone(tmp_path):
    (tmp_path / "eval.jsonl").write_text(
        '{"prompt":"A calculation contains 60000-5000 as an expression."}\n'
        '{"prompt":"Call the support line at 555-123-4567."}\n',
        encoding="utf-8",
    )
    config = Config(
        artifacts=[ArtifactOverride(path="eval.jsonl", roles=["evaluation_dataset"])]
    )

    findings = _scan_findings(tmp_path, "eval.jsonl", config)
    phone_findings = [
        finding
        for finding in findings
        if finding.rule_id == "contamination.sensitive_value_exposure"
        and finding.evidence["detector_type"] == "phone"
    ]

    assert len(phone_findings) == 1
    assert phone_findings[0].evidence["exposure_count"] == 1


def test_eval_near_duplicate_ignores_different_explicit_context_and_target(tmp_path):
    (tmp_path / "eval.jsonl").write_text(
        "\n".join(
            [
                json.dumps(
                    {
                        "prompt": "Who was the president of Notre Dame in 1879?",
                        "context": "The 1879 university record names the president for that year.",
                        "answer": "president-1879",
                    }
                ),
                json.dumps(
                    {
                        "prompt": "Who was the president of Notre Dame in 1934?",
                        "context": "The 1934 university record names the president for that year.",
                        "answer": "president-1934",
                    }
                ),
            ]
        )
        + "\n",
        encoding="utf-8",
    )
    config = Config(
        artifacts=[ArtifactOverride(path="eval.jsonl", roles=["evaluation_dataset"])],
        similarity=SimilarityConfig(enabled=True, threshold=0.85),
    )

    findings = _scan_findings(tmp_path, "eval.jsonl", config)

    assert not [
        finding
        for finding in findings
        if finding.rule_id == "contamination.duplicate_eval_near_duplicate"
    ]


def test_eval_near_duplicate_remains_when_explicit_context_and_target_match(tmp_path):
    (tmp_path / "eval.jsonl").write_text(
        "\n".join(
            [
                json.dumps(
                    {
                        "prompt": "Explain the documented evaluation safety procedure.",
                        "context": "The procedure requires a deterministic review.",
                        "answer": "review",
                    }
                ),
                json.dumps(
                    {
                        "prompt": "Explain the documented evaluation safety procedures.",
                        "context": "The procedure requires a deterministic review.",
                        "answer": "review",
                    }
                ),
            ]
        )
        + "\n",
        encoding="utf-8",
    )
    config = Config(
        artifacts=[ArtifactOverride(path="eval.jsonl", roles=["evaluation_dataset"])],
        similarity=SimilarityConfig(enabled=True, threshold=0.85),
    )

    findings = _scan_findings(tmp_path, "eval.jsonl", config)

    assert [
        finding
        for finding in findings
        if finding.rule_id == "contamination.duplicate_eval_near_duplicate"
    ]