"""Unit and integration tests for Milestone 4: Reporting Pipeline and CLI Interface."""

import json
from pathlib import Path
import tempfile
import pytest

from llm_doctor.cli import main
from llm_doctor.finding import Finding, Location, Severity, Confidence
from llm_doctor.reporting import (
    sort_findings_deterministically,
    generate_json_report,
    render_terminal_summary,
)


def test_sort_findings_deterministically():
    f_medium = Finding(
        rule_id="contamination.untrusted_context_interpolation",
        severity=Severity.MEDIUM.value,
        confidence=Confidence.HEURISTIC.value,
        title="Medium finding",
        message="msg",
        impact="imp",
        recommendation="rec",
        locations=[Location(role="primary", path="b_prompt.md", line=10)],
        evidence={"k": "v"},
    )
    f_critical = Finding(
        rule_id="contamination.train_eval_overlap",
        severity=Severity.CRITICAL.value,
        confidence=Confidence.CONFIRMED.value,
        title="Critical finding",
        message="msg",
        impact="imp",
        recommendation="rec",
        locations=[Location(role="source", path="a_train.jsonl", row=5)],
        evidence={"k": "v"},
    )

    sorted_f = sort_findings_deterministically([f_medium, f_critical])
    assert sorted_f[0].severity == "critical"
    assert sorted_f[1].severity == "medium"


def test_generate_json_report_schema():
    report = generate_json_report(
        scan_root=".",
        config_path="evalproof.yaml",
        artifacts_scanned=2,
        findings=[],
        diagnostics=[],
        started_at="2026-01-01T00:00:00Z",
        completed_at="2026-01-01T00:00:01Z",
    )
    assert report["schema_version"] == "1.0"
    assert report["tool"]["name"] == "evalproof"
    assert report["scan"]["root"] == "."
    assert report["summary"]["artifacts_scanned"] == 2
    assert report["summary"]["findings_total"] == 0
    assert report["summary"]["findings_by_severity"]["critical"] == 0


def test_cli_exit_code_0_clean_scan():
    with tempfile.TemporaryDirectory() as tmp_dir:
        p = Path(tmp_dir)
        (p / "data").mkdir()
        (p / "data" / "clean.jsonl").write_text('{"q": "unique 1"}\n{"q": "unique 2"}\n', encoding="utf-8")

        ret = main(["scan", tmp_dir])
        assert ret == 0


def test_cli_exit_code_1_failing_severity():
    with tempfile.TemporaryDirectory() as tmp_dir:
        p = Path(tmp_dir)
        (p / "train.jsonl").write_text('{"q": "overlap"}\n', encoding="utf-8")
        (p / "eval.jsonl").write_text('{"q": "overlap"}\n', encoding="utf-8")

        ret = main(["scan", tmp_dir])
        assert ret == 1


def test_cli_exit_code_2_output_without_json():
        ret = main(["scan", ".", "--output", "report.json"])
        assert ret == 2


def test_cli_exit_code_2_invalid_fail_on():
        ret = main(["scan", ".", "--fail-on", "super_high"])
        assert ret == 2


def test_cli_exit_code_3_invalid_config():
    with tempfile.TemporaryDirectory() as tmp_dir:
        p = Path(tmp_dir)
        (p / "evalproof.yaml").write_text("invalid_top_key: 123\n", encoding="utf-8")

        ret = main(["scan", tmp_dir])
        assert ret == 3


def test_cli_exit_code_4_non_existent_scan_root():
    ret = main(["scan", "non_existent_directory_xyz123"])
    assert ret == 4


def test_cli_json_and_output(capsys):
    with tempfile.TemporaryDirectory() as tmp_dir:
        p = Path(tmp_dir)
        out_json = p / "out.json"
        (p / "eval.jsonl").write_text('{"q": "1"}\n', encoding="utf-8")

        ret = main(["scan", tmp_dir, "--json", "--output", str(out_json)])
        assert ret == 0
        assert out_json.exists()
        content = json.loads(out_json.read_text(encoding="utf-8"))
        assert content["schema_version"] == "1.0"
