# Positioning

## Question

What is LLM Doctor, and what is it not?

## Core Position

LLM Doctor is a local-first static preflight scanner for LLM evaluation artifacts.

It helps engineers decide whether evaluation artifacts are trustworthy before they rely on benchmark results, regression results, or deployment decisions.

LLM Doctor does not answer:

> How good is this model?

LLM Doctor answers:

> Can I trust the artifacts used to evaluate this model or LLM system?

## Primary Promise

> Before you trust an LLM evaluation, run LLM Doctor.

This promise defines the product boundary. Features that do not improve confidence in evaluation artifacts do not belong in the MVP.

## Primary Wedge

LLM Doctor should become known for one capability:

> Detecting LLM evaluation contamination.

Evaluation contamination means defects in evaluation artifacts that can make evaluation results misleading, invalid, non-reproducible, or unsafe to trust.

Examples include train/eval overlap, duplicate evaluation samples, answer leakage from RAG corpora, missing reproducibility metadata, prompt or dataset fingerprint mismatch, and unsafe prompt interpolation that compromises evaluation validity.

Security-related checks are included only when they affect evaluation trust. LLM Doctor is not a general-purpose security scanner.

## Product Category

LLM Doctor is an artifact trust scanner.

It sits before evaluation execution and before production observability:

1. A team prepares datasets, prompts, RAG corpora, and evaluation result files.
2. The team runs LLM Doctor.
3. LLM Doctor reports contamination and trust findings.
4. The team fixes artifact issues.
5. The team runs evaluation frameworks or trusts existing results.

LLM Doctor integrates with evaluation tools by improving the quality and trustworthiness of their inputs and outputs. It does not replace them.

## What LLM Doctor Is

LLM Doctor is:

- A static scanner.
- A local-first command-line tool.
- An offline-first trust checker.
- A rule engine that produces standardized findings.
- A preflight tool for evaluation artifacts.
- A CI-friendly artifact quality gate.
- A complement to evaluation frameworks and observability tools.

The system architecture is defined in [System Overview](../02-architecture/system-overview.md).

## What LLM Doctor Is Not

LLM Doctor is not an evaluation framework, benchmark runner, prompt engineering tool, observability platform, LLMOps platform, or generic security scanner.

MVP exclusions are defined in [Non-Goals](non-goals.md). The exact MVP boundary is defined in [MVP Scope](mvp-scope.md).

## Intended Users

The primary users are engineers responsible for evaluating LLM systems:

- ML engineers.
- AI engineers.
- Evaluation infrastructure engineers.
- Applied research engineers.
- RAG system owners.
- CI owners for LLM applications.

The MVP is not optimized for non-technical prompt authors, business users, or hosted no-code workflows.

## Product Voice

LLM Doctor must be direct, evidence-based, and conservative.

Findings should say what was detected, why it matters, and what action to take. Findings must not speculate beyond the evidence.

Good:

> 23 normalized records appear in both `data/train.jsonl` and `data/eval.jsonl`. This can inflate evaluation results because the model may have seen evaluation samples during training.

Bad:

> Your dataset quality is poor.

Finding requirements are defined in [Finding Model And Schema](../01-concepts/finding-model-and-schema.md) and [Evidence Requirements](../03-rule-design/evidence-requirements.md).

## Design Decisions

- LLM Doctor is positioned as an artifact trust scanner, not an evaluation framework.
- The primary wedge is evaluation contamination detection.
- The primary promise is: "Before you trust an LLM evaluation, run LLM Doctor."
- The MVP must remain static, local-first, offline-first, and CI-friendly.
- Security-related checks are allowed only when they affect evaluation artifact trust.
- LLM Doctor complements existing evaluation and observability tools instead of replacing them.
- Findings must be evidence-based and avoid subjective quality judgments.

## Open Questions

None.

## Dependencies

- [Non-Goals](non-goals.md)
- [MVP Scope](mvp-scope.md)
- [Design Principles](design-principles.md)
- [Evaluation Contamination](../01-concepts/evaluation-contamination.md)
- [Finding Model And Schema](../01-concepts/finding-model-and-schema.md)
- [System Overview](../02-architecture/system-overview.md)
- [Evidence Requirements](../03-rule-design/evidence-requirements.md)

## Future Considerations

Future versions may add dynamic checks, integrations, hosted workflows, SDKs, MCP support, or editor integrations only if they preserve the primary positioning.
