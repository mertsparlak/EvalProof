import hashlib
import json
from pathlib import Path

import pytest
import yaml

import evalproof.cli as cli
from evalproof.config import ConfigError, parse_and_validate_config_dict

MISSING = "provenance.required_metadata_missing"
MISMATCH = "provenance.manifest_fingerprint_mismatch"
SOURCE = "provenance.local_source_unresolved"
RULES = ",".join([MISSING, MISMATCH, SOURCE])
DATA = b'{"prompt":"hello"}\n'
FINGERPRINT = "sha256:" + hashlib.sha256(DATA.rstrip(b"\n")).hexdigest()


def run(root, provenance=None, raw=DATA, rules=RULES, extra=None):
    entry = {"path": "train.jsonl", "roles": ["training_dataset"]}
    if provenance is not None:
        entry["provenance"] = provenance
    config = {"artifacts": [entry], "similarity": {"enabled": False}}
    config.update(extra or {})
    (root / "train.jsonl").write_bytes(raw)
    (root / "evalproof.yaml").write_text(yaml.safe_dump(config), encoding="utf-8")
    output = root.parent / (root.name + "-provenance-report.json")
    code = cli.main(["scan", str(root), "--rules", rules, "--json", "--output", str(output)])
    return code, json.loads(output.read_text(encoding="utf-8")) if code in {0, 1} else None


def test_no_contract_or_empty_contract_abstains(tmp_path):
    for contract in [None, {}]:
        code, report = run(tmp_path, contract)
        assert code == 0
        assert report["findings"] == []


def test_only_explicitly_required_metadata_is_missing(tmp_path):
    contract = {"required": ["source.ref", "version", "generator.name", "license"], "version": "  ", "generator": {"name": None}, "license": "private-license"}
    code, report = run(tmp_path, contract)
    assert code == 0
    assert len(report["findings"]) == 1
    f = report["findings"][0]
    assert f["rule_id"] == MISSING
    assert (f["severity"], f["confidence"]) == ("medium", "confirmed")
    assert f["evidence"]["missing_fields"] == ["generator.name", "source.ref", "version"]
    assert f["evidence"]["missing_count"] == 3
    assert "private-license" not in json.dumps(report)


def test_matching_and_mismatching_semantic_fingerprint(tmp_path):
    code, report = run(tmp_path, {"fingerprint": FINGERPRINT.upper()})
    assert code == 0
    assert report["findings"] == []
    code, report = run(tmp_path, {"fingerprint": "0" * 64})
    assert code == 1
    f = report["findings"][0]
    assert f["rule_id"] == MISMATCH
    assert f["evidence"]["observed_fingerprint"] == FINGERPRINT
    assert f["evidence"]["declared_fingerprint"] == "sha256:" + "0" * 64


@pytest.mark.parametrize("raw,extra", [
    (DATA + DATA, {"limits": {"max_rows_per_artifact": 1}}),
    (DATA + b'{bad}\n', {}), (b'\xff', {}),
    (b'x' * (1024 * 1024 + 1), {"limits": {"max_file_mb": 1}}),
], ids=["row_limit", "malformed_row", "encoding", "file_limit"])
def test_incomplete_fingerprint_abstains(tmp_path, raw, extra):
    code, report = run(tmp_path, {"fingerprint": "0" * 64}, raw=raw, extra=extra)
    assert code == 0
    assert report["findings"] == []
    assert report["diagnostics"]


def test_local_source_presence_missing_and_directory(tmp_path):
    source = tmp_path / "private-source.bin"
    contract = {"source": {"type": "local", "ref": source.name}}
    code, report = run(tmp_path, contract)
    assert code == 1
    f = report["findings"][0]
    assert f["rule_id"] == SOURCE
    assert f["evidence"]["source_status"] == "missing"
    assert "private-source.bin" not in json.dumps(report)
    source.mkdir()
    assert run(tmp_path, contract)[1]["findings"][0]["evidence"]["source_status"] == "not_file"
    source.rmdir()
    source.write_bytes(b"opaque source")
    assert run(tmp_path, contract)[1]["findings"] == []


def test_excluded_source_is_not_read_or_discovered(tmp_path, monkeypatch):
    (tmp_path / "secret.bin").write_bytes(b"must-not-read")
    original = Path.read_bytes
    def guarded(path):
        assert path.name != "secret.bin", "source content must not be opened"
        return original(path)
    monkeypatch.setattr(Path, "read_bytes", guarded)
    code, report = run(tmp_path, {"source": {"type": "local", "ref": "secret.bin"}}, extra={"exclude": ["secret.bin"]})
    assert code == 0
    assert report["findings"] == []


@pytest.mark.parametrize("source", [None, {}, {"type": "local"}, {"ref": "missing.bin"}, {"type": "remote", "ref": "https://invalid.example/private-token"}])
def test_missing_or_remote_source_not_inferred(tmp_path, source, monkeypatch):
    import socket
    monkeypatch.setattr(socket, "create_connection", lambda *a, **kw: pytest.fail("network access"))
    code, report = run(tmp_path, {"source": source})
    assert code == 0
    assert report["findings"] == []
    assert "private-token" not in json.dumps(report)


