# MVP Success Criteria

## Question

How do we know the MVP is complete and good enough?

## Completion Criteria

The MVP is complete when it can:

- Detect train/eval contamination.
- Detect duplicated evaluation samples.
- Detect missing reproducibility metadata.
- Detect at least one RAG answer leakage pattern.
- Produce deterministic findings for unchanged inputs.
- Produce JSON reports matching the MVP JSON contract.
- Run fully offline.
- Run without model inference.
- Be integrated into CI using exit codes and JSON output.
- Complete scans on medium-sized repositories within an acceptable time.

## Quality Criteria

The MVP is good enough when:

- Every finding includes evidence, impact, and recommendation.
- Findings are stable across repeated scans of the same files.
- Rule output does not depend on file traversal order.
- A scan can finish even when some files are malformed.
- Malformed files produce diagnostics instead of uncaught failures.
- The scanner avoids subjective findings.
- The scanner produces fewer, higher-confidence findings rather than broad noisy output.

## Performance Target

A medium-sized repository means a repository with:

- Up to 10,000 local files.
- Up to 1 GB of scanned text and structured artifacts.
- Up to 250,000 dataset rows across supported text-based datasets.

The MVP should complete a scan of such a repository in under 60 seconds on a typical developer laptop, excluding unusually large files that are skipped by configured or default limits.

This target is a product success criterion, not a promise that every rule must read every byte of every file.

## Design Decisions

- MVP success is measured by trust-relevant detections, not number of rules.
- Determinism, offline execution, and CI compatibility are required.
- Performance expectations are defined at repository scale, not single-file scale.
- Malformed files must not crash the full scan.

## Open Questions

None.

## Dependencies

- [MVP Scope](mvp-scope.md)
- [Finding Model And Schema](../01-concepts/finding-model-and-schema.md)
- [Evidence Requirements](../03-rule-design/evidence-requirements.md)
- [JSON Report](../05-cli-and-reports/json-report.md)
- [CLI Contract And Exit Codes](../05-cli-and-reports/cli-contract-and-exit-codes.md)

## Future Considerations

Future versions may define stricter performance tiers for very large monorepos and binary-heavy repositories.
