"""Optional reader guarantees which also run in the base installation."""

import builtins
import json
import sys
from types import SimpleNamespace

import pytest
import yaml

from evalproof.artifact import create_artifact_from_file
from evalproof.cli import main
from evalproof.config import Config
from evalproof.project_index import ProjectIndex


@pytest.mark.parametrize("name,role", [
    ("train.parquet", "training_dataset"), ("eval.parquet", "evaluation_dataset"),
    ("benchmark.parquet", "benchmark_dataset"), ("results.parquet", "evaluation_result"),
    ("corpus.parquet", "rag_document"),
])
def test_parquet_discovery(name, role, tmp_path):
    art = create_artifact_from_file(str(tmp_path), name, Config())
    assert art is not None and art.format == "parquet"
    assert role in art.roles


@pytest.mark.parametrize("module", [None, SimpleNamespace(__version__="23.0.1")], ids=["absent", "incompatible"])
@pytest.mark.parametrize("role", ["evaluation_dataset", "rag_document"])
def test_missing_extra_is_diagnostic_not_corruption(tmp_path, monkeypatch, module, role):
    monkeypatch.setitem(sys.modules, "pyarrow", module)
    (tmp_path / "corpus.parquet").write_bytes(b"binary-not-text")
    (tmp_path / "eval.jsonl").write_text('{"prompt":"hello"}\n', encoding="utf-8")
    (tmp_path / "evalproof.yaml").write_text(yaml.safe_dump({
        "similarity": {"enabled": False},
        "artifacts": [{"path": "corpus.parquet", "roles": [role],
                       **({"schema": {"required": ["prompt"], "fields": {"prompt": {"type": "string"}}}} if role == "evaluation_dataset" else {})}],
    }), encoding="utf-8")
    out = tmp_path.parent / (tmp_path.name + "-report.json")
    code = main(["scan", str(tmp_path), "--rules", "dataset.schema_contract_violation,rag.empty_or_corrupted_document,dataset.invalid_text_encoding",
                 "--json", "--output", str(out)])
    assert code == 0
    report = json.loads(out.read_text(encoding="utf-8"))
    assert report["findings"] == []
    assert [d["code"] for d in report["diagnostics"]] == ["artifact.optional_dependency_missing"]
    coverage = next(a for a in report["scan"]["artifacts"] if a["path"] == "corpus.parquet")
    assert coverage["index_status"] == "skipped"
    assert coverage["index_reasons"] == ["optional_dependency_missing"]


def test_text_scans_never_import_arrow(tmp_path, monkeypatch):
    original = builtins.__import__
    def guarded(name, *args, **kwargs):
        assert not name.startswith("pyarrow")
        return original(name, *args, **kwargs)
    monkeypatch.setattr(builtins, "__import__", guarded)
    (tmp_path / "eval.jsonl").write_text('{"prompt":"hello"}\n', encoding="utf-8")
    index = ProjectIndex(Config())
    index.build([create_artifact_from_file(str(tmp_path), "eval.jsonl", Config())])
    assert len(index.rows_by_artifact["eval.jsonl"]) == 1


def test_binary_text_access_is_empty_and_size_gate_precedes_reader(tmp_path, monkeypatch):
    path = tmp_path / "eval.parquet"
    path.write_bytes(b"x" * (1024 * 1024 + 1))
    art = create_artifact_from_file(str(tmp_path), path.name, Config())
    assert art is not None
    assert art.read_text() == ""
    monkeypatch.setitem(sys.modules, "pyarrow", None)
    config = Config()
    config.limits.max_file_mb = 1
    index = ProjectIndex(config)
    index.build([art])
    assert [d.code for d in index.diagnostics] == ["artifact.file_size_limit_exceeded"]


def test_missing_reader_cannot_prove_reference_absence(tmp_path, monkeypatch):
    monkeypatch.setitem(sys.modules, "pyarrow", None)
    (tmp_path / "corpus.jsonl").write_text('{"id":"observed","content":"known"}', encoding="utf-8")
    (tmp_path / "corpus.parquet").write_bytes(b"unavailable")
    (tmp_path / "eval.parquet").write_bytes(b"unavailable")
    (tmp_path / "eval.jsonl").write_text('{"prompt":"q","context_id":"unobserved"}', encoding="utf-8")
    (tmp_path / "result.json").write_text(json.dumps({"dataset_fingerprint": "sha256:" + "0" * 64}), encoding="utf-8")
    out = tmp_path.parent / (tmp_path.name + "-report.json")
    assert main(["scan", str(tmp_path), "--rules", "rag.unreachable_context_id,contamination.fingerprint_mismatch",
                 "--json", "--output", str(out)]) == 0
    report = json.loads(out.read_text(encoding="utf-8"))
    assert report["findings"] == []
    assert len(report["diagnostics"]) == 2
