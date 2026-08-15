from __future__ import annotations

import json
from pathlib import Path

from evalproof.cli import main


def scan_json(root: Path, *extra_args: str) -> tuple[int, dict]:
    output = root.parent / "coverage-report.json"
    ret = main(["scan", str(root), "--json", "--output", str(output), *extra_args])
    return ret, json.loads(output.read_text(encoding="utf-8"))


def write_config(root: Path, body: str) -> None:
    (root / "evalproof.yaml").write_text(body, encoding="utf-8")


def test_json_report_contains_deterministic_artifact_coverage_manifest(tmp_path):
    write_config(
        tmp_path,
        """
artifacts:
  - path: custom_eval.jsonl
    roles: [evaluation_dataset]
""".lstrip(),
    )
    (tmp_path / "custom_eval.jsonl").write_text('{"prompt":"sample"}\n', encoding="utf-8")

    ret, report = scan_json(tmp_path)

    assert ret == 0
    artifacts = report["scan"]["artifacts"]
    assert [artifact["path"] for artifact in artifacts] == sorted(artifact["path"] for artifact in artifacts)

    custom_eval = next(artifact for artifact in artifacts if artifact["path"] == "custom_eval.jsonl")
    assert custom_eval == {
        "path": "custom_eval.jsonl",
        "format": "jsonl",
        "roles": ["evaluation_dataset"],
        "role_source": "config",
        "index_status": "indexed",
        "index_reasons": ["complete"],
        "rows_indexed": 1,
        "rows_rejected": 0,
        "truncated": False,
        "fingerprint": custom_eval["fingerprint"],
        "diagnostic_codes": [],
        "role_matched_rule_ids": sorted(custom_eval["role_matched_rule_ids"]),
    }
    assert custom_eval["fingerprint"].startswith("sha256:")


def test_heuristic_train_eval_role_conflict_is_reported(tmp_path):
    (tmp_path / "train_eval.jsonl").write_text('{"prompt":"sample"}\n', encoding="utf-8")

    ret, report = scan_json(tmp_path)

    assert ret == 0
    artifact = next(item for item in report["scan"]["artifacts"] if item["path"] == "train_eval.jsonl")
    assert set(artifact["roles"]) == {"training_dataset", "evaluation_dataset"}
    assert artifact["role_source"] == "heuristic"
    assert "artifact.role_conflict" in artifact["diagnostic_codes"]
    assert any(diagnostic["code"] == "artifact.role_conflict" for diagnostic in report["diagnostics"])


def test_explicit_multi_role_override_does_not_report_role_conflict(tmp_path):
    write_config(
        tmp_path,
        """
artifacts:
  - path: mixed.jsonl
    roles: [training_dataset, evaluation_dataset]
""".lstrip(),
    )
    (tmp_path / "mixed.jsonl").write_text('{"prompt":"sample"}\n', encoding="utf-8")

    ret, report = scan_json(tmp_path)

    assert ret == 0
    assert not any(diagnostic["code"] == "artifact.role_conflict" for diagnostic in report["diagnostics"])


def test_cross_split_rules_never_compare_an_artifact_with_itself(tmp_path):
    write_config(
        tmp_path,
        """
artifacts:
  - path: mixed.jsonl
    roles: [training_dataset, evaluation_dataset]
  - path: eval.jsonl
    roles: [evaluation_dataset]
""".lstrip(),
    )
    (tmp_path / "mixed.jsonl").write_text('{"prompt":"shared sample"}\n', encoding="utf-8")
    (tmp_path / "eval.jsonl").write_text('{"prompt":"shared sample"}\n', encoding="utf-8")

    ret, report = scan_json(tmp_path)

    assert ret == 1
    overlap_findings = [
        finding
        for finding in report["findings"]
        if finding["rule_id"] == "contamination.train_eval_overlap"
    ]
    assert overlap_findings
    for finding in overlap_findings:
        paths = [location["path"] for location in finding["locations"]]
        assert paths[0] != paths[1]


def test_terminal_summary_reports_coverage(capsys, tmp_path):
    (tmp_path / "eval.jsonl").write_text('{"prompt":"sample"}\n', encoding="utf-8")

    ret = main(["scan", str(tmp_path)])

    assert ret == 0
    assert "Coverage: indexed=" in capsys.readouterr().out


def test_coverage_manifest_marks_partial_indexing_without_double_counting_diagnostics(tmp_path):
    write_config(
        tmp_path,
        """
limits:
  max_rows_per_artifact: 1
artifacts:
  - path: eval.jsonl
    roles: [evaluation_dataset]
""".lstrip(),
    )
    (tmp_path / "eval.jsonl").write_text(
        '{"prompt":"first"}\n'
        "not-json\n"
        '{"prompt":"second"}\n',
        encoding="utf-8",
    )

    ret, report = scan_json(tmp_path)

    assert ret == 0
    artifact = next(item for item in report["scan"]["artifacts"] if item["path"] == "eval.jsonl")
    assert artifact["index_status"] == "partial"
    assert artifact["rows_indexed"] == 1
    assert artifact["rows_rejected"] == 1
    assert artifact["truncated"] is True
    assert artifact["index_reasons"] == ["row_parse_failures", "row_limit"]
