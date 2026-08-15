"""Unit tests for Milestone 3: Rule Engine and All 7 MVP Contamination Rules."""

import json
from pathlib import Path
import tempfile
import pytest

from evalproof.artifact import create_artifact_from_file
from evalproof.config import Config, ArtifactOverride
from evalproof.finding import Severity, Confidence
from evalproof.project_index import ProjectIndex
from evalproof.rule_engine import ScanContext, execute_rules, default_registry
from evalproof.rules import register_mvp_rules


@pytest.fixture(autouse=True)
def ensure_rules_registered():
    register_mvp_rules()


def test_registry_get_enabled_rules():
    cfg = Config(disabled_rules=["contamination.rag_answer_leakage"])
    enabled = default_registry.get_enabled_rules(cfg)
    rule_ids = [r.id for r in enabled]
    assert "contamination.train_eval_overlap" in rule_ids
    assert "contamination.rag_answer_leakage" not in rule_ids


def test_rule_train_eval_overlap():
    with tempfile.TemporaryDirectory() as tmp_dir:
        p = Path(tmp_dir)
        (p / "train.jsonl").write_text('{"q": "what is 2+2", "a": "4"}\n', encoding="utf-8")
        (p / "eval.jsonl").write_text('{"q": "what is 2+2", "a": "4"}\n', encoding="utf-8")

        cfg = Config(
            artifacts=[
                ArtifactOverride(path="train.jsonl", roles=["training_dataset"]),
                ArtifactOverride(path="eval.jsonl", roles=["evaluation_dataset"]),
            ]
        )

        art_train = create_artifact_from_file(tmp_dir, "train.jsonl", cfg)
        art_eval = create_artifact_from_file(tmp_dir, "eval.jsonl", cfg)

        idx = ProjectIndex(cfg)
        idx.build([art_train, art_eval])

        ctx = ScanContext(
            scan_root=tmp_dir,
            config=cfg,
            artifacts={"train.jsonl": art_train, "eval.jsonl": art_eval},
            project_index=idx,
        )

        findings, _ = execute_rules(ctx)
        overlap_findings = [f for f in findings if f.rule_id == "contamination.train_eval_overlap"]
        assert len(overlap_findings) == 1
        assert overlap_findings[0].severity == "critical"
        assert overlap_findings[0].confidence == "confirmed"


def test_rule_duplicate_eval_sample():
    with tempfile.TemporaryDirectory() as tmp_dir:
        p = Path(tmp_dir)
        (p / "eval.jsonl").write_text(
            '{"q": "same"}\n{"q": "different"}\n{"q": "same"}\n', encoding="utf-8"
        )

        cfg = Config(
            artifacts=[ArtifactOverride(path="eval.jsonl", roles=["evaluation_dataset"])]
        )

        art_eval = create_artifact_from_file(tmp_dir, "eval.jsonl", cfg)
        idx = ProjectIndex(cfg)
        idx.build([art_eval])

        ctx = ScanContext(
            scan_root=tmp_dir,
            config=cfg,
            artifacts={"eval.jsonl": art_eval},
            project_index=idx,
        )

        findings, _ = execute_rules(ctx)
        dup_findings = [f for f in findings if f.rule_id == "contamination.duplicate_eval_sample"]
        assert len(dup_findings) == 1
        assert dup_findings[0].evidence["duplicate_count"] == 2
        assert dup_findings[0].evidence["duplicate_row_locations"] == [1, 3]


def test_rule_rag_answer_leakage():
    with tempfile.TemporaryDirectory() as tmp_dir:
        p = Path(tmp_dir)
        (p / "eval.jsonl").write_text(
            '{"question": "who won?", "gold_answer": "The quick brown fox jumps over the lazy dog."}\n',
            encoding="utf-8",
        )
        (p / "corpus.txt").write_text(
            "Here is context: The quick brown fox jumps over the lazy dog. End context.",
            encoding="utf-8",
        )

        cfg = Config(
            artifacts=[
                ArtifactOverride(path="eval.jsonl", roles=["evaluation_dataset"]),
                ArtifactOverride(path="corpus.txt", roles=["rag_document"]),
            ]
        )

        art_eval = create_artifact_from_file(tmp_dir, "eval.jsonl", cfg)
        art_rag = create_artifact_from_file(tmp_dir, "corpus.txt", cfg)

        idx = ProjectIndex(cfg)
        idx.build([art_eval, art_rag])

        ctx = ScanContext(
            scan_root=tmp_dir,
            config=cfg,
            artifacts={"eval.jsonl": art_eval, "corpus.txt": art_rag},
            project_index=idx,
        )

        findings, _ = execute_rules(ctx)
        rag_findings = [f for f in findings if f.rule_id == "contamination.rag_answer_leakage"]
        assert len(rag_findings) == 1
        assert rag_findings[0].severity == "high"


