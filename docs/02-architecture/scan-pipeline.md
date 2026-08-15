# Scan Pipeline

## Question

In what order does a scan execute?

## Pipeline Order

An MVP scan must execute in this order:

1. Parse CLI arguments.
2. Load configuration.
3. Discover candidate files.
4. Detect artifacts and roles.
5. Build the project index.
6. Register MVP rules.
7. Execute enabled rules.
8. Apply severity overrides.
9. Collect findings and scan diagnostics.
10. Build deterministic artifact coverage metadata.
11. Sort findings deterministically.
12. Render reports.
13. Return exit code.

## Discovery

Discovery identifies candidate files under the scan root using include and exclude rules from [Configuration And Schema](configuration-and-schema.md).

Discovery must be deterministic. File traversal order must not affect final findings or report ordering.

## Artifact Detection

Candidate files become artifacts through format and role detection described in [Artifact Model And Interface](../01-concepts/artifact-model-and-interface.md).

Detection must preserve malformed artifact information when possible.

## Indexing

The project index is built after artifact detection and before rule execution.

Indexing provides shared cross-artifact data needed by contamination rules. Its responsibilities are defined in [Project Index](project-index.md).

Indexing also records artifact coverage status, row counts, fingerprints, role source, and artifact-scoped diagnostics for the JSON report.

## Rule Execution

Rules execute against a scan context containing configuration, artifacts, project index, and deterministic cache access.

Rule execution order must not affect final findings.

## Finding Ordering

Reports must receive findings sorted deterministically by:

1. severity rank
2. rule id
3. primary artifact path
4. primary location
5. fingerprint

## Failure Handling

A single malformed file or rule-level recoverable error must not crash the full scan.

Fatal errors are limited to invalid CLI usage, unreadable scan root, invalid configuration, or failure to write requested output.

## Design Decisions

- Configuration is loaded before discovery so include/exclude and role overrides affect the scan.
- Project index construction happens before rules so cross-artifact rules do not duplicate indexing logic.
- Reports are rendered only after all findings are collected and sorted.
- Rule order must not affect output.

## Open Questions

None.

## Dependencies

- [Configuration And Schema](configuration-and-schema.md)
- [Artifact Model And Interface](../01-concepts/artifact-model-and-interface.md)
- [Project Index](project-index.md)
- [Rule Engine](rule-engine.md)
- [CLI Contract And Exit Codes](../05-cli-and-reports/cli-contract-and-exit-codes.md)

## Future Considerations

Future parallel rule execution must preserve deterministic findings and report ordering.
