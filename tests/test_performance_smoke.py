from __future__ import annotations

import json
import time
from pathlib import Path

from llm_doctor.cli import main


def run_scan(root: Path, output_name: str) -> tuple[int, dict, float]:
    output = root.parent / output_name
    start = time.perf_counter()
    ret = main(["scan", str(root), "--json", "--output", str(output)])
    elapsed = time.perf_counter() - start
    assert output.exists()
    return ret, json.loads(output.read_text(encoding="utf-8")), elapsed


def normalize_report(report: dict) -> dict:
    normalized = json.loads(json.dumps(report, sort_keys=True))
    normalized["scan"]["started_at"] = "<timestamp>"
    normalized["scan"]["completed_at"] = "<timestamp>"
    return normalized


def write_jsonl(path: Path, rows: list[str]) -> None:
    path.write_text("\n".join(rows) + "\n", encoding="utf-8")


def test_exact_overlap_smoke_handles_thousands_of_rows(tmp_path):
    train_rows = [f'{{"prompt":"training unique row {idx:05d}"}}' for idx in range(1000)]
    eval_rows = [f'{{"prompt":"evaluation unique row {idx:05d}"}}' for idx in range(1000)]
    train_rows.append('{"prompt":"shared contamination sentinel"}')
    eval_rows.append('{"prompt":"shared contamination sentinel"}')
    write_jsonl(tmp_path / "train.jsonl", train_rows)
    write_jsonl(tmp_path / "eval.jsonl", eval_rows)

    ret, report, elapsed = run_scan(tmp_path, "exact-smoke.json")

    assert ret == 1
    assert elapsed < 10.0
    assert report["summary"]["artifacts_scanned"] == 2
    overlap = [finding for finding in report["findings"] if finding["rule_id"] == "contamination.train_eval_overlap"]
    assert len(overlap) == 1
    assert overlap[0]["evidence"]["training_row"] == 1001
    assert overlap[0]["evidence"]["evaluation_row"] == 1001


def test_similarity_smoke_handles_thousands_of_rows_deterministically(tmp_path):
    (tmp_path / "evalproof.yaml").write_text(
        """
similarity:
  threshold: 0.7
artifacts:
  - path: train.jsonl
    roles: [training_dataset]
  - path: eval.jsonl
    roles: [evaluation_dataset]
""".lstrip(),
        encoding="utf-8",
    )
    train_rows = [f'{{"prompt":"training filler text with stable token {idx:05d}"}}' for idx in range(600)]
    eval_rows = [f'{{"prompt":"evaluation filler text with stable token {idx:05d}"}}' for idx in range(600)]
    train_rows.append('{"prompt":"The Apollo program landed humans on the Moon in 1969."}')
    eval_rows.append('{"prompt":"The Apollo program put humans on the Moon in 1969."}')
    write_jsonl(tmp_path / "train.jsonl", train_rows)
    write_jsonl(tmp_path / "eval.jsonl", eval_rows)

    ret1, report1, elapsed1 = run_scan(tmp_path, "similarity-smoke-1.json")
    ret2, report2, elapsed2 = run_scan(tmp_path, "similarity-smoke-2.json")

    assert ret1 == 1
    assert ret2 == 1
    assert elapsed1 < 10.0
    assert elapsed2 < 10.0
    near = [finding for finding in report1["findings"] if finding["rule_id"] == "contamination.train_eval_near_duplicate"]
    assert len(near) == 1
    assert near[0]["evidence"]["training_row"] == 601
    assert near[0]["evidence"]["evaluation_row"] == 601
    assert normalize_report(report1) == normalize_report(report2)


def test_default_report_file_does_not_affect_large_second_scan(tmp_path):
    train_rows = [f'{{"prompt":"train row {idx:05d}"}}' for idx in range(700)]
    eval_rows = [f'{{"prompt":"eval row {idx:05d}"}}' for idx in range(700)]
    write_jsonl(tmp_path / "train.jsonl", train_rows)
    write_jsonl(tmp_path / "eval.jsonl", eval_rows)

    first = main(["scan", str(tmp_path)])
    assert first == 0
    first_report = normalize_report(json.loads((tmp_path / "evalproof_report.json").read_text(encoding="utf-8")))

    second = main(["scan", str(tmp_path)])
    assert second == 0
    second_report = normalize_report(json.loads((tmp_path / "evalproof_report.json").read_text(encoding="utf-8")))

    assert first_report == second_report
    assert second_report["summary"]["artifacts_scanned"] == 2