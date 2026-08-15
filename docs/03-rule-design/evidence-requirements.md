# Evidence Requirements

## Question

What evidence is required before a rule may emit a finding?

## Core Requirement

No rule may emit a finding without evidence.

Evidence must be concrete enough for a user to understand what was detected, verify the issue, and decide what to change.

## Evidence Must Include

Every finding must include evidence that identifies:

- the artifact or artifacts involved
- the relevant row, line, field, hash, or snippet when available
- the comparison or condition that triggered the finding
- the reason the evidence affects evaluation trust

## Evidence Must Not Include

Evidence must not include:

- speculation
- generic best-practice advice
- raw secrets
- excessive copied user data
- model-generated judgments
- hidden scanner internals that users cannot verify

If a rule detects secret-like or PII-like content, evidence should include redacted values or stable hashes, not the full sensitive value.

## Confidence Mapping

Use `confirmed` when deterministic evidence directly proves the issue.

Use `likely` when deterministic evidence strongly indicates the issue but depends on artifact roles or metadata.

Use `heuristic` only when the evidence is pattern-based and may need user review.

Confidence values are defined in [Finding Model And Schema](../01-concepts/finding-model-and-schema.md).

## Actionability

Every finding must include a recommendation that names a concrete next action.

Good:

> Remove overlapping rows from the evaluation dataset or move them to the training split, then regenerate the dataset fingerprint.

Bad:

> Improve your data quality.

## Rule Validation Coverage

Every built-in rule must have test coverage for:

- at least one positive artifact that should emit the rule
- at least one negative boundary artifact that should not emit the rule
- an abstention or ambiguity artifact for confirmed rules when applicability evidence is absent or intent is not objectively knowable

The coverage tests must assert the standardized finding fields, rule-specific evidence presence, confidence class, deterministic fingerprints, and sensitive-value redaction. This is a test requirement for maintaining the rule set; it does not add runtime report fields or change the finding schema.

## Design Decisions

- Evidence is mandatory for every finding.
- Redaction is required for sensitive evidence.
- The MVP should prefer confirmed and likely findings over heuristic findings.
- Recommendations must be concrete and tied to the finding.

## Open Questions

None.

## Dependencies

- [Design Principles](../00-product/design-principles.md)
- [Finding Model And Schema](../01-concepts/finding-model-and-schema.md)
- [Contamination Rules](contamination-rules.md)

## Future Considerations

Future model-assisted rules must still provide user-verifiable evidence and must clearly mark confidence.
