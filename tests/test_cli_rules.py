from evalproof.cli import main


EXPECTED_RULE_IDS = [
    "contamination.duplicate_eval_near_duplicate",
    "contamination.duplicate_eval_sample",
    "contamination.duplicate_train_near_duplicate",
    "contamination.duplicate_train_sample",
    "contamination.fingerprint_mismatch",
    "contamination.missing_repro_metadata",
    "contamination.rag_answer_leakage",
    "contamination.sensitive_value_exposure",
    "contamination.train_eval_near_duplicate",
    "contamination.train_eval_overlap",
    "contamination.untrusted_context_interpolation",
    "dataset.empty_evaluation_input",
    "dataset.label_inconsistency",
    "dataset.sample_id_collision",
    "evaluation.metric_out_of_bounds",
    "evaluation.sample_alignment_mismatch",
    "prompt.unresolved_placeholder",
    "rag.empty_referenced_document",
    "rag.unreachable_context_id",
]


def test_rules_command_lists_all_builtin_rules_deterministically(capsys):
    ret = main(["rules"])

    assert ret == 0
    output = capsys.readouterr().out
    assert "EvalProof Built-in Rules" in output

    positions = []
    for rule_id in EXPECTED_RULE_IDS:
        assert rule_id in output
        positions.append(output.index(rule_id))
    assert positions == sorted(positions)


def test_rules_command_shows_severity_confidence_and_ci_behavior(capsys):
    ret = main(["rules"])

    assert ret == 0
    output = capsys.readouterr().out
    assert "severity=critical" in output
    assert "confidence=confirmed" in output
    assert "confidence=heuristic" in output
    assert "fails default CI" in output
    assert "does not fail default CI" in output
    assert "tags=contamination" in output


def test_rules_command_rejects_unknown_options():
    ret = main(["rules", "--unknown"])

    assert ret == 2
