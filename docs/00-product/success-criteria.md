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

This original MVP target is aspirational and has not been demonstrated with
similarity enabled. It is not the release qualification gate for later
milestones; the approved [roadmap](../../ROADMAP.md#v127-release-qualification)
requires measured scale checks without a hardware-independent time guarantee.
Do not advertise the 60-second target as measured performance.

## Release Qualification Evidence

The recorded calibration used package 0.6.0 and 29 rules. Its
[GitHub Actions run](https://github.com/mertsparlak/EvalProof/actions/runs/33404984003)
passed all seven jobs on Linux for commit 9ee7f71, including the four Python
versions, optional Parquet, installed-wheel checks and 100k-row smoke.
The subsequent version-only 1.0.0 transition passed the full 455-test optional
suite and clean base/extra wheel smoke locally. These are qualification records,
not a claim that the package has been published or that main was merged.

- The accuracy manifest now requires a positive, negative and no-artifact
  abstention case for every registered rule. The shared negative fixture contains
  training/evaluation rows, a RAG corpus, a delimited prompt, valid result metrics,
  sample IDs, schema and provenance contracts, with similarity enabled. It must
  produce no findings or diagnostics with all rules active.
- No-artifact abstention only checks the absence-of-scope boundary. Rule-specific
  ambiguity, partial-data and malformed-input tests remain necessary; the empty
  case does not substitute for those tests.
- Full local suites passed on Python 3.11.15, 3.12.13, 3.13.13 and 3.14 without
  PyArrow: 423 passed, 2 skipped in each environment. Python 3.14 with PyArrow
  25.0.1 passed 455 tests, with 1 skipped. The normal suite deliberately skips the
  100k-row job; base installations also skip optional Parquet tests.
- Fresh non-editable 0.6.0 wheel installations passed base and optional-Parquet
  CLI/scan/profile smoke from outside the checkout. The package version, runtime
  version and report version agree.
- The explicit 100k-row generated scan/profile test passed locally: approximately
  170 seconds for the similarity-enabled scan and 5 seconds for profiling.
  Its pseudo-random texts exercise scale, not near-duplicate precision or recall.
- The user's local dataset_v2 check indexed 55,015 rows with all 29 rules active:
  47 findings, no diagnostics, exit 1. Two runs took approximately 374 and 365
  seconds. Source hashes, including the existing report, were unchanged. Reports
  were written outside the dataset directory. Findings and summary stayed equal
  across the config-role correction; artifact metadata intentionally changed.
- A full-field privacy check compared 238,205 source strings of at least 32
  characters against report string values without finding an exposed field.
  This is narrower than proving absence of every possible substring leak.
  Dedicated regressions cover short IDs, secrets, interpolation excerpts and
  parser exception content.

### Public Dataset Calibration

The [recorded receipt](../../tests/fixtures/accuracy_audit/public_calibration_receipt.json)
contains API response hashes, source-order ranges, explicit field mappings,
materialized-file hashes, scanner-source identity and normalized report hashes.
No raw public or user dataset rows are committed.

| Dataset | Observed Rows | Findings |
| --- | ---: | ---: |
| deepset/prompt-injections | 616 | 3 |
| lmsys/toxic-chat | 1,000 | 20 |
| xTRam1/safe-guard-prompt-injection | 1,000 | 10 |
| nvidia/Aegis-AI-Content-Safety-Dataset-2.0 | 1,000 | 2 |
| openai/gsm8k | 1,000 | 1 |
| rajpurkar/squad | 1,000 | 2 |
| truthfulqa/truthful_qa | 817 | 1 |
| BeIR/fiqa | 1,000 | 2 |
| BeIR/nfcorpus | 1,000 | 1 |
| BeIR/scifact | 1,000 | 1 |

All 9,433 sampled rows were scanned without diagnostics. Both scan and profile
reports were identical after removing timestamps on two offline replays.
The seven confirmed findings were independently checked against decoded source
records, without using detector hashes as the truth oracle: one train/eval exact
overlap, five within-split exact duplicates, and one repeated RAG text field.
The RAG check confirms repeated text, not identical document metadata or a mandate
to delete a document. No confirmed false positive remains in this reviewed sample.

The remaining findings are likely lexical similarities or heuristic pattern
matches; this exercise does not certify their semantic precision. Prefix sampling
is not representative sampling, and no precision/recall estimate is claimed.
Result/provenance contracts are covered synthetically here, not by pretending
these public datasets contain evaluation-run metadata. BeIR query/corpus prefixes
have no qrels-derived reference links, so they do not calibrate unreachable-ID
absence claims. SQuAD contexts and answer collections remain intact.

The opt-in [calibration harness](../../tests/release_public_calibration.py) can be
run from the checkout using an output directory outside the repository:

```text
python tests/release_public_calibration.py <external-output-directory> --fetch
python tests/release_public_calibration.py <same-external-output-directory>
```

Only `--fetch` permits network access on a cache miss. Replay verifies cached
response hashes and refuses missing or modified responses. The receipt identifies
observed Dataset Viewer responses, not an immutable Hub commit: exact historical
replay requires keeping that external cache. Fetching later may return changed
data and must produce a new calibration record. The product scanner remains
offline and does not import this harness.

### Review Coverage

The author reviewed changed role detection, fixtures, calibration mappings,
cache integrity, report isolation, CI configuration and test assertions.
No independent model-review result is claimed.
Code review: skipped (ce-code-review unavailable). This environment exposes no
reviewer subagent dispatch; a manual diff review and local tests were used instead.

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
