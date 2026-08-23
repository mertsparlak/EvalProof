"""Unit and integration tests for near-duplicate contamination rules."""

from pathlib import Path
import tempfile
import pytest

from llm_doctor.config import Config, SimilarityConfig
from llm_doctor.artifact import create_artifact_from_file
from llm_doctor.project_index import ProjectIndex
from llm_doctor.rule_engine import ScanContext, execute_rules
from llm_doctor.rules.train_eval_near_duplicate import TrainEvalNearDuplicateRule
from llm_doctor.rules.duplicate_eval_near_duplicate import DuplicateEvalNearDuplicateRule


def test_train_eval_near_duplicate_rule():
    with tempfile.TemporaryDirectory() as tmp_dir:
        p = Path(tmp_dir)

        # 1. Exact duplicate (should NOT be emitted by near-duplicate rule)
        # 2. Near-duplicate above threshold 0.85 (SHOULD be emitted)
        # 3. Completely different (should NOT be emitted)

        train_content = (
            '{"prompt": "Exact match prompt sample text."}\n'
            '{"prompt": "The quick brown fox jumps over the lazy dog and runs away."}\n'
            '{"prompt": "Unrelated training data for testing purposes."}\n'
        )
        eval_content = (
            '{"prompt": "Exact match prompt sample text."}\n'
            '{"prompt": "The quick brown fox jumps over a lazy dog and runs away!"}\n'
            '{"prompt": "Completely different evaluation prompt content."}\n'
        )

        (p / "train.jsonl").write_text(train_content, encoding="utf-8")
        (p / "eval.jsonl").write_text(eval_content, encoding="utf-8")

        cfg = Config(similarity=SimilarityConfig(enabled=True, threshold=0.85))
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

        rule_ids = [f.rule_id for f in findings]
        assert "contamination.train_eval_overlap" in rule_ids
        assert "contamination.train_eval_near_duplicate" in rule_ids

        # Check near duplicate findings
        near_f = [f for f in findings if f.rule_id == "contamination.train_eval_near_duplicate"]
        assert len(near_f) == 1

        f = near_f[0]
        assert f.confidence == "likely"
        assert f.evidence["training_row"] == 2
        assert f.evidence["evaluation_row"] == 2
        assert isinstance(f.evidence["similarity_score"], float)
        assert 0.85 <= f.evidence["similarity_score"] < 1.0


def test_duplicate_eval_near_duplicate_rule():
    with tempfile.TemporaryDirectory() as tmp_dir:
        p = Path(tmp_dir)

        # Near duplicates within eval.jsonl
        eval_content = (
            '{"prompt": "Artificial intelligence model evaluation framework benchmark."}\n'
            '{"prompt": "Artificial intelligence model evaluation framework benchmarks!"}\n'
        )

        (p / "eval.jsonl").write_text(eval_content, encoding="utf-8")

        cfg = Config(similarity=SimilarityConfig(enabled=True, threshold=0.85))
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
        dup_near = [f for f in findings if f.rule_id == "contamination.duplicate_eval_near_duplicate"]
        assert len(dup_near) == 1

        f = dup_near[0]
        assert f.confidence == "likely"
        assert f.evidence["evaluation_row"] == 2
        assert f.evidence["duplicate_row"] == 1
        assert isinstance(f.evidence["similarity_score"], float)


