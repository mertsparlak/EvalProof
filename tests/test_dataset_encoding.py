import hashlib
import json

import pytest
import yaml

import evalproof.cli as cli
from evalproof.artifact import create_artifact_from_file
from evalproof.config import parse_and_validate_config_dict
from evalproof.project_index import ProjectIndex

RULE = "dataset.invalid_text_encoding"


def scan(root, raw, suffix="jsonl", role="training_dataset", rules=RULE, limits=None):
    name = "data." + suffix
    config = {"artifacts": [{"path": name, "roles": [role]}], "similarity": {"enabled": False}}
    if limits:
        config["limits"] = limits
    (root / "evalproof.yaml").write_text(yaml.safe_dump(config), encoding="utf-8")
    (root / name).write_bytes(raw)
    output = root.parent / (root.name + "-encoding-report.json")
    code = cli.main(["scan", str(root), "--rules", rules, "--json", "--output", str(output)])
    assert code in {0, 1}
    return code, json.loads(output.read_text(encoding="utf-8"))


@pytest.mark.parametrize("raw,offset,length", [
    (b'{"prompt":"secret-\xff"}\n', 18, 1),
    (b'\xef\xbb\xbf\xe2\x82', 3, 2),
    (b'\xc0\xaf', 0, 1),
    (b'\xed\xa0\x80', 0, 1),
])
def test_invalid_utf8_is_redacted_and_never_indexed(tmp_path, raw, offset, length):
    code, report = scan(tmp_path, raw)
    assert code == 0
    assert len(report["findings"]) == 1
    finding = report["findings"][0]
    assert (finding["severity"], finding["confidence"]) == ("medium", "confirmed")
    evidence = finding["evidence"]
    assert evidence["invalid_utf8_range"] == {"offset": offset, "length": length}
    assert evidence["byte_hash"] == "sha256:" + hashlib.sha256(raw).hexdigest()
    assert evidence["byte_count"] == len(raw)
    assert evidence["nul_byte_count"] == 0
    assert "secret-" not in json.dumps(report)
    coverage = next(a for a in report["scan"]["artifacts"] if a["path"] == "data.jsonl")
    assert coverage["index_status"] == "skipped"
    assert "invalid_text_encoding" in coverage["index_reasons"]
    assert coverage["fingerprint"] is None
    assert any(d["code"] == "artifact.invalid_text_encoding" for d in report["diagnostics"])


def test_actual_nul_is_not_mislabelled_as_invalid_utf8(tmp_path):
    _, report = scan(tmp_path, b"prompt\nhello\x00world\n", suffix="csv")
    finding = report["findings"][0]
    assert finding["evidence"]["invalid_utf8_range"] is None
    assert finding["evidence"]["nul_byte_count"] == 1
    assert finding["evidence"]["sample_nul_offsets"] == [12]
    assert "NUL" in finding["message"]


def test_bounded_nul_offsets_preserve_full_count(tmp_path):
    _, report = scan(tmp_path, b"a" + b"\x00" * 50 + b"\xff")
    evidence = report["findings"][0]["evidence"]
    assert evidence["nul_byte_count"] == 50
    assert evidence["sample_nul_offsets"] == list(range(1, 21))
    assert evidence["nul_offsets_truncated"] is True
    assert evidence["invalid_utf8_range"] == {"offset": 51, "length": 1}


@pytest.mark.parametrize("raw", [b'{"prompt":"escaped \\u0000"}\n', '{"prompt":"T\u00fcrk\u00e7e \u4e2d\u6587 \ufffd"}\n'.encode("utf-8"), b""])
def test_valid_text_is_not_an_encoding_finding(tmp_path, raw):
    assert scan(tmp_path, raw)[1]["findings"] == []


@pytest.mark.parametrize("suffix,raw", [
    ("jsonl", b'{"prompt":"hello"}\n'), ("json", b'[{"prompt":"hello"}]'),
    ("csv", b'prompt\nhello\n'), ("yaml", b'- prompt: hello\n'),
    ("toml", b'[[rows]]\nprompt="hello"\n'), ("txt", b'hello\n'),
])
def test_utf8_bom_is_accepted_and_semantic_fingerprint_is_unchanged(tmp_path, suffix, raw):
    first = scan(tmp_path, raw, suffix=suffix)[1]
    second = scan(tmp_path, b"\xef\xbb\xbf" + raw, suffix=suffix)[1]
    for report in [first, second]:
        assert report["findings"] == []
        assert not any(d["code"] in {"artifact.invalid_text_encoding", "artifact.parse_failed", "artifact.row_parse_failed"} for d in report["diagnostics"])
    entries = [next(a for a in report["scan"]["artifacts"] if a["path"] == "data." + suffix) for report in [first, second]]
    assert entries[0]["fingerprint"] == entries[1]["fingerprint"]
    assert entries[1]["index_status"] == "indexed"


@pytest.mark.parametrize("role", ["training_dataset", "evaluation_dataset", "benchmark_dataset"])
def test_dataset_roles_are_audited(tmp_path, role):
    assert len(scan(tmp_path, b"\xff", role=role)[1]["findings"]) == 1


@pytest.mark.parametrize("role", ["rag_document", "evaluation_result", "prompt_template", "configuration"])
def test_unrelated_roles_do_not_get_dataset_encoding_findings(tmp_path, role):
    assert scan(tmp_path, b"\xff", role=role)[1]["findings"] == []


def test_file_limit_precedes_byte_audit(tmp_path):
    _, report = scan(tmp_path, b"\xff" * (1024 * 1024 + 1), limits={"max_file_mb": 1})
    assert report["findings"] == []
    assert not any(d["code"] == "artifact.invalid_text_encoding" for d in report["diagnostics"])


def test_encoding_diagnostic_exists_even_when_rule_not_selected(tmp_path):
    _, report = scan(tmp_path, b'{"prompt":"bad-\xff"}\n', rules="contamination.duplicate_train_sample")
    assert report["findings"] == []
    assert any(d["code"] == "artifact.invalid_text_encoding" for d in report["diagnostics"])


def test_invalid_tail_is_audited_past_row_limit(tmp_path):
    _, report = scan(tmp_path, b'{"prompt":"valid"}\n' * 3 + b'\xff', limits={"max_rows_per_artifact": 1})
    assert len(report["findings"]) == 1


def test_encoding_findings_are_deterministic(tmp_path, monkeypatch):
    raw = b"private content\x00\xff"
    first = scan(tmp_path, raw)[1]
    original = cli.discover_files
    monkeypatch.setattr(cli, "discover_files", lambda *a, **kw: list(reversed(original(*a, **kw))))
    second = scan(tmp_path, raw)[1]
    for report in [first, second]:
        report["scan"].pop("started_at")
        report["scan"].pop("completed_at")
    assert first == second


def test_index_exposes_facts_without_replacement_rows(tmp_path):
    (tmp_path / "train.jsonl").write_bytes(b'{"prompt":"\xff"}\n')
    config = parse_and_validate_config_dict({"similarity": {"enabled": False}})
    index = ProjectIndex(config)
    index.build([create_artifact_from_file(str(tmp_path), "train.jsonl", config)])
    assert "train.jsonl" in index.encoding_issues
    assert "train.jsonl" not in index.rows_by_artifact
    assert "train.jsonl" not in index.artifact_fingerprints
