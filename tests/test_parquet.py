"""Generated local Parquet fixtures exercise the optional format contract."""

import hashlib
import json

import pytest
import yaml

pa = pytest.importorskip("pyarrow", minversion="25.0.0")
import pyarrow.parquet as pq

from evalproof.artifact import create_artifact_from_file
from evalproof.cli import main
from evalproof.config import Config
from evalproof.project_index import ProjectIndex, compute_row_hash


def index_file(root, name, config=None):
    config = config or Config()
    config.similarity.enabled = False
    index = ProjectIndex(config)
    art = create_artifact_from_file(str(root), name, config)
    assert art is not None
    index.build([art])
    return index


def scan(root, entries, rules, extra=None):
    config = {"similarity": {"enabled": False}, "artifacts": entries}
    config.update(extra or {})
    (root / "evalproof.yaml").write_text(yaml.safe_dump(config), encoding="utf-8")
    out = root.parent / (root.name + "-parquet-report.json")
    code = main(["scan", str(root), "--rules", rules, "--json", "--output", str(out)])
    assert code in {0, 1}
    return code, json.loads(out.read_text(encoding="utf-8"))


@pytest.mark.parametrize("compression,row_group_size", [(None, 1), ("snappy", 2), ("gzip", 99)])
def test_jsonl_equivalent_rows_and_fingerprints(tmp_path, compression, row_group_size):
    rows = [
        {"id": 1, "prompt": " hello ", "answer": "long private answer", "nested": {"x": [1, 2]}, "flag": True, "value": None},
        {"id": 2, "prompt": "world", "answer": "different private answer", "nested": {"x": []}, "flag": False, "value": None},
    ]
    (tmp_path / "eval.jsonl").write_text("\n".join(json.dumps(r) for r in rows), encoding="utf-8")
    table = pa.Table.from_pylist(rows).replace_schema_metadata({b"private": b"must not interpret"})
    pq.write_table(table, tmp_path / "eval.parquet", compression=compression, row_group_size=row_group_size)
    text = index_file(tmp_path, "eval.jsonl")
    binary = index_file(tmp_path, "eval.parquet")
    assert not binary.diagnostics
    assert binary.artifact_fingerprints["eval.parquet"] == text.artifact_fingerprints["eval.jsonl"]
    assert [r.row_data for r in binary.rows_by_artifact["eval.parquet"]] == rows
    assert [r.row_hash for r in binary.rows_by_artifact["eval.parquet"]] == [compute_row_hash(r) for r in rows]
    assert [r.row_num for r in binary.rows_by_artifact["eval.parquet"]] == [1, 2]
    assert len(binary.answer_records) == 2
    assert not binary.encoding_issues


def test_dictionary_and_fixed_list_types(tmp_path):
    table = pa.table({"prompt": pa.array(["a", "b"]).dictionary_encode(),
                      "values": pa.array([[1, 2], [3, 4]], type=pa.list_(pa.int64(), 2))})
    pq.write_table(table, tmp_path / "train.parquet")
    index = index_file(tmp_path, "train.parquet")
    assert not index.diagnostics
    assert index.rows_by_artifact["train.parquet"][1].row_data == {"prompt": "b", "values": [3, 4]}


@pytest.mark.parametrize("dtype", [pa.binary(), pa.timestamp("ms"), pa.decimal128(8, 2), pa.map_(pa.string(), pa.int64())], ids=["binary", "timestamp", "decimal", "map"])
@pytest.mark.parametrize("role", ["evaluation_dataset", "rag_document"])
def test_unsupported_types_are_not_corruption(tmp_path, dtype, role):
    pq.write_table(pa.table({"content": pa.array([None], type=dtype)}), tmp_path / "corpus.parquet")
    (tmp_path / "eval.jsonl").write_text('{"prompt":"hello"}', encoding="utf-8")
    _, report = scan(tmp_path, [{"path": "corpus.parquet", "roles": [role], **({"schema": {"required": ["content"], "fields": {"content": {"type": "string"}}}} if role == "evaluation_dataset" else {})}],
                     "dataset.schema_contract_violation,rag.empty_or_corrupted_document")
    assert report["findings"] == []
    assert [d["code"] for d in report["diagnostics"]] == ["artifact.unsupported_parquet_schema"]