@pytest.mark.parametrize("ref", ["../private.bin", "a/../private.bin", "/private.bin", "C:\\private.bin", "C:private.bin", "\\\\server\\private", "file:private", "nul\x00name", "a\nname"])
def test_escaping_or_unsafe_local_paths_are_config_errors(tmp_path, ref, monkeypatch):
    monkeypatch.setattr(cli, "discover_files", lambda *a, **kw: pytest.fail("discovery must not start"))
    assert run(tmp_path, {"source": {"type": "local", "ref": ref}})[0] == 3


@pytest.mark.parametrize("contract", [
    {"extra": 1}, {"required": "version"}, {"required": ["source"]},
    {"required": ["version", "version"]}, {"version": 1}, {"license": False},
    {"fingerprint": "not-a-hash"}, {"source": []}, {"source": {"type": "guessed"}},
    {"source": {"ref": []}}, {"generator": {"name": 5}}, {"generator": {"extra": "x"}},
])
def test_invalid_contract_types_rejected(contract):
    with pytest.raises(ConfigError):
        parse_and_validate_config_dict({"artifacts": [{"path": "train.jsonl", "roles": ["training_dataset"], "provenance": contract}]})


def test_validated_contract_trims_values_and_sorts_required():
    cfg = parse_and_validate_config_dict({"artifacts": [{"path": "train.jsonl", "roles": ["training_dataset"], "provenance": {"required": ["version", "license"], "version": "  v1 ", "fingerprint": "A" * 64}}]})
    contract = cfg.artifacts[0].provenance
    assert contract.version == "v1"
    assert contract.required == ["license", "version"]
    assert contract.fingerprint == "sha256:" + "a" * 64


def test_required_metadata_still_checked_for_damaged_artifact(tmp_path):
    code, report = run(tmp_path, {"required": ["version"]}, raw=b"\xff")
    assert code == 0
    assert [f["rule_id"] for f in report["findings"]] == [MISSING]


def test_provenance_determinism_and_sensitive_metadata_redaction(tmp_path, monkeypatch):
    contract = {"required": ["version", "license"], "source": {"type": "remote", "ref": "private-token"}, "generator": {"name": "private-generator"}, "fingerprint": "0" * 64}
    first = run(tmp_path, contract)[1]
    original = cli.discover_files
    monkeypatch.setattr(cli, "discover_files", lambda *a, **kw: list(reversed(original(*a, **kw))))
    second = run(tmp_path, contract)[1]
    for report in [first, second]:
        report["scan"].pop("started_at")
        report["scan"].pop("completed_at")
        assert "private-token" not in json.dumps(report)
        assert "private-generator" not in json.dumps(report)
    assert first == second
    contract["required"].reverse()
    reordered = run(tmp_path, contract)[1]
    assert first["findings"] == reordered["findings"]


def test_resolved_source_escape_rejected_before_discovery(tmp_path, monkeypatch):
    original = Path.resolve
    def resolve(path, *args, **kwargs):
        if path.name == "link.bin":
            return tmp_path.parent / "private-outside.bin"
        return original(path, *args, **kwargs)
    monkeypatch.setattr(Path, "resolve", resolve)
    monkeypatch.setattr(cli, "discover_files", lambda *a, **kw: pytest.fail("unsafe source reached discovery"))
    code, _ = run(tmp_path, {"source": {"type": "local", "ref": "link.bin"}})
    assert code == 3


def test_source_permission_error_is_diagnostic_not_missing_finding(tmp_path, monkeypatch):
    original = Path.stat
    def stat(path, *args, **kwargs):
        if path.name == "denied.bin":
            raise PermissionError("private-denied-source-details")
        return original(path, *args, **kwargs)
    monkeypatch.setattr(Path, "stat", stat)
    code, report = run(tmp_path, {"source": {"type": "local", "ref": "denied.bin"}})
    assert code == 0
    assert report["findings"] == []
    assert any(d["code"] == "artifact.provenance_source_unreadable" for d in report["diagnostics"])
    assert "private-denied-source-details" not in json.dumps(report)


@pytest.mark.parametrize("roles,path", [(["evaluation_result"], "data.json"), (["training_dataset", "configuration"], "data.json"), ([], "data.json"), (["training_dataset"], "data.bin")])
def test_provenance_requires_supported_dataset_target(roles, path):
    with pytest.raises(ConfigError):
        parse_and_validate_config_dict({"artifacts": [{"path": path, "roles": roles, "provenance": {}}]})


def test_provenance_target_cannot_be_silently_excluded(tmp_path, monkeypatch):
    monkeypatch.setattr(cli, "discover_files", lambda *a, **kw: pytest.fail("invalid contract reached discovery"))
    assert run(tmp_path, {"required": ["version"]}, extra={"exclude": ["train.jsonl"]})[0] == 3


def test_provenance_target_must_exist(tmp_path, monkeypatch):
    (tmp_path / "evalproof.yaml").write_text('artifacts:\n- path: absent.jsonl\n  roles: [training_dataset]\n  provenance: {}\n', encoding="utf-8")
    monkeypatch.setattr(cli, "discover_files", lambda *a, **kw: pytest.fail("invalid contract reached discovery"))
    assert cli.main(["scan", str(tmp_path)]) == 3


def test_source_separator_normalization_does_not_leak_ref():
    cfg = parse_and_validate_config_dict({"artifacts": [{"path": "train.jsonl", "roles": ["training_dataset"], "provenance": {"source": {"type": "local", "ref": "./raw\\source.bin"}}}]})
    assert cfg.artifacts[0].provenance.source["ref"] == "raw/source.bin"
