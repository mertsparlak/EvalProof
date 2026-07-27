# Design Principles

## Question

What principles constrain every MVP design decision?

## Principles

### Evidence Over Opinions

Every finding must be backed by concrete evidence. EvalProof must not emit subjective quality judgments.

### Prefer False Negatives Over False Positives

The MVP should miss some issues rather than produce noisy findings engineers learn to ignore.

### Local-First

The scanner must run against local files without requiring an account, service, API key, or network connection.

### Offline-First

The MVP must produce useful results when fully offline.

### No Model Inference In MVP

The MVP must not require LLM calls. Rules must be deterministic static analysis checks.

### Trust Over Feature Count

A small set of high-confidence findings is better than broad coverage with weak evidence.

### One Rule Solves One Problem

Each rule should detect one clearly described failure mode and produce one type of finding.

### Findings Are The Product

Rules, plugins, and reports exist to produce and communicate standardized findings. The finding contract is the most important interface.

### Reports Render; Rules Decide

Reports must only render findings. Reporters must not apply rule logic, severity logic, suppression logic, or baseline logic.

### Simplicity Beats Completeness

The MVP should choose the simplest design that supports contamination detection, deterministic reports, and CI integration.

## Design Decisions

- The MVP optimizes for trustworthiness of findings, not breadth of checks.
- Static analysis is mandatory for MVP rules.
- No rule may emit a finding without evidence.
- The finding schema is the central cross-system contract.
- Simplicity is preferred when a more complete design would not improve evaluation trust.

## Open Questions

None.

## Dependencies

- [Positioning](positioning.md)
- [Non-Goals](non-goals.md)
- [Finding Model And Schema](../01-concepts/finding-model-and-schema.md)
- [Evidence Requirements](../03-rule-design/evidence-requirements.md)

## Future Considerations

Future dynamic checks must remain opt-in and must not weaken the default local/offline behavior.
