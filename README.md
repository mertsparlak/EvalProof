# EvalProof

EvalProof is a local-first static preflight scanner for LLM evaluation artifacts.

Primary promise:

> Before you trust an LLM evaluation, run EvalProof.

This repository currently contains the frozen MVP foundation documentation. It is intended to be sufficient for another coding agent to implement the MVP without making architectural decisions.

## Read First

1. [Positioning](docs/00-product/positioning.md)
2. [Non-Goals](docs/00-product/non-goals.md)
3. [Design Principles](docs/00-product/design-principles.md)
4. [MVP Scope](docs/00-product/mvp-scope.md)
5. [Success Criteria](docs/00-product/success-criteria.md)

## Core Concepts

- [Evaluation Contamination](docs/01-concepts/evaluation-contamination.md)
- [Finding Model And Schema](docs/01-concepts/finding-model-and-schema.md)
- [Artifact Model And Interface](docs/01-concepts/artifact-model-and-interface.md)

## Architecture

- [System Overview](docs/02-architecture/system-overview.md)
- [Scan Pipeline](docs/02-architecture/scan-pipeline.md)
- [Project Index](docs/02-architecture/project-index.md)
- [Rule Engine](docs/02-architecture/rule-engine.md)
- [Configuration And Schema](docs/02-architecture/configuration-and-schema.md)

## Rule Design

- [Evidence Requirements](docs/03-rule-design/evidence-requirements.md)
- [Contamination Rules](docs/03-rule-design/contamination-rules.md)

## CLI And Reports

- [CLI Contract And Exit Codes](docs/05-cli-and-reports/cli-contract-and-exit-codes.md)
- [JSON Report](docs/05-cli-and-reports/json-report.md)

## Implementation Boundary

The MVP is not an evaluation framework, benchmark runner, prompt engineering tool, observability platform, LLMOps platform, or generic security scanner.

The MVP is a static rule-driven scanner that detects evidence-backed contamination and trust issues in LLM evaluation artifacts.

## Documentation Status

The MVP documentation structure is frozen. Do not add new foundation documents, modules, features, or scope unless a critical architectural flaw is found.