def test_rule_missing_repro_metadata():
    with tempfile.TemporaryDirectory() as tmp_dir:
        p = Path(tmp_dir)
        # Result missing model_id and timestamp
        (p / "result.json").write_text(
            json.dumps({"metric": "accuracy", "params": {}}),
            encoding="utf-8",
        )

        cfg = Config(
            artifacts=[ArtifactOverride(path="result.json", roles=["evaluation_result"])]
        )

        art = create_artifact_from_file(tmp_dir, "result.json", cfg)
        idx = ProjectIndex(cfg)
        idx.build([art])

        ctx = ScanContext(
            scan_root=tmp_dir,
            config=cfg,
            artifacts={"result.json": art},
            project_index=idx,
        )

        findings, _ = execute_rules(ctx)
        meta_findings = [f for f in findings if f.rule_id == "contamination.missing_repro_metadata"]
        assert len(meta_findings) == 1
        assert "model_id" in meta_findings[0].evidence["missing_metadata_fields"]


def test_rule_fingerprint_mismatch():
    with tempfile.TemporaryDirectory() as tmp_dir:
        p = Path(tmp_dir)
        (p / "prompt.md").write_text("System prompt template content.", encoding="utf-8")
        (p / "result.json").write_text(
            json.dumps({
                "model": "gpt-4",
                "prompt_sha256": "0000000000000000000000000000000000000000000000000000000000000000",
            }),
            encoding="utf-8",
        )

        cfg = Config(
            artifacts=[
                ArtifactOverride(path="prompt.md", roles=["prompt_template"]),
                ArtifactOverride(path="result.json", roles=["evaluation_result"]),
            ]
        )

        art_p = create_artifact_from_file(tmp_dir, "prompt.md", cfg)
        art_r = create_artifact_from_file(tmp_dir, "result.json", cfg)

        idx = ProjectIndex(cfg)
        idx.build([art_p, art_r])

        ctx = ScanContext(
            scan_root=tmp_dir,
            config=cfg,
            artifacts={"prompt.md": art_p, "result.json": art_r},
            project_index=idx,
        )

        findings, _ = execute_rules(ctx)
        mismatch_findings = [f for f in findings if f.rule_id == "contamination.fingerprint_mismatch"]
        assert len(mismatch_findings) == 1


def test_rule_untrusted_context_interpolation():
    with tempfile.TemporaryDirectory() as tmp_dir:
        p = Path(tmp_dir)
        (p / "prompt.md").write_text(
            "Answer the question using the provided info:\n{context}\nMake sure to be concise.",
            encoding="utf-8",
        )

        cfg = Config(
            artifacts=[ArtifactOverride(path="prompt.md", roles=["prompt_template"])]
        )

        art = create_artifact_from_file(tmp_dir, "prompt.md", cfg)
        idx = ProjectIndex(cfg)
        idx.build([art])

        ctx = ScanContext(
            scan_root=tmp_dir,
            config=cfg,
            artifacts={"prompt.md": art},
            project_index=idx,
        )

        findings, _ = execute_rules(ctx)
        interp_findings = [f for f in findings if f.rule_id == "contamination.untrusted_context_interpolation"]
        assert len(interp_findings) == 1
        assert interp_findings[0].severity == "medium"


def test_rule_sensitive_value_exposure():
    with tempfile.TemporaryDirectory() as tmp_dir:
        p = Path(tmp_dir)
        (p / "eval.jsonl").write_text(
            '{"user": "test@example.com", "key": "api_key = 1234567890abcdef1234"}\n',
            encoding="utf-8",
        )

        cfg = Config(
            artifacts=[ArtifactOverride(path="eval.jsonl", roles=["evaluation_dataset"])]
        )

        art = create_artifact_from_file(tmp_dir, "eval.jsonl", cfg)
        idx = ProjectIndex(cfg)
        idx.build([art])

        ctx = ScanContext(
            scan_root=tmp_dir,
            config=cfg,
            artifacts={"eval.jsonl": art},
            project_index=idx,
        )

        findings, _ = execute_rules(ctx)
        sens_findings = [f for f in findings if f.rule_id == "contamination.sensitive_value_exposure"]
        assert len(sens_findings) >= 2
        # Verify evidence redaction format <type>:sha256:...
        for f in sens_findings:
            assert all(value.startswith("<") for value in f.evidence["redacted_values"])
            assert all(":sha256:" in value for value in f.evidence["redacted_values"])
