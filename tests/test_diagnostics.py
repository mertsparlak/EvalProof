from __future__ import annotations

import json
from pathlib import Path

from evalproof.cli import main


def test_malformed_and_limited_artifacts_emit_diagnostics_without_crashing(tmp_path):
    root = tmp_path / "project"
    root.mkdir()
    (root / "evalproof.yaml").write_text(
        "\n".join(
            [
                "limits:",
                "  max_file_mb: 1",
                "  max_rows_per_artifact: 1",
                "artifacts:",
                "  - path: notes.weird",
                "    roles: [evaluation_dataset]",
            ]
        )
        + "\n",
        encoding="utf-8",
    )
    (root / "eval.jsonl").write_text('{"prompt": "valid one"}\n{bad json}\n{"prompt": "valid two"}\n', encoding="utf-8")
    (root / "broken.json").write_text('{"not": "closed"', encoding="utf-8")
    (root / "broken.yaml").write_text('key: [unterminated\n', encoding="utf-8")
    (root / "broken.toml").write_text('name = "unterminated\n', encoding="utf-8")
    (root / "notes.weird").write_text("configured unsupported extension", encoding="utf-8")
    (root / "large_eval.jsonl").write_text('{"prompt":"x"}\n' * 90000, encoding="utf-8")

    output_path = tmp_path / "report.json"
    ret = main(["scan", str(root), "--json", "--output", str(output_path), "--fail-on", "critical"])

    assert ret == 0
    report = json.loads(output_path.read_text(encoding="utf-8"))
    assert report["findings"] == []
    codes = {diagnostic["code"] for diagnostic in report["diagnostics"]}
    assert {
        "artifact.row_parse_failed",
        "artifact.row_limit_reached",
        "artifact.parse_failed",
        "artifact.file_size_limit_exceeded",
        "artifact.unsupported_extension",
    }.issubset(codes)


def test_cli_output_write_failure_returns_exit_code_5(tmp_path):
    root = tmp_path / "project"
    root.mkdir()
    (root / "eval.jsonl").write_text('{"prompt": "clean"}\n', encoding="utf-8")

    ret = main(["scan", str(root), "--json", "--output", str(root)])

    assert ret == 5
