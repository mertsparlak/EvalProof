from __future__ import annotations

import json
import shutil
from pathlib import Path

from evalproof.cli import main


FIXTURE_ROOT = Path(__file__).parent / "fixtures" / "contaminated_project"


def copy_fixture(tmp_path: Path) -> Path:
    target = tmp_path / "contaminated_project"
    shutil.copytree(FIXTURE_ROOT, target)
    return target


def run_json_scan(root: Path, output_name: str = "report.json") -> tuple[int, dict]:
    output_path = root.parent / output_name
    ret = main(["scan", str(root), "--json", "--output", str(output_path)])
    assert output_path.exists()
    return ret, json.loads(output_path.read_text(encoding="utf-8"))


def test_json_report_matches_public_contract(tmp_path):
    root = copy_fixture(tmp_path)
    ret, report = run_json_scan(root)

    assert ret == 1
    assert set(report) == {"schema_version", "tool", "scan", "summary", "findings", "diagnostics"}
    assert report["schema_version"] == "1.0"
    assert report["tool"] == {"name": "evalproof", "version": "0.2.0"}
    assert set(report["scan"]) == {"root", "started_at", "completed_at", "config_path", "rules", "artifacts"}
    assert report["scan"]["rules"]["mode"] == "all"
    assert report["scan"]["rules"]["ids"]
    assert report["scan"]["rules"]["ids"] == sorted(report["scan"]["rules"]["ids"])
    assert report["scan"]["root"] == "."
    assert report["scan"]["config_path"] == "evalproof.yaml"
    assert report["scan"]["artifacts"]
    assert set(report["summary"]["findings_by_severity"]) == {"critical", "high", "medium", "low"}
    assert report["summary"]["findings_total"] == len(report["findings"])

    required_finding_keys = {
        "rule_id",
        "severity",
        "confidence",
        "title",
        "message",
        "impact",
        "recommendation",
        "locations",
        "evidence",
        "fingerprint",
    }
    assert report["findings"]
    for finding in report["findings"]:
        assert set(finding) == required_finding_keys
        assert finding["evidence"]
        assert finding["impact"]
        assert finding["recommendation"]
        assert finding["fingerprint"].startswith("sha256:")
        for location in finding["locations"]:
            path = location.get("path")
            if path:
                assert not Path(path).is_absolute()
                assert "\\" not in path

    for diagnostic in report["diagnostics"]:
        assert {"severity", "code", "message"}.issubset(diagnostic)
        if "path" in diagnostic:
            assert not Path(diagnostic["path"]).is_absolute()
            assert "\\" not in diagnostic["path"]


def test_golden_fixture_emits_expected_rule_families(tmp_path):
    root = copy_fixture(tmp_path)
    ret, report = run_json_scan(root)

    assert ret == 1
    rule_ids = {finding["rule_id"] for finding in report["findings"]}
    assert {
        "contamination.train_eval_overlap",
        "contamination.train_eval_near_duplicate",
        "contamination.duplicate_eval_sample",
        "contamination.duplicate_train_sample",
        "contamination.rag_answer_leakage",
        "contamination.missing_repro_metadata",
        "contamination.fingerprint_mismatch",
        "contamination.untrusted_context_interpolation",
        "contamination.sensitive_value_exposure",
    }.issubset(rule_ids)
    assert any(f["severity"] in {"critical", "high"} for f in report["findings"])
