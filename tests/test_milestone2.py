"""Unit tests for Milestone 2: Artifact Model and Project Index."""

import json
from pathlib import Path
import tempfile
import pytest

from evalproof.artifact import (
    Artifact,
    compute_artifact_id,
    detect_file_format,
    detect_heuristic_roles,
    create_artifact_from_file,
)
from evalproof.config import Config, ArtifactOverride
from evalproof.finding import DiagnosticCode, DiagnosticSeverity
from evalproof.project_index import (
    ProjectIndex,
    normalize_plain_text,
    compute_row_hash,
    is_trivial_answer,
)


def test_compute_artifact_id():
    id1 = compute_artifact_id("data/train.jsonl")
    id2 = compute_artifact_id("./data/train.jsonl")
    assert id1.startswith("sha256:")
    assert id1 == id2


def test_detect_heuristic_roles():
    roles1 = detect_heuristic_roles("eval/results/baseline.json", "json")
    assert "evaluation_dataset" in roles1
    assert "evaluation_result" in roles1

    roles2 = detect_heuristic_roles("prompts/system_template.md", "markdown")
    assert "prompt_template" in roles2

    roles3 = detect_heuristic_roles("docs/knowledge.txt", "plain_text")
    assert "rag_document" in roles3


def test_create_artifact_with_config_override():
    cfg = Config(
        artifacts=[ArtifactOverride(path="custom/data.bin", roles=["training_dataset"])]
    )
    # Unsupported extension 'custom/data.bin' but configured -> plain_text with diagnostic
    art = create_artifact_from_file(".", "custom/data.bin", cfg)
    assert art is not None
    assert art.format == "plain_text"
    assert "training_dataset" in art.roles
    assert any(d.code == DiagnosticCode.ARTIFACT_UNSUPPORTED_EXTENSION.value for d in art.diagnostics)


def test_plain_text_normalization():
    raw = "  Hello \r\n world \t\t with   extra   spaces.  "
    norm = normalize_plain_text(raw)
    assert norm == "Hello world with extra spaces."


def test_trivial_answer_filtering():
    assert is_trivial_answer("yes")
    assert is_trivial_answer("True")
    assert is_trivial_answer("A")
    assert is_trivial_answer("7")
    assert not is_trivial_answer("The quick brown fox jumps over the lazy dog.")


def test_project_index_jsonl_indexing():
    with tempfile.TemporaryDirectory() as tmp_dir:
        p = Path(tmp_dir) / "train.jsonl"
        p.write_text(
            '{"prompt": "hi", "answer": "Hello world this is a test answer that is long enough."}\n'
            'invalid json line\n'
            '{"prompt": "bye", "answer": "Goodbye world this is another long answer."}\n',
            encoding="utf-8",
        )

        cfg = Config()
        art = create_artifact_from_file(tmp_dir, "train.jsonl", cfg)
        assert art is not None

        index = ProjectIndex(cfg)
        index.build([art])

        assert "train.jsonl" in index.rows_by_artifact
        assert len(index.rows_by_artifact["train.jsonl"]) == 2
        # Diagnostic emitted for malformed line
        assert any(d.code == DiagnosticCode.ARTIFACT_ROW_PARSE_FAILED.value for d in index.diagnostics)
        assert "train.jsonl" in index.artifact_fingerprints
        assert index.artifact_fingerprints["train.jsonl"].startswith("sha256:")


def test_project_index_csv_indexing():
    with tempfile.TemporaryDirectory() as tmp_dir:
        p = Path(tmp_dir) / "eval.csv"
        p.write_text(
            "prompt, expected_answer\n"
            "What is 2+2?, Four is the correct mathematical answer.\n"
            "Bad row without enough fields\n"
            "What is 3+3?, Six is the correct mathematical answer.\n",
            encoding="utf-8",
        )

        cfg = Config()
        art = create_artifact_from_file(tmp_dir, "eval.csv", cfg)
        index = ProjectIndex(cfg)
        index.build([art])

        assert len(index.rows_by_artifact["eval.csv"]) == 2
        assert any(d.code == DiagnosticCode.ARTIFACT_ROW_PARSE_FAILED.value for d in index.diagnostics)


def test_project_index_json_object_rows_and_metadata():
    with tempfile.TemporaryDirectory() as tmp_dir:
        p = Path(tmp_dir) / "result.json"
        p.write_text(
            json.dumps({
                "model": "gpt-4o",
                "parameters": {"temperature": 0.7},
                "prompt_sha256": "abc123def456",
                "dataset_sha256": "789ghi012jkl",
                "metric_name": "accuracy",
                "pass_threshold": 0.85,
                "timestamp": "2026-01-01T00:00:00Z",
                "records": [
                    {"question": "Q1", "gold": "Gold answer long enough to extract."},
                ]
            }),
            encoding="utf-8",
        )

        cfg = Config(
            artifacts=[ArtifactOverride(path="result.json", roles=["evaluation_result"])]
        )
        art = create_artifact_from_file(tmp_dir, "result.json", cfg)
        index = ProjectIndex(cfg)
        index.build([art])

        assert "result.json" in index.eval_metadata
        meta = index.eval_metadata["result.json"]
        assert meta["model_id"] == "gpt-4o"
        assert meta["metric_name"] == "accuracy"
        assert meta["prompt_fingerprint"] == "abc123def456"

        assert len(index.answer_records) == 1
        assert index.answer_records[0].field_name == "gold"
