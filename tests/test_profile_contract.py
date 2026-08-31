import copy
import hashlib
import json
from pathlib import Path

import pytest
import yaml

import evalproof.cli as cli
from evalproof.similarity import SimilarityIndex


def profile(root, *args):
    output = root.parent / (root.name + "-profile-report.json")
    result = cli.main(["profile", str(root), "--json", "--output", str(output), *args])
    return result, json.loads(output.read_text(encoding="utf-8")) if output.exists() else None


def test_profile_is_not_a_scan_or_similarity_run(tmp_path, monkeypatch):
    def forbidden(*args, **kwargs):
        raise AssertionError("rule/similarity code must not run")
    monkeypatch.setattr(cli, "execute_rules", forbidden)
    monkeypatch.setattr(cli.default_registry, "get_enabled_rules", forbidden)
    monkeypatch.setattr(SimilarityIndex, "add_item", forbidden)
    monkeypatch.setattr(SimilarityIndex, "find_all_pairs", forbidden)
    (tmp_path / "train.jsonl").write_text('{"prompt":"private input"}\n' * 2, encoding="utf-8")
    (tmp_path / "eval.jsonl").write_text('{"prompt":"private input"}\n', encoding="utf-8")
    (tmp_path / "corpus.txt").write_text("private document", encoding="utf-8")
    before = {p.name: p.read_bytes() for p in tmp_path.iterdir()}
    code, report = profile(tmp_path)
    assert code == 0
    assert set(report) == {"schema_version", "report_type", "tool", "profile", "summary", "measurements", "diagnostics"}
    assert report["schema_version"] == "1.0"
    assert report["report_type"] == "profile"
    assert report["profile"]["root"] == "."
    assert report["measurements"] == []
    assert report["summary"] == {"artifacts_profiled": 2, "measurements_total": 0}
    assert [a["path"] for a in report["profile"]["artifacts"]] == ["eval.jsonl", "train.jsonl"]
    assert all("role_matched_rule_ids" not in a for a in report["profile"]["artifacts"])
    assert "private" not in json.dumps(report)
    assert before == {p.name: p.read_bytes() for p in tmp_path.iterdir()}


@pytest.mark.parametrize("args", [["--rules", "dataset.label_inconsistency"], ["--fail-on", "high"], ["--unknown"], ["--output", "x.json"]])
def test_profile_invalid_usage_precedes_io(tmp_path, args, monkeypatch):
    def forbidden(*args, **kwargs):
        pytest.fail("invalid usage touched config")
    monkeypatch.setattr(cli, "load_config", forbidden)
    assert cli.main(["profile", str(tmp_path / "missing"), *args]) == 2


def test_profile_help_does_not_read_files(monkeypatch, capsys):
    monkeypatch.setattr(cli, "load_config", lambda *a, **k: pytest.fail("help read config"))
    assert cli.main(["profile", "--help"]) == 0
    assert "usage:" in capsys.readouterr().out


def test_profile_error_categories(tmp_path, monkeypatch):
    assert cli.main(["profile", str(tmp_path / "missing")]) == 4
    (tmp_path / "evalproof.yaml").write_text("unknown: true", encoding="utf-8")
    assert profile(tmp_path)[0] == 3
    (tmp_path / "evalproof.yaml").unlink()
    (tmp_path / "train.jsonl").write_text('{}\n', encoding="utf-8")
    assert cli.main(["profile", str(tmp_path), "--json", "--output", str(tmp_path)]) == 5
    def bad_index(*a, **kw):
        raise RuntimeError("private internal text")
    monkeypatch.setattr(cli.ProjectIndex, "build", bad_index)
    assert profile(tmp_path)[0] == 6


def test_profile_diagnostics_and_default_output(tmp_path, capsys):
    (tmp_path / "train.jsonl").write_text('{}\n{broken}', encoding="utf-8")
    assert cli.main(["profile", str(tmp_path)]) == 0
    text = capsys.readouterr().out
    assert "EvalProof Dataset Profile" in text
    assert "CI result:" not in text
    assert "Diagnostics: 1" in text
    first = json.loads((tmp_path / "evalproof_profile.json").read_text(encoding="utf-8"))
    assert first["diagnostics"][0]["code"] == "artifact.row_parse_failed"
    assert first["profile"]["artifacts"][0]["index_status"] == "partial"
    assert cli.main(["profile", str(tmp_path), "--json"]) == 0
    second = json.loads(capsys.readouterr().out)
    for report in (first, second):
        for key in ("started_at", "completed_at"):
            report["profile"].pop(key)
    assert first == second


def test_profile_ignores_its_custom_output_even_with_exclude_override(tmp_path):
    (tmp_path / "evalproof.yaml").write_text("exclude: []", encoding="utf-8")
    (tmp_path / "train.jsonl").write_text('{}\n', encoding="utf-8")
    output = tmp_path / "train_profile.json"
    results = []
    for _ in range(2):
        assert cli.main(["profile", str(tmp_path), "--json", "--output", str(output)]) == 0
        report = json.loads(output.read_text(encoding="utf-8"))
        for field in ("started_at", "completed_at"):
            report["profile"].pop(field)
        results.append(report)
    assert results[0] == results[1]
    assert results[0]["summary"]["artifacts_profiled"] == 1