def test_duplicate_column_names_rejected(tmp_path):
    pq.write_table(pa.Table.from_arrays([pa.array([1]), pa.array([2])], names=["id", "id"]), tmp_path / "eval.parquet")
    index = index_file(tmp_path, "eval.parquet")
    assert [d.code for d in index.diagnostics] == ["artifact.unsupported_parquet_schema"]
    assert not index.artifact_fingerprints


def test_corrupt_file_redacted(tmp_path):
    (tmp_path / "eval.parquet").write_bytes(b"private-corrupt-payload")
    index = index_file(tmp_path, "eval.parquet")
    assert [d.code for d in index.diagnostics] == ["artifact.parse_failed"]
    assert "private-corrupt-payload" not in str(index.diagnostics)
    assert not index.artifact_fingerprints


def test_empty_table_has_empty_fingerprint(tmp_path):
    pq.write_table(pa.table({"prompt": pa.array([], type=pa.string())}), tmp_path / "eval.parquet")
    index = index_file(tmp_path, "eval.parquet")
    assert index.rows_by_artifact["eval.parquet"] == []
    assert index.artifact_fingerprints["eval.parquet"] == "sha256:" + hashlib.sha256(b"").hexdigest()


def test_batch_boundaries_and_row_limit(tmp_path):
    pq.write_table(pa.table({"id": range(65538)}), tmp_path / "eval.parquet", row_group_size=32769)
    index = index_file(tmp_path, "eval.parquet")
    assert len(index.rows_by_artifact["eval.parquet"]) == 65538
    assert index.rows_by_artifact["eval.parquet"][-1].row_num == 65538
    config = Config()
    config.limits.max_rows_per_artifact = 65536
    limited = index_file(tmp_path, "eval.parquet", config)
    assert len(limited.rows_by_artifact["eval.parquet"]) == 65536
    assert [d.code for d in limited.diagnostics] == ["artifact.row_limit_reached"]
    assert limited.get_artifact_coverage([])[0]["index_status"] == "partial"


def test_rag_containment_and_sensitive_values_are_redacted(tmp_path):
    answer = "The undisclosed evaluation gold answer"
    pq.write_table(pa.Table.from_pylist([{"prompt": "Question", "answer": answer}]), tmp_path / "eval.parquet")
    pq.write_table(pa.Table.from_pylist([{"chunk_id": "private-id", "content": answer + " contact private-person@example.com"}]), tmp_path / "corpus.parquet")
    code, report = scan(tmp_path, [], "contamination.rag_answer_leakage,contamination.sensitive_value_exposure,rag.empty_or_corrupted_document")
    assert code == 1
    assert {f["rule_id"] for f in report["findings"]} == {"contamination.rag_answer_leakage", "contamination.sensitive_value_exposure"}
    sensitive = next(f for f in report["findings"] if f["rule_id"].endswith("sensitive_value_exposure"))
    assert sensitive["locations"][0]["row"] == 1
    assert "line" not in sensitive["locations"][0]
    assert sensitive["evidence"]["sample_locations"] == [{"row": 1}]
    raw = json.dumps(report)
    for secret in [answer, "private-id", "private-person@example.com"]:
        assert secret not in raw


def test_rag_does_not_join_records_for_containment(tmp_path):
    pq.write_table(pa.Table.from_pylist([{"prompt": "q", "answer": "first part second part"}]), tmp_path / "eval.parquet")
    pq.write_table(pa.Table.from_pylist([{"content": "first part"}, {"content": "second part"}]), tmp_path / "corpus.parquet")
    assert scan(tmp_path, [], "contamination.rag_answer_leakage")[1]["findings"] == []


def test_text_rag_answer_evidence_also_hashes_raw_answer(tmp_path):
    answer = "This private answer must not appear in a report"
    (tmp_path / "eval.jsonl").write_text(json.dumps({"prompt": "q", "answer": answer}), encoding="utf-8")
    (tmp_path / "corpus.txt").write_text(answer, encoding="utf-8")
    _, report = scan(tmp_path, [], "contamination.rag_answer_leakage")
    assert len(report["findings"]) == 1
    assert answer not in json.dumps(report)
    assert report["findings"][0]["evidence"]["matched_normalized_text"].startswith("sha256:")


