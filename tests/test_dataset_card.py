import hashlib
import json
from pathlib import Path

import pytest
import yaml

import evalproof.cli as cli

RULE = "provenance.required_metadata_missing"


def run(root, *, card="private-card.md", license=None, required=None):
    (root / "train.jsonl").write_text('{"prompt":"hello"}\n', encoding="utf-8")
    contract = {"required": required or ["license"], "card": card, "license": license}
    config = {"include": ["train.jsonl"], "similarity": {"enabled": False},
              "artifacts": [{"path": "train.jsonl", "roles": ["training_dataset"],
                             "provenance": contract}]}
    (root / "evalproof.yaml").write_text(yaml.safe_dump(config), encoding="utf-8")
    output = root.parent / (root.name + "-card-report.json")
    code = cli.main(["scan", str(root), "--rules", RULE, "--json", "--output", str(output)])
    return code, json.loads(output.read_text(encoding="utf-8")) if code in {0, 1} else None


@pytest.mark.parametrize("value", ["private-license-token", "[private-license-token, other-token]", "' yes '"])
def test_card_license_satisfies_required_metadata_offline(tmp_path, value, monkeypatch):
    import socket
    monkeypatch.setattr(socket, "create_connection", lambda *a, **k: pytest.fail("network"))
    (tmp_path / "private-card.md").write_text("---\nlicense: " + value + "\n---\nprivate-body", encoding="utf-8")
    code, report = run(tmp_path)
    assert code == 0 and not report["findings"] and not report["diagnostics"]
    assert "private-license-token" not in json.dumps(report)
    assert "private-body" not in json.dumps(report)


@pytest.mark.parametrize("metadata", ["{}", "license: null", "license: ''", "license: []", "language: en"])
def test_observed_missing_license_has_bounded_evidence(tmp_path, metadata):
    header = ("---\n" + metadata + "\n---\n").encode()
    (tmp_path / "private-card.md").write_bytes(header + b"body-secret")
    code, report = run(tmp_path)
    assert code == 0 and len(report["findings"]) == 1
    evidence = report["findings"][0]["evidence"]
    assert evidence["missing_fields"] == ["license"]
    assert evidence["license_status"] == "missing"
    assert evidence["card_header_fingerprint"] == "sha256:" + hashlib.sha256(header).hexdigest()
    assert "private-card.md" not in json.dumps(report)
    assert "body-secret" not in json.dumps(report)


@pytest.mark.parametrize("body", [
    b"not front matter", b"---\nlicense: x", b"---\nlicense: [\n---\n",
    b"---\nlicense: 42\n---\n", b"---\nlicense: [x, null]\n---\n",
    b"---\nlicense: ['']\n---\n", b"---\nlicense: yes\n---\n",
    b"---\nlicense: x\nlicense: y\n---\n", b"---\n1: x\n---\n",
    b"---\nlicense: &a x\nother: *a\n---\n", b"---\nlicense: !!str x\n---\n",
    b"---\n- x\n---\n", b"---\nlicense: \xff\n---\n",
    b"---\nlicense: " + b"[" * 17 + b"x" + b"]" * 17 + b"\n---\n",
    b"---\nlicense: [" + b"x," * 3000 + b"x]\n---\n",
    b"---\nlicense: " + b"x" * (1024 * 1024) + b"\n---\n",
], ids=["no-header", "no-close", "invalid-yaml", "number", "mixed-list", "blank-list",
        "boolean", "duplicate-key", "numeric-key", "alias", "tag", "sequence",
        "encoding", "depth", "tokens", "bytes"])
def test_unobservable_card_abstains_only_for_license(tmp_path, body):
    (tmp_path / "private-card.md").write_bytes(body)
    code, report = run(tmp_path, required=["license", "version"])
    assert code == 0
    assert report["findings"][0]["evidence"]["missing_fields"] == ["version"]
    assert report["diagnostics"][0]["code"] == "artifact.dataset_card_unavailable"
    assert report["diagnostics"][0]["details"]["license_status"] == "unavailable"
    assert report["scan"]["artifacts"][0]["index_status"] == "indexed"


def test_explicit_license_wins_even_when_card_unavailable(tmp_path):
    code, report = run(tmp_path, license="private-explicit-license")
    assert code == 0 and not report["findings"] and report["diagnostics"]
    assert "private-explicit-license" not in json.dumps(report)


def test_card_permission_error_is_redacted(tmp_path, monkeypatch):
    original = Path.open
    (tmp_path / "private-card.md").write_text("---\nlicense: x\n---", encoding="utf-8")
    def guarded(path, *args, **kwargs):
        if path.name == "private-card.md":
            raise PermissionError("private-exception-details")
        return original(path, *args, **kwargs)
    monkeypatch.setattr(Path, "open", guarded)
    code, report = run(tmp_path)
    assert code == 0 and not report["findings"] and report["diagnostics"]
    assert "private-exception-details" not in json.dumps(report)


@pytest.mark.parametrize("ref", [None, "", " ", 1, "../card.md", "/card.md", "C:\\card.md", "https://invalid/card.md", "card.txt", "card.md\n"])
def test_invalid_card_binding_is_config_error(tmp_path, ref, monkeypatch):
    monkeypatch.setattr(cli, "discover_files", lambda *a, **k: pytest.fail("discovery"))
    assert run(tmp_path, card=ref)[0] == 3