def test_profile_empty_root_and_disabled_rules(tmp_path):
    (tmp_path / "evalproof.yaml").write_text(yaml.safe_dump({"rules": {"disabled": [r.id for r in cli.default_registry.get_all_rules()]}}), encoding="utf-8")
    code, report = profile(tmp_path)
    assert code == 0
    assert report["summary"] == {"artifacts_profiled": 0, "measurements_total": 0}


def test_profile_traversal_order_determinism(tmp_path, monkeypatch):
    (tmp_path / "train.jsonl").write_text('{}\n', encoding="utf-8")
    (tmp_path / "eval.jsonl").write_text('{}\n', encoding="utf-8")
    first = profile(tmp_path)[1]
    original = cli.discover_files
    monkeypatch.setattr(cli, "discover_files", lambda *a: list(reversed(original(*a))))
    second = profile(tmp_path)[1]
    for report in (first, second):
        for key in ("started_at", "completed_at"):
            report["profile"].pop(key)
    assert first == second


def measurement(**overrides):
    from evalproof.measurement import Measurement
    data = dict(measurement_id="dataset.row_count", artifact_id="sha256:" + "0" * 64,
                artifact_path="train.jsonl", scope={"type": "artifact"}, value=2, unit="rows",
                population_count=2, coverage={"status": "complete", "reasons": ["complete"]},
                parameters={}, method="indexed_rows/v1", evidence={"observed_rows": 2})
    data.update(overrides)
    return Measurement(**data)


def test_measurement_fingerprint_and_shape():
    item = measurement()
    result = item.to_dict()
    assert not {"severity", "confidence", "impact", "recommendation"}.intersection(result)
    payload = copy.deepcopy(result)
    fingerprint = payload.pop("fingerprint")
    assert fingerprint == "sha256:" + hashlib.sha256(json.dumps(payload, sort_keys=True, separators=(",", ":"), ensure_ascii=False).encode("utf-8")).hexdigest()
    assert measurement().to_dict() == result
    assert measurement(method="indexed_rows/v2").fingerprint != fingerprint
    assert measurement(value=3).fingerprint != fingerprint


@pytest.mark.parametrize("value", [float("nan"), float("inf"), {"x": float("-inf")}])
def test_measurement_rejects_nonfinite_values(value):
    with pytest.raises(ValueError):
        measurement(value=value)


@pytest.mark.parametrize("change", [
    {"population_count": True}, {"population_count": -1},
    {"scope": {"type": "unknown"}}, {"coverage": {"status": "good", "reasons": []}},
    {"artifact_path": "../private.jsonl"}, {"artifact_path": "C:/private.jsonl"},
    {"measurement_id": "Not An ID"}, {"parameters": []},
])
def test_measurement_rejects_invalid_contract(change):
    with pytest.raises(ValueError):
        measurement(**change)


def test_measurement_scope_order_and_report_order():
    from evalproof.reporting import generate_profile_report
    a = measurement(scope={"type": "field", "field": "prompt"})
    b = measurement(scope={"field": "prompt", "type": "field"})
    assert a.fingerprint == b.fingerprint
    c = measurement(measurement_id="dataset.other")
    first = generate_profile_report(None, [], [a, c], [], "start", "end")
    second = generate_profile_report(None, [], [c, b], [], "start", "end")
    assert first == second


def test_profile_defaults_to_cwd_and_relative_output(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    (tmp_path / "train.jsonl").write_text('{}\n', encoding="utf-8")
    assert cli.main(["profile", "--json", "--output", "out/profile.json"]) == 0
    assert (tmp_path / "out/profile.json").exists()
    assert not (tmp_path / "evalproof_profile.json").exists()


def test_profile_serialization_error_is_internal_not_write_failure(tmp_path, monkeypatch):
    monkeypatch.setattr(cli, "generate_profile_report", lambda *a: {"invalid": float("nan")})
    assert profile(tmp_path)[0] == 6


def test_profile_process_determinism(tmp_path):
    import os
    import subprocess
    import sys
    (tmp_path / "train.jsonl").write_text('{"prompt":"private data"}\n{bad}', encoding="utf-8")
    output = tmp_path.parent / (tmp_path.name + "-profile.json")
    reports = []
    for seed in ("1", "987"):
        result = subprocess.run([sys.executable, "-c", "from evalproof.cli import main; raise SystemExit(main())",
            "profile", str(tmp_path), "--json", "--output", str(output)],
            env={**os.environ, "PYTHONHASHSEED": seed}, capture_output=True, text=True)
        assert result.returncode == 0, result.stderr
        report = json.loads(output.read_text(encoding="utf-8"))
        for field in ("started_at", "completed_at"):
            report["profile"].pop(field)
        reports.append(report)
    assert reports[0] == reports[1]
