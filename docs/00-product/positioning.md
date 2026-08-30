# Positioning

## Question

What is EvalProof, and what is it not?

## Core Position

EvalProof is a local-first static preflight scanner for LLM datasets and evaluation artifacts.

It helps engineers decide whether training datasets and evaluation artifacts satisfy explicit, verifiable trust contracts before they start training or rely on benchmark, regression, or deployment decisions.

EvalProof does not answer:

> How good is this model?

EvalProof answers:

> Can I trust the dataset and evaluation artifacts used to train or evaluate this model or LLM system?

## Primary Promise

> Before you trust an LLM evaluation, run EvalProof.

This promise defines the product boundary. Training-dataset checks belong only when they establish an objective preflight fact, such as contamination, duplicate identity, malformed structure, or violation of an explicit contract. Subjective dataset scoring remains outside the product boundary.

## Primary Wedge

EvalProof should become known for one capability:

> Detecting LLM evaluation contamination.

Evaluation contamination means defects in evaluation artifacts that can make evaluation results misleading, invalid, non-reproducible, or unsafe to trust.

Examples include train/eval overlap, duplicate evaluation samples, answer leakage from RAG corpora, missing reproducibility metadata, prompt or dataset fingerprint mismatch, and unsafe prompt interpolation that compromises evaluation validity.

Security-related checks are included only when they affect evaluation trust. EvalProof is not a general-purpose security scanner.

## Product Category

EvalProof is a dataset and evaluation artifact trust scanner.

It sits before evaluation execution and before production observability:

1. A team prepares training or evaluation datasets, prompts, RAG corpora, and evaluation result files.
2. The team runs EvalProof.
3. EvalProof reports contamination and trust findings.
4. The team fixes artifact issues.
5. The team runs evaluation frameworks or trusts existing results.

EvalProof integrates with evaluation tools by improving the quality and trustworthiness of their inputs and outputs. It does not replace them.

## What EvalProof Is

EvalProof is:

- A static scanner.
- A local-first command-line tool.
- An offline-first trust checker.
- A rule engine that produces standardized findings.
- A preflight tool for training datasets and evaluation artifacts.
- A CI-friendly artifact quality gate.
- A complement to evaluation frameworks and observability tools.

The system architecture is defined in [System Overview](../02-architecture/system-overview.md).

## What EvalProof Is Not

EvalProof is not an evaluation framework, benchmark runner, prompt engineering tool, observability platform, LLMOps platform, or generic security scanner.

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

EvalProof must be direct, evidence-based, and conservative.

Findings should say what was detected, why it matters, and what action to take. Findings must not speculate beyond the evidence.

Good:

> 23 normalized records appear in both `data/train.jsonl` and `data/eval.jsonl`. This can inflate evaluation results because the model may have seen evaluation samples during training.

Bad:

> Your dataset quality is poor.

Finding requirements are defined in [Finding Model And Schema](../01-concepts/finding-model-and-schema.md) and [Evidence Requirements](../03-rule-design/evidence-requirements.md).

## Design Decisions

- EvalProof is positioned as an artifact trust scanner, not an evaluation framework.
- The primary wedge remains evaluation contamination detection; explicit training-dataset contracts extend the same evidence-first trust model without creating a general dataset quality product.
- The primary promise is: "Before you trust an LLM evaluation, run EvalProof."
- The MVP must remain static, local-first, offline-first, and CI-friendly.
- Security-related checks are allowed only when they affect evaluation artifact trust.
- EvalProof complements existing evaluation and observability tools instead of replacing them.
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