def test_reader_failure_keeps_observations_but_not_fingerprint(tmp_path, monkeypatch):
    batch = pa.RecordBatch.from_pylist([{"id": 1, "prompt": "private observed value"}])
    handles = []
    class Reader:
        schema_arrow = batch.schema
        def __init__(self, source, **kwargs):
            assert source.mode == "rb"
            handles.append(source)
            assert kwargs == {"arrow_extensions_enabled": False, "page_checksum_verification": True}
        def __enter__(self):
            return self
        def __exit__(self, *args):
            pass
        def iter_batches(self, **kwargs):
            assert kwargs == {"batch_size": 65536, "use_threads": False}
            yield batch
            raise pa.ArrowInvalid("private failing payload")
    monkeypatch.setattr(pq, "ParquetFile", Reader)
    (tmp_path / "eval.parquet").write_bytes(b"placeholder")
    index = index_file(tmp_path, "eval.parquet")
    assert len(index.rows_by_artifact["eval.parquet"]) == 1
    assert not index.artifact_fingerprints
    assert [d.code for d in index.diagnostics] == ["artifact.parse_failed"]
    assert "private" not in str(index.diagnostics)
    assert index.get_artifact_coverage([])[0]["index_status"] == "skipped"
    assert handles[0].closed


def test_nested_duplicate_fields_rejected(tmp_path):
    nested = pa.StructArray.from_arrays([pa.array([1]), pa.array([2])], names=["id", "id"])
    pq.write_table(pa.table({"nested": nested}), tmp_path / "train.parquet")
    index = index_file(tmp_path, "train.parquet")
    assert [d.code for d in index.diagnostics] == ["artifact.unsupported_parquet_schema"]


def test_limit_equal_to_rows_is_complete(tmp_path):
    pq.write_table(pa.table({"id": [1, 2]}), tmp_path / "eval.parquet")
    config = Config()
    config.limits.max_rows_per_artifact = 2
    index = index_file(tmp_path, "eval.parquet", config)
    assert index.get_artifact_coverage([])[0]["index_status"] == "indexed"
    assert index.diagnostics == []


def test_partial_result_cannot_prove_sample_count_mismatch(tmp_path):
    pq.write_table(pa.table({"id": [1, 2]}), tmp_path / "eval.parquet")
    fingerprint = index_file(tmp_path, "eval.parquet").artifact_fingerprints["eval.parquet"]
    (tmp_path / "result.json").write_text(json.dumps({"dataset_fingerprint": fingerprint,
        "samples": [{"id": 1}, {"id": 3}, {"id": 2}]}), encoding="utf-8")
    # Only two result rows are indexed; this is not proof that the result has two rows.
    _, report = scan(tmp_path, [], "evaluation.sample_alignment_mismatch", {"limits": {"max_rows_per_artifact": 2}})
    assert report["findings"] == []


@pytest.mark.parametrize("rows,expected_state", [([], "empty"), ([{"content": " "}], "empty"), ([{"content": "valid"}], None), ([{"other": "not inferred"}], None)])
def test_empty_rag_contract(tmp_path, rows, expected_state):
    table = pa.Table.from_pylist(rows) if rows else pa.table({"content": pa.array([], type=pa.string())})
    pq.write_table(table, tmp_path / "corpus.parquet")
    (tmp_path / "eval.jsonl").write_text('{"prompt":"q"}', encoding="utf-8")
    _, report = scan(tmp_path, [], "rag.empty_or_corrupted_document")
    if expected_state:
        assert report["findings"][0]["evidence"]["state"] == expected_state
    else:
        assert report["findings"] == []


