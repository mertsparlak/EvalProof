# MVP Scope

## Question

What exactly is included in the MVP?

## MVP Definition

The MVP is a local CLI scanner that detects evidence-backed contamination and trust issues in LLM evaluation artifacts and produces deterministic findings as terminal and JSON reports.

The MVP command is defined in [CLI Contract And Exit Codes](../05-cli-and-reports/cli-contract-and-exit-codes.md).

## Included Artifact Types

The MVP supports files commonly used for evaluation artifacts:

- JSON
- JSONL
- CSV
- YAML
- TOML
- Markdown
- plain text

The artifact model is defined in [Artifact Model And Interface](../01-concepts/artifact-model-and-interface.md).

## Included Artifact Roles

The MVP recognizes these roles:

- Training dataset.
- Evaluation dataset.
- Benchmark dataset.
- Evaluation result.
- Prompt template.
- RAG corpus document.
- Configuration file.

Role detection may use filename and directory heuristics, but configuration overrides must be supported.

## Included Rule Families

The MVP includes only contamination-focused and trustworthiness-critical rules:

- Train/eval contamination.
- Duplicate evaluation samples.
- RAG answer leakage.
- Missing reproducibility metadata.
- Prompt or dataset fingerprint mismatch where evidence exists.
- Unsafe prompt interpolation that affects evaluation validity.
- Secret-like or PII-like exposure in evaluation artifacts when it affects artifact trust.

Exact MVP rules are defined in [Contamination Rules](../03-rule-design/contamination-rules.md).

## Included Outputs

The MVP must produce:

- A human-readable terminal summary.
- Deterministic findings in a JSON report.
- Deterministic exit codes suitable for CI.

The JSON contract is defined in [JSON Report](../05-cli-and-reports/json-report.md).

## Excluded Scope

Excluded scope is defined in [Non-Goals](non-goals.md). This document does not repeat those exclusions.

## Design Decisions

- The MVP is a CLI-first scanner.
- JSON output is required because it is the machine-readable contract for CI and future integrations.
- SARIF is not required for the MVP.
- External plugins are not required for the MVP.
- The MVP includes security-sensitive checks only when they directly affect evaluation artifact trust.

## Open Questions

None.

## Dependencies

- [Positioning](positioning.md)
- [Non-Goals](non-goals.md)
- [Artifact Model And Interface](../01-concepts/artifact-model-and-interface.md)
- [Contamination Rules](../03-rule-design/contamination-rules.md)
- [CLI Contract And Exit Codes](../05-cli-and-reports/cli-contract-and-exit-codes.md)
- [JSON Report](../05-cli-and-reports/json-report.md)

## Future Considerations

Future versions may add SARIF, baselines, suppressions, dynamic checks, or integrations after the MVP proves the contamination scanner.