def test_threshold_override_behavior():
    with tempfile.TemporaryDirectory() as tmp_dir:
        p = Path(tmp_dir)

        train_content = '{"prompt": "System prompt security verification test vector."}\n'
        eval_content = '{"prompt": "System prompt security validation test vector."}\n'

        (p / "train.jsonl").write_text(train_content, encoding="utf-8")
        (p / "eval.jsonl").write_text(eval_content, encoding="utf-8")

        # High threshold (0.95) -> 0 findings
        cfg_high = Config(similarity=SimilarityConfig(enabled=True, threshold=0.95))
        art_t = create_artifact_from_file(tmp_dir, "train.jsonl", cfg_high)
        art_e = create_artifact_from_file(tmp_dir, "eval.jsonl", cfg_high)
        idx_high = ProjectIndex(cfg_high)
        idx_high.build([art_t, art_e])
        ctx_high = ScanContext(scan_root=tmp_dir, config=cfg_high, artifacts={"train.jsonl": art_t, "eval.jsonl": art_e}, project_index=idx_high)
        findings_high, _ = execute_rules(ctx_high)
        near_high = [f for f in findings_high if f.rule_id == "contamination.train_eval_near_duplicate"]
        assert len(near_high) == 0

        # Lower threshold (0.70) -> 1 finding
        cfg_low = Config(similarity=SimilarityConfig(enabled=True, threshold=0.70))
        idx_low = ProjectIndex(cfg_low)
        idx_low.build([art_t, art_e])
        ctx_low = ScanContext(scan_root=tmp_dir, config=cfg_low, artifacts={"train.jsonl": art_t, "eval.jsonl": art_e}, project_index=idx_low)
        findings_low, _ = execute_rules(ctx_low)
        near_low = [f for f in findings_low if f.rule_id == "contamination.train_eval_near_duplicate"]
        assert len(near_low) == 1


def test_deterministic_repeated_runs():
    with tempfile.TemporaryDirectory() as tmp_dir:
        p = Path(tmp_dir)
        (p / "train.jsonl").write_text('{"q": "The quick brown fox jumps over the lazy dog."}\n', encoding="utf-8")
        (p / "eval.jsonl").write_text('{"q": "The quick brown fox jumps over a lazy dog."}\n', encoding="utf-8")

        cfg = Config(similarity=SimilarityConfig(enabled=True, threshold=0.80))
        art_t = create_artifact_from_file(tmp_dir, "train.jsonl", cfg)
        art_e = create_artifact_from_file(tmp_dir, "eval.jsonl", cfg)

        idx1 = ProjectIndex(cfg)
        idx1.build([art_t, art_e])
        ctx1 = ScanContext(scan_root=tmp_dir, config=cfg, artifacts={"train.jsonl": art_t, "eval.jsonl": art_e}, project_index=idx1)
        f1, _ = execute_rules(ctx1)

        idx2 = ProjectIndex(cfg)
        idx2.build([art_t, art_e])
        ctx2 = ScanContext(scan_root=tmp_dir, config=cfg, artifacts={"train.jsonl": art_t, "eval.jsonl": art_e}, project_index=idx2)
        f2, _ = execute_rules(ctx2)

        assert len(f1) == len(f2)
        for item1, item2 in zip(f1, f2):
            assert item1.fingerprint == item2.fingerprint
            assert item1.evidence == item2.evidence


def test_duplicate_train_sample_and_near_duplicate_rules():
    with tempfile.TemporaryDirectory() as tmp_dir:
        p = Path(tmp_dir)

        # Internal duplicates in train.jsonl
        train_content = (
            '{"prompt": "Exact training duplicate entry."}\n'
            '{"prompt": "Exact training duplicate entry."}\n'
            '{"prompt": "Machine learning model optimization techniques."}\n'
            '{"prompt": "Machine learning model optimization technique!"}\n'
        )

        (p / "train.jsonl").write_text(train_content, encoding="utf-8")

        cfg = Config(similarity=SimilarityConfig(enabled=True, threshold=0.85))
        art_train = create_artifact_from_file(tmp_dir, "train.jsonl", cfg)

        idx = ProjectIndex(cfg)
        idx.build([art_train])

        ctx = ScanContext(
            scan_root=tmp_dir,
            config=cfg,
            artifacts={"train.jsonl": art_train},
            project_index=idx,
        )

        findings, _ = execute_rules(ctx)

        exact_train_dup = [f for f in findings if f.rule_id == "contamination.duplicate_train_sample"]
        near_train_dup = [f for f in findings if f.rule_id == "contamination.duplicate_train_near_duplicate"]

        assert len(exact_train_dup) == 1
        assert exact_train_dup[0].evidence["duplicate_count"] == 2

        assert len(near_train_dup) == 1
        assert near_train_dup[0].evidence["training_row"] == 4
        assert near_train_dup[0].evidence["duplicate_row"] == 3