def test_card_resolved_escape_rejected(tmp_path, monkeypatch):
    original = Path.resolve
    def resolve(path, *args, **kwargs):
        if path.name == "private-card.md":
            return tmp_path.parent / "outside.md"
        return original(path, *args, **kwargs)
    monkeypatch.setattr(Path, "resolve", resolve)
    monkeypatch.setattr(cli, "discover_files", lambda *a, **k: pytest.fail("discovery"))
    assert run(tmp_path)[0] == 3


def test_bom_crlf_and_body_not_parsed(tmp_path):
    (tmp_path / "private-card.md").write_bytes(b"\xef\xbb\xbf---\r\nlicense: x\r\n---\r\n\xff" + b"x" * 2000000)
    assert run(tmp_path)[1]["findings"] == []
    assert not run(tmp_path)[1]["diagnostics"]


def test_determinism_and_other_fields_not_inferred(tmp_path, monkeypatch):
    (tmp_path / "private-card.md").write_text("---\nversion: private-version\n---", encoding="utf-8")
    first = run(tmp_path, required=["license", "version"])[1]
    original = cli.discover_files
    monkeypatch.setattr(cli, "discover_files", lambda *a, **k: list(reversed(original(*a, **k))))
    second = run(tmp_path, required=["version", "license"])[1]
    for report in [first, second]:
        report["scan"].pop("started_at")
        report["scan"].pop("completed_at")
    assert first == second
    assert first["findings"][0]["evidence"]["missing_fields"] == ["license", "version"]
    assert "private-version" not in json.dumps(first)


def test_unset_card_preserves_contract_fingerprint(tmp_path):
    from tests.test_provenance import run as run_existing
    from evalproof.finding import canonical_json_dumps
    contract = {"required": ["license"], "version": None, "fingerprint": None,
                "source": {}, "generator": {}, "license": None}
    report = run_existing(tmp_path, {"required": ["license"]})[1]
    expected = "sha256:" + hashlib.sha256(canonical_json_dumps(contract).encode()).hexdigest()
    assert report["findings"][0]["evidence"]["contract_fingerprint"] == expected


def test_shared_card_read_once_and_refreshed_on_build(tmp_path, monkeypatch):
    from evalproof.config import parse_and_validate_config_dict
    from evalproof.artifact import create_artifact_from_file
    import evalproof.project_index as module
    config = parse_and_validate_config_dict({"similarity": {"enabled": False}, "artifacts": [
        {"path": name, "roles": ["training_dataset"], "provenance": {"card": "private-card.md"}}
        for name in ["a.jsonl", "b.jsonl"]]})
    for name in ["a.jsonl", "b.jsonl"]:
        (tmp_path / name).write_text('{}\n', encoding="utf-8")
    card = tmp_path / "private-card.md"
    card.write_text("---\nlicense: x\n---", encoding="utf-8")
    original = module.read_dataset_card
    calls = []
    def read(*args):
        calls.append(args[1])
        return original(*args)
    monkeypatch.setattr(module, "read_dataset_card", read)
    index = module.ProjectIndex(config, scan_root=str(tmp_path))
    artifacts = [create_artifact_from_file(str(tmp_path), name, config) for name in ["a.jsonl", "b.jsonl"]]
    index.build(artifacts)
    assert calls == ["private-card.md"]
    assert all(f["license_status"] == "present" for f in index.dataset_cards.values())
    card.write_text("---\n{}\n---", encoding="utf-8")
    index.build(list(reversed(artifacts)))
    assert calls == ["private-card.md", "private-card.md"]
    assert all(f["license_status"] == "missing" for f in index.dataset_cards.values())


def test_byte_limit_and_no_body_read(tmp_path, monkeypatch):
    import io
    from evalproof.dataset_card import read_dataset_card
    header = b"---\nlicense: x\n---\n"
    path = tmp_path / "card.md"
    path.write_bytes(header)
    class Guarded(io.BytesIO):
        def readline(self, size=-1):
            assert self.tell() < len(header), "card body was read"
            return super().readline(size)
    monkeypatch.setattr(Path, "open", lambda *a, **k: Guarded(header + b"secret-body"))
    assert read_dataset_card(str(tmp_path), "card.md", len(header))["license_status"] == "present"
    assert read_dataset_card(str(tmp_path), "card.md", len(header) - 1)["license_status"] == "unavailable"


def test_non_file_and_missing_card_do_not_prove_missing_license(tmp_path):
    for name in ["absent.md", "directory.md"]:
        if name == "directory.md":
            (tmp_path / name).mkdir()
        code, report = run(tmp_path, card=name)
        assert code == 0 and not report["findings"] and len(report["diagnostics"]) == 1


def test_profile_observes_card_failure_without_new_measurements(tmp_path, monkeypatch):
    run(tmp_path)
    monkeypatch.setattr(cli, "execute_rules", lambda *a, **k: pytest.fail("profile ran rules"))
    output = tmp_path.parent / "card-profile.json"
    assert cli.main(["profile", str(tmp_path), "--json", "--output", str(output)]) == 0
    report = json.loads(output.read_text(encoding="utf-8"))
    assert len(report["measurements"]) == 7
    assert report["diagnostics"][0]["code"] == "artifact.dataset_card_unavailable"
    assert all(m["coverage"]["status"] == "complete" for m in report["measurements"])
