# Non-Goals

## Question

What must the MVP intentionally not do?

## Purpose

This document protects the MVP from scope drift. If a feature is listed here, an implementation agent must not add it unless another foundation document explicitly requires it.

## Non-Goals For The MVP

### Evaluation Execution

The MVP must not run model evaluations, benchmark suites, prompt sweeps, model comparisons, or regression tests.

Reason: EvalProof validates whether evaluation artifacts can be trusted. Evaluation frameworks already execute evaluations.

### Model Calls

The MVP must not call local or remote language models by default.

Reason: model calls add nondeterminism, cost, credentials, latency, provider drift, and offline failure modes.

### Prompt Optimization

The MVP must not rewrite prompts, suggest better wording, rank prompts, or judge style.

Reason: subjective prompt quality is outside the contamination wedge. Prompt checks are allowed only when they identify evidence-backed contamination or trust risks.

### Observability

The MVP must not collect traces, monitor production traffic, store spans, analyze latency, or build runtime dashboards.

Reason: observability tools operate after or during runtime. EvalProof is a preflight scanner.

### LLMOps Platform Features

The MVP must not manage deployments, model registries, experiment tracking, hosted datasets, approvals, human feedback, or production rollout state.

Reason: these features create platform scope unrelated to static evaluation trust.

### External Plugin Runtime

The MVP must not expose a third-party plugin marketplace or external plugin loading contract.

Reason: plugin APIs freeze early mistakes. Built-in rule groups may be internally organized as plugins, but external plugin support is deferred.

### SDK, MCP, VSCode, Hosted UI

The MVP must not include a Python SDK, MCP server, VSCode extension, hosted dashboard, browser UI, or service backend.

Reason: the CLI and JSON report are enough to prove the scanner.

### General Security Scanning

The MVP must not become a broad secret scanner, compliance scanner, vulnerability scanner, or red-team framework.

Reason: security checks belong only when they affect whether evaluation artifacts can be trusted.

### Broad Dataset Quality Scoring

The MVP must not score dataset diversity, representativeness, usefulness, fairness, or domain quality.

Reason: those judgments are contextual and usually subjective without domain-specific evidence.

## Design Decisions

- MVP scope is intentionally narrower than the long-term architecture.
- Static contamination and trust checks are in scope; dynamic evaluation and platform features are not.
- External plugin loading is deferred even though the architecture uses rule groups internally.
- Security checks are supporting checks, not a separate product pillar.

## Open Questions

None.

## Dependencies

- [Positioning](positioning.md)
- [MVP Scope](mvp-scope.md)
- [Design Principles](design-principles.md)

## Future Considerations

Deferred capabilities may be reconsidered after the MVP proves deterministic contamination findings on real repositories.
