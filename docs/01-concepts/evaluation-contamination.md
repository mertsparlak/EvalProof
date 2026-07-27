# Evaluation Contamination

## Question

What does evaluation contamination mean in this project?

## Definition

Evaluation contamination is any evidence-backed flaw in evaluation artifacts that can make evaluation results misleading, invalid, non-reproducible, or unsafe to trust.

EvalProof focuses on contamination because it directly affects the question defined in [Positioning](../00-product/positioning.md):

> Can I trust these evaluation artifacts?

## Contamination Categories

### Split Leakage

Split leakage occurs when training data overlaps with evaluation or benchmark data.

The MVP detects exact normalized overlap. Near-duplicate detection is outside MVP unless it can be implemented deterministically and cheaply without changing the rule contract.

### Duplicate Evaluation Samples

Duplicate evaluation samples occur when the same or equivalent sample appears multiple times in an evaluation dataset.

Duplicates can overweight specific cases and inflate confidence in evaluation results.

### RAG Answer Leakage

RAG answer leakage occurs when evaluation answers or gold labels are present in retrieval documents in a way that lets a system answer by copying rather than reasoning or retrieving appropriately.

The MVP focuses on evidence-backed exact or normalized text containment patterns.

### Benchmark Contamination

Benchmark contamination occurs when benchmark examples are present in training data, evaluation examples, RAG corpora, generated outputs used for tuning, or other artifacts that should remain independent.

### Reproducibility Contamination

Reproducibility contamination occurs when evaluation results cannot be interpreted or reproduced because required metadata is missing or inconsistent.

Examples include missing model id, generation parameters, prompt fingerprint, dataset fingerprint, metric definition, or timestamp.

### Prompt-Artifact Mismatch

Prompt-artifact mismatch occurs when an evaluation result claims or implies one prompt version but the available prompt artifact fingerprint differs.

The MVP should detect only cases where both sides expose comparable evidence.

### Trust-Sensitive Exposure

Trust-sensitive exposure occurs when an evaluation artifact contains secret-like or PII-like values that compromise the safe use of that artifact.

This category is included only as a trust check on evaluation artifacts, not as a general security scanner.

## What Is Not Contamination

The following are not contamination by themselves:

- A low benchmark score.
- A weak prompt style.
- A small dataset without evidence of invalidity.
- Domain bias without concrete evidence.
- A subjective judgment that examples are poor.
- A model output that seems bad.

Those may matter, but they are not MVP contamination findings unless supported by a specific rule in [Contamination Rules](../03-rule-design/contamination-rules.md).

## Design Decisions

- Evaluation contamination is the project center of gravity.
- MVP contamination detection favors exact, normalized, deterministic evidence.
- Subjective dataset, prompt, or model quality judgments are excluded.
- Security-sensitive issues are included only when they affect evaluation artifact trust.

## Open Questions

None.

## Dependencies

- [Positioning](../00-product/positioning.md)
- [MVP Scope](../00-product/mvp-scope.md)
- [Evidence Requirements](../03-rule-design/evidence-requirements.md)
- [Contamination Rules](../03-rule-design/contamination-rules.md)

## Future Considerations

Near-duplicate detection, embedding-based similarity, and model-assisted contamination checks may be added later as opt-in capabilities if they preserve deterministic reporting semantics.
