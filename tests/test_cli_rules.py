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
    "dataset.invalid_text_encoding",
    "dataset.label_inconsistency",
    "dataset.partial_sample_id_coverage",
    "dataset.sample_id_collision",
    "dataset.schema_contract_violation",
    "evaluation.metric_out_of_bounds",
    "evaluation.sample_alignment_mismatch",
    "prompt.unresolved_placeholder",
    "provenance.local_source_unresolved",
    "provenance.manifest_fingerprint_mismatch",
    "provenance.required_metadata_missing",
    "rag.chunk_id_collision",
    "rag.duplicate_chunk_in_corpus",
    "rag.empty_or_corrupted_document",
    "rag.empty_referenced_document",
    "rag.unreachable_context_id",
    "reproducibility.nondeterministic_generation_without_seed",
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
    assert "tags: contamination" in output


def test_rules_command_rejects_unknown_options():
    ret = main(["rules", "--unknown"])

    assert ret == 2


def test_rules_command_uses_separate_readable_rule_blocks(capsys):
    assert main(["rules"]) == 0
    lines = capsys.readouterr().out.splitlines()
    assert "========================" in lines
    assert any(line.startswith("[01] contamination.") for line in lines)
    assert any(line.startswith("     Description: ") for line in lines)
    assert any(line == "" for line in lines)
    assert max(map(len, lines)) <= 96


def test_rules_command_keeps_long_metadata_out_of_single_lines(capsys):
    assert main(["rules"]) == 0
    output = capsys.readouterr().out
    assert " | tags=" not in output
    assert " | severity=" not in output
    assert "default CI: fails default CI" in output