def test_overlap_labels_schema_and_provenance_keep_record_semantics(tmp_path):
    rows = [{"id": "private-A", "prompt": "private same input", "answer": "private first target"},
            {"id": "private-B", "prompt": "private same input", "answer": "private second target"}]
    table = pa.Table.from_pylist(rows)
    pq.write_table(table, tmp_path / "eval.parquet")
    pq.write_table(table, tmp_path / "train.parquet")
    rules = "contamination.train_eval_overlap,dataset.label_inconsistency,dataset.schema_contract_violation,provenance.manifest_fingerprint_mismatch"
    entry = {"path": "eval.parquet", "roles": ["evaluation_dataset"],
             "schema": {"fields": {"id": {"type": "integer"}}}, "provenance": {"fingerprint": "0" * 64}}
    _, report = scan(tmp_path, [entry], rules)
    assert {f["rule_id"] for f in report["findings"]} == set(rules.split(","))
    assert "private" not in json.dumps(report)


def test_result_alignment_and_metric_rows(tmp_path):
    pq.write_table(pa.table({"id": ["private-a", "private-b"], "prompt": ["one", "two"]}), tmp_path / "eval.parquet")
    fingerprint = index_file(tmp_path, "eval.parquet").artifact_fingerprints["eval.parquet"]
    (tmp_path / "result.json").write_text(json.dumps({"dataset_fingerprint": fingerprint,
        "samples": [{"id": "private-a"}, {"id": "private-other"}]}), encoding="utf-8")
    pq.write_table(pa.Table.from_pylist([{"metrics": {"accuracy": {"value": 2.0, "unit": "fraction"}}}]), tmp_path / "scores.parquet")
    rules = "evaluation.sample_alignment_mismatch,evaluation.metric_out_of_bounds"
    _, report = scan(tmp_path, [], rules)
    assert {f["rule_id"] for f in report["findings"]} == set(rules.split(","))
    assert "private" not in json.dumps(report)


def test_rag_identity_and_duplicate_rules(tmp_path):
    rows = [{"chunk_id": "private-id", "content": "private original content"},
            {"chunk_id": "private-id", "content": "private changed content"},
            {"chunk_id": "private-other", "content": "private original content"}]
    pq.write_table(pa.Table.from_pylist(rows), tmp_path / "corpus.parquet")
    (tmp_path / "eval.jsonl").write_text(json.dumps({"prompt": "q", "context_id": "private-missing"}), encoding="utf-8")
    rules = "rag.chunk_id_collision,rag.duplicate_chunk_in_corpus,rag.unreachable_context_id"
    _, report = scan(tmp_path, [], rules)
    assert {f["rule_id"] for f in report["findings"]} == set(rules.split(","))
    assert "private" not in json.dumps(report)


def test_full_report_determinism_and_compression_independence(tmp_path):
    import os
    import subprocess
    import sys
    rows = [{"id": 1, "prompt": "Find this private answer", "answer": "private target"}] * 2
    table = pa.Table.from_pylist(rows)
    reports = []
    output = tmp_path.parent / (tmp_path.name + "-process-report.json")
    for seed, compression in [("1", None), ("987", "gzip")]:
        pq.write_table(table, tmp_path / "eval.parquet", compression=compression)
        result = subprocess.run([sys.executable, "-c", "from evalproof.cli import main; raise SystemExit(main())",
            "scan", str(tmp_path), "--json", "--output", str(output)],
            env={**os.environ, "PYTHONHASHSEED": seed}, capture_output=True, text=True)
        assert result.returncode in {0, 1}, result.stderr
        report = json.loads(output.read_text(encoding="utf-8"))
        for field in ["started_at", "completed_at"]:
            report["scan"].pop(field)
        reports.append(report)
    assert reports[0] == reports[1]


def test_jsonl_parquet_measurement_equivalence(tmp_path):
    from evalproof.profiling import collect_measurements
    rows = [{"id": "a", "prompt": "  private input  ", "label": "secret-class"}] * 2
    (tmp_path / "train.jsonl").write_text("\n".join(json.dumps(row) for row in rows), encoding="utf-8")
    pq.write_table(pa.Table.from_pylist(rows), tmp_path / "train.parquet", row_group_size=1, compression="gzip")
    results = []
    for name in ("train.jsonl", "train.parquet"):
        measurements = collect_measurements(index_file(tmp_path, name))
        normalized = []
        for item in measurements:
            record = item.to_dict()
            for field in ("artifact_id", "artifact_path", "fingerprint"):
                record.pop(field)
            normalized.append(record)
        results.append(normalized)
    assert len(results[0]) == 7
    assert results[0] == results[1]
