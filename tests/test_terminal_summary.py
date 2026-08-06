from pathlib import Path

from llm_doctor.cli import main


def test_clean_scan_summary_reports_ci_pass(capsys, tmp_path):
    (tmp_path / "eval.jsonl").write_text('{"prompt": "clean one"}\n', encoding="utf-8")

    ret = main(["scan", str(tmp_path)])

    assert ret == 0
    output = capsys.readouterr().out
    assert "EvalProof Trust Preflight" in output
    assert "CI result: pass" in output
    assert "Diagnostics: 0" in output
    assert "JSON report:" in output


def test_failing_scan_summary_reports_ci_failure(capsys, tmp_path):
    (tmp_path / "train.jsonl").write_text('{"prompt": "overlap"}\n', encoding="utf-8")
    (tmp_path / "eval.jsonl").write_text('{"prompt": "overlap"}\n', encoding="utf-8")

    ret = main(["scan", str(tmp_path)])

    assert ret == 1
    output = capsys.readouterr().out
    assert "CI result: fail (finding at or above high)" in output
    assert "Top findings:" in output
    assert "critical confirmed contamination.train_eval_overlap" in output


def test_heuristic_finding_is_marked_in_summary(capsys, tmp_path):
    prompt_dir = tmp_path / "prompts"
    prompt_dir.mkdir()
    (prompt_dir / "eval_prompt.md").write_text("System\n\n{{ context }}\n\nQuestion: {{ question }}\n", encoding="utf-8")

    ret = main(["scan", str(tmp_path)])

    assert ret == 0
    output = capsys.readouterr().out
    assert "medium heuristic contamination.untrusted_context_interpolation" in output
    assert "CI result: pass" in output


def test_diagnostics_summary_includes_count_and_codes(capsys, tmp_path):
    (tmp_path / "eval.jsonl").write_text('{"prompt": "valid"}\n{bad json}\n', encoding="utf-8")

    ret = main(["scan", str(tmp_path)])

    assert ret == 0
    output = capsys.readouterr().out
    assert "Diagnostics: 1" in output
    assert "artifact.row_parse_failed" in output
    assert "eval.jsonl" in output