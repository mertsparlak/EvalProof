"""Explicit release job: generated 100k rows, not part of the fast default suite."""

import hashlib
import json
import os
import time

import pytest

from evalproof.cli import main


@pytest.mark.skipif(os.environ.get("EVALPROOF_RELEASE_SMOKE") != "1", reason="Run in the explicit release-smoke job")
def test_100k_row_scan_and_profile(tmp_path):
    def row(number):
        digest = hashlib.sha256(f"release-row-{number}".encode()).hexdigest()
        return {"id": number, "prompt": " ".join(digest[i:i + 8] for i in range(0, 64, 8))}
    for name, start in (("train.jsonl", 0), ("eval.jsonl", 50000)):
        with (tmp_path / name).open("w", encoding="utf-8") as stream:
            for number in range(start, start + 50000):
                # One exact cross-split sentinel, no same-split duplicate identities.
                stream.write(json.dumps(row(0 if number == 99999 else number)) + "\n")
    scan_output = tmp_path.parent / (tmp_path.name + "-scale-scan.json")
    started = time.perf_counter()
    assert main(["scan", str(tmp_path), "--json", "--output", str(scan_output)]) == 1
    scan_seconds = time.perf_counter() - started
    report = json.loads(scan_output.read_text(encoding="utf-8"))
    assert report["diagnostics"] == []
    assert len(report["scan"]["rules"]["ids"]) == 29
    assert sum(item["rows_indexed"] for item in report["scan"]["artifacts"]) == 100000
    overlap = [f for f in report["findings"] if f["rule_id"] == "contamination.train_eval_overlap"]
    assert len(overlap) == 1
    profile_output = tmp_path.parent / (tmp_path.name + "-scale-profile.json")
    started = time.perf_counter()
    assert main(["profile", str(tmp_path), "--json", "--output", str(profile_output)]) == 0
    profile_seconds = time.perf_counter() - started
    profile = json.loads(profile_output.read_text(encoding="utf-8"))
    assert profile["summary"] == {"artifacts_profiled": 2, "measurements_total": 14}
    assert profile["diagnostics"] == []
    counts = [m["value"] for m in profile["measurements"] if m["measurement_id"] == "dataset.row_count"]
    assert counts == [50000, 50000]
    metrics = {"rows": 100000, "scan_seconds": round(scan_seconds, 3), "profile_seconds": round(profile_seconds, 3)}
    (tmp_path.parent / "release-scale-timings.json").write_text(json.dumps(metrics), encoding="utf-8")
    print(json.dumps(metrics))
