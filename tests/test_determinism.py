from __future__ import annotations

import json
import os
import shutil
import subprocess
import sys
from pathlib import Path

from evalproof.cli import main


FIXTURE_ROOT = Path(__file__).parent / "fixtures" / "contaminated_project"


def normalized_report(report: dict) -> dict:
    normalized = json.loads(json.dumps(report, sort_keys=True))
    normalized["scan"]["started_at"] = "<timestamp>"
    normalized["scan"]["completed_at"] = "<timestamp>"
    return normalized


def test_scan_report_is_deterministic_for_unchanged_inputs(tmp_path):
    root = tmp_path / "contaminated_project"
    shutil.copytree(FIXTURE_ROOT, root)

    outputs = []
    for idx in range(2):
        output_path = tmp_path / f"report-{idx}.json"
        ret = main(["scan", str(root), "--json", "--output", str(output_path)])
        assert ret == 1
        outputs.append(normalized_report(json.loads(output_path.read_text(encoding="utf-8"))))

    assert outputs[0] == outputs[1]


def test_default_report_file_does_not_change_second_scan_results(tmp_path):
    root = tmp_path / "contaminated_project"
    shutil.copytree(FIXTURE_ROOT, root)

    first = main(["scan", str(root)])
    assert first == 1
    first_report = normalized_report(json.loads((root / "evalproof_report.json").read_text(encoding="utf-8")))

    second = main(["scan", str(root)])
    assert second == 1
    second_report = normalized_report(json.loads((root / "evalproof_report.json").read_text(encoding="utf-8")))

    assert first_report == second_report


def test_full_scan_report_is_stable_across_process_hash_seeds(tmp_path):
    root = tmp_path / "project"
    shutil.copytree(FIXTURE_ROOT, root)
    reports = []
    for seed in ["1", "2", "987"]:
        output = tmp_path / f"report-{seed}.json"
        result = subprocess.run(
            [sys.executable, "-c", "from evalproof.cli import main; raise SystemExit(main())", "scan", str(root), "--json", "--output", str(output)],
            capture_output=True, text=True, env={**os.environ, "PYTHONHASHSEED": seed},
        )
        assert result.returncode == 1, result.stderr
        assert output.exists(), result.stderr
        reports.append(normalized_report(json.loads(output.read_text(encoding="utf-8"))))
    assert reports[0] == reports[1] == reports[2]
