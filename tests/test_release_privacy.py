import json

import pytest

from evalproof.cli import main


def report_for(root, args):
    output = root.parent / (root.name + "-privacy-report.json")
    code = main([*args, str(root), "--json", "--output", str(output)])
    assert code in {0, 1}
    return json.loads(output.read_text(encoding="utf-8"))


def test_interpolation_evidence_never_contains_raw_prompt(tmp_path):
    secret = "private training instruction must never be exposed"
    (tmp_path / "prompt.txt").write_text(secret + " {context}", encoding="utf-8")
    report = report_for(tmp_path, ["scan"])
    findings = [f for f in report["findings"] if f["rule_id"] == "contamination.untrusted_context_interpolation"]
    assert len(findings) == 1
    assert secret not in json.dumps(report)
    assert findings[0]["evidence"]["snippet"].startswith("sha256:")


@pytest.mark.parametrize("command", ["scan", "profile"])
def test_parser_diagnostics_never_echo_source_values(tmp_path, command):
    secret = "private_credential_1234567890"
    (tmp_path / "train.yaml").write_text("prompt: [" + secret, encoding="utf-8")
    report = report_for(tmp_path, [command])
    assert report["diagnostics"]
    assert report["diagnostics"][0]["code"] == "artifact.parse_failed"
    assert secret not in json.dumps(report)


@pytest.mark.parametrize("reference", ["private-secret-reference", "sha256:wrong", 123, {"credential": "private-secret-reference"}, ["private-secret-reference"]])
def test_invalid_reference_is_not_comparable_fingerprint_evidence(tmp_path, reference):
    (tmp_path / "eval.jsonl").write_text('{"prompt":"question"}', encoding="utf-8")
    (tmp_path / "result.json").write_text(json.dumps({"dataset_fingerprint": reference}), encoding="utf-8")
    output = tmp_path.parent / (tmp_path.name + "-fingerprint-report.json")
    assert main(["scan", str(tmp_path), "--rules", "contamination.fingerprint_mismatch", "--json", "--output", str(output)]) == 0
    report = json.loads(output.read_text(encoding="utf-8"))
    assert report["findings"] == []
    assert "private-secret-reference" not in json.dumps(report)
