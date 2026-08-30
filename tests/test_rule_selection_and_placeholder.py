import json

from evalproof.cli import main


RULE_ID = "prompt.unresolved_placeholder"


def _write_eval(path, rows):
    path.write_text(
        "".join(json.dumps(row) + "\n" for row in rows),
        encoding="utf-8",
    )


def test_rules_listing_includes_short_description(capsys):
    ret = main(["rules"])

    assert ret == 0
    output = capsys.readouterr().out
    assert RULE_ID in output
    assert "Detects template-like placeholder patterns" in output


def test_selected_scan_runs_only_selected_rules_and_records_scope(tmp_path, capsys):
    _write_eval(tmp_path / "eval.jsonl", [{"prompt": "Answer {user_input}"}])
    (tmp_path / "train.jsonl").write_text(
        '{"prompt": "training-only"}\n',
        encoding="utf-8",
    )

    ret = main(["scan", str(tmp_path), "--rules", f"{RULE_ID}, {RULE_ID}"])

    assert ret == 0
    capsys.readouterr()
    report = json.loads((tmp_path / "evalproof_report.json").read_text(encoding="utf-8"))
    assert report["scan"]["rules"] == {"mode": "selected", "ids": [RULE_ID]}
    assert {finding["rule_id"] for finding in report["findings"]} == {RULE_ID}
    finding = report["findings"][0]
    assert finding["confidence"] == "heuristic"
    assert finding["severity"] == "medium"
    assert finding["locations"][0]["field"] == "prompt"
    assert "user_input" not in json.dumps(finding["evidence"])


def test_selection_order_does_not_change_report_findings(tmp_path, capsys):
    _write_eval(tmp_path / "eval.jsonl", [{"prompt": "Answer {user_input}"}])

    first = main(["scan", str(tmp_path), "--json", "--rules", f"{RULE_ID},dataset.label_inconsistency"])
    capsys.readouterr()
    first_report = json.loads((tmp_path / "evalproof_report.json").read_text(encoding="utf-8"))

    second = main(["scan", str(tmp_path), "--json", "--rules", f"dataset.label_inconsistency,{RULE_ID}"])
    capsys.readouterr()
    second_report = json.loads((tmp_path / "evalproof_report.json").read_text(encoding="utf-8"))

    assert first == second == 0
    assert first_report["findings"] == second_report["findings"]
    assert first_report["scan"]["rules"] == second_report["scan"]["rules"]


def test_unknown_rule_selection_fails_before_writing_report(tmp_path, capsys):
    _write_eval(tmp_path / "eval.jsonl", [{"prompt": "clean"}])

    ret = main(["scan", str(tmp_path), "--rules", "unknown.rule"])

    assert ret == 2
    assert "Unknown rule id(s): unknown.rule" in capsys.readouterr().err
    assert not (tmp_path / "evalproof_report.json").exists()


def test_empty_rule_selection_fails_before_writing_report(tmp_path, capsys):
    _write_eval(tmp_path / "eval.jsonl", [{"prompt": "clean"}])

    ret = main(["scan", str(tmp_path), "--rules", ""])

    assert ret == 2
    assert "non-empty rule ids" in capsys.readouterr().err
    assert not (tmp_path / "evalproof_report.json").exists()


def test_disabled_rule_cannot_be_selected(tmp_path, capsys):
    _write_eval(tmp_path / "eval.jsonl", [{"prompt": "Answer {user_input}"}])
    (tmp_path / "evalproof.yaml").write_text(
        "rules:\n  disabled:\n    - prompt.unresolved_placeholder\n",
        encoding="utf-8",
    )

    ret = main(["scan", str(tmp_path), "--rules", RULE_ID])

    assert ret == 2
    assert "no enabled rules" in capsys.readouterr().err


def test_placeholder_rule_ignores_training_and_prompt_template_artifacts(tmp_path, capsys):
    _write_eval(tmp_path / "train.jsonl", [{"prompt": "Answer {user_input}"}])
    (tmp_path / "prompts").mkdir()
    (tmp_path / "prompts" / "template.md").write_text("Answer {user_input}\n", encoding="utf-8")

    ret = main(["scan", str(tmp_path), "--rules", RULE_ID])

    assert ret == 0
    capsys.readouterr()
    report = json.loads((tmp_path / "evalproof_report.json").read_text(encoding="utf-8"))
    assert report["findings"] == []


def test_placeholder_rule_supports_declared_syntaxes_and_is_deterministic(tmp_path, capsys):
    _write_eval(
        tmp_path / "eval.jsonl",
        [{"question": "A {{ question }} B ${answer} C {context}"}],
    )

    first = main(["scan", str(tmp_path), "--rules", RULE_ID])
    capsys.readouterr()
    first_report = json.loads((tmp_path / "evalproof_report.json").read_text(encoding="utf-8"))
    second = main(["scan", str(tmp_path), "--rules", RULE_ID])
    capsys.readouterr()
    second_report = json.loads((tmp_path / "evalproof_report.json").read_text(encoding="utf-8"))

    assert first == second == 0
    assert first_report["findings"] == second_report["findings"]
    evidence = first_report["findings"][0]["evidence"]
    assert evidence["detected_count"] == 3
    assert evidence["syntax_classes"] == ["dollar_brace", "double_brace", "single_brace"]
