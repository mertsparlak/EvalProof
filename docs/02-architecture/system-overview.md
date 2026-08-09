# System Overview

## Question

What are the major system parts and boundaries?

## Architecture

LLM Doctor uses this pipeline:

```text
Files
-> Artifacts
-> Project Index
-> Rules
-> Findings
-> Reports
```

The architecture is rule-engine based. The product identity is not. The product identity remains evaluation artifact trust scanning as defined in [Positioning](../00-product/positioning.md).

## Core Responsibilities

Core owns:

- File discovery.
- Artifact model.
- Project index.
- Rule execution.
- Finding schema.
- Reporting pipeline.
- Configuration.
- Severity policy.
- Exit codes.

## MVP Implementation Runtime

The MVP implementation runtime is Python 3.11 or newer.

The MVP uses the Python standard library plus `PyYAML` for `.yaml` and `.yml` files. It must not require network access at scan time.

This runtime decision exists to eliminate implementation ambiguity. It does not create a Python SDK, which is outside MVP scope.

## MVP Rule Group Responsibilities

The MVP has one built-in contamination rule group. That group owns the rule subcategories defined in [Contamination Rules](../03-rule-design/contamination-rules.md):

- split and benchmark contamination
- duplicate evaluation samples
- RAG answer leakage
- reproducibility metadata gaps
- fingerprint mismatch
- evaluation-scoped prompt interpolation risk
- evaluation-scoped sensitive value exposure

External plugin loading is outside MVP. Internal rule groups may follow plugin-like boundaries, but the external plugin contract is not frozen.

## Boundary Rules

Rules generate findings.

Reports render findings.

Core controls execution order, configuration, severity overrides, and exit-code behavior.

Rules must not directly control reporters, parse CLI arguments, or walk files.

Reporters must not create findings or apply rule logic.

## Design Decisions

- The system is organized around standardized findings.
- Core centralizes contracts that must remain consistent across rules and reports.
- Rule groups are modular internally without exposing an external plugin API in the MVP.
- The project index is a first-class architecture component because contamination is often cross-artifact.

## Open Questions

None.

## Dependencies

- [Positioning](../00-product/positioning.md)
- [Artifact Model And Interface](../01-concepts/artifact-model-and-interface.md)
- [Finding Model And Schema](../01-concepts/finding-model-and-schema.md)
- [Scan Pipeline](scan-pipeline.md)
- [Project Index](project-index.md)
- [Rule Engine](rule-engine.md)

## Future Considerations

External plugin loading can be added only after the internal rule interface proves stable.
