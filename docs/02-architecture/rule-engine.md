# Rule Engine

## Question

How are rules defined, registered, and executed?

## Rule Model

A rule is a deterministic check that inspects scan context and emits zero or more findings.

Rules must be project-scoped. A rule may inspect one artifact, but the interface must allow rules to compare multiple artifacts through the project index.

## Required Rule Metadata

Every rule must define:

- `id`
- `title`
- `default_severity`
- `description`
- `artifact_roles`
- `tags`

Rule ids must be stable and namespaced by rule family, such as `contamination.train_eval_overlap`.

## Execution Context

Rules receive a context containing:

- scan root
- loaded configuration
- artifacts
- project index
- deterministic cache access if needed

Rules must not receive CLI arguments or reporter instances.

## Rule Registration

The MVP registers built-in rule groups during scan startup.

Internal rule groups may be organized like plugins, but external plugin loading is outside MVP.

## Rule Output

Rules emit findings matching [Finding Model And Schema](../01-concepts/finding-model-and-schema.md).

Rules must not print output, set process exit codes, or write report files.

## Determinism

Rules must produce the same findings for the same inputs and configuration.

Rules must not depend on:

- file traversal order
- wall-clock time
- random numbers
- network state
- model output
- absolute machine-specific paths

## Design Decisions

- Rules are project-scoped to support contamination checks across artifacts.
- Rule ids are stable because they appear in reports, configuration, and future suppressions.
- External plugin loading is deferred.
- Rules emit findings only; all rendering and exit-code behavior stays outside rules.

## Open Questions

None.

## Dependencies

- [Finding Model And Schema](../01-concepts/finding-model-and-schema.md)
- [Project Index](project-index.md)
- [Evidence Requirements](../03-rule-design/evidence-requirements.md)
- [Contamination Rules](../03-rule-design/contamination-rules.md)

## Future Considerations

Future external plugin support must use this rule model rather than introducing analyzer-specific contracts.
