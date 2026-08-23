# JSON Report

## Question

What machine-readable report must the MVP produce?

## Purpose

The JSON report is the MVP machine-readable contract for CI and future integrations.

Terminal output is for humans. JSON output is for tools.

## Top-Level Schema

```json
{
  "schema_version": "1.0",
  "tool": {
    "name": "evalproof",
    "version": "0.0.0"
  },
  "scan": {
    "root": ".",
    "started_at": "2026-01-01T00:00:00Z",
    "completed_at": "2026-01-01T00:00:01Z",
    "config_path": "evalproof.yaml"
  },
  "summary": {
    "artifacts_scanned": 0,
    "findings_total": 0,
    "findings_by_severity": {
      "critical": 0,
      "high": 0,
      "medium": 0,
      "low": 0
    }
  },
  "findings": [],
  "diagnostics": []
}
```

Timestamps are optional report metadata. They may differ between runs and must not be used in finding fingerprints.

## Finding Objects

Each finding object must match [Finding Model And Schema](../01-concepts/finding-model-and-schema.md).

Minimum JSON shape:

```json
{
  "rule_id": "contamination.train_eval_overlap",
  "severity": "critical",
  "confidence": "confirmed",
  "title": "Train/eval overlap detected",
  "message": "A normalized record appears in both training and evaluation artifacts.",
  "impact": "Evaluation results may be inflated because the model may have seen evaluation samples during training.",
  "recommendation": "Remove overlapping records from one split and regenerate dataset fingerprints.",
  "locations": [
    {
      "role": "source",
      "path": "data/train.jsonl",
      "row": 12
    },
    {
      "role": "target",
      "path": "data/eval.jsonl",
      "row": 4
    }
  ],
  "evidence": {
    "normalized_record_hash": "sha256:..."
  },
  "fingerprint": "sha256:..."
}
```

## Diagnostics

Diagnostics describe scan-level issues that are not rule findings, such as skipped files or parse failures.

Diagnostics must not be counted as findings unless emitted by a rule as a finding.

Diagnostic severities:

- `info`
- `warning`
- `error`

Minimum diagnostic object shape:

```json
{
  "severity": "warning",
  "code": "artifact.parse_failed",
  "message": "Artifact could not be parsed as JSONL.",
  "path": "data/eval.jsonl",
  "details": {
    "format": "jsonl"
  }
}
```

Required diagnostic fields:

- `severity`
- `code`
- `message`

Optional diagnostic fields:

- `path`
- `line`
- `row`
- `details`

MVP diagnostic codes:

- `artifact.parse_failed`
- `artifact.row_parse_failed`
- `artifact.row_limit_reached`
- `artifact.file_size_limit_exceeded`
- `artifact.unsupported_extension`
- `config.invalid`
- `rule.recoverable_error`

## Determinism

For unchanged inputs and configuration:

- finding order must be stable
- finding fingerprints must be stable
- summary counts must be stable
- diagnostic ordering must be stable when diagnostics are based on scanned files

Report metadata timestamps may differ between runs. The deterministic JSON contract applies to findings, diagnostics, summary counts, ordering, and schema shape, excluding optional scan timing metadata.

## Paths

Paths in JSON reports must be relative to the scan root.

Absolute paths must not appear in findings, diagnostics, or fingerprints.

## Design Decisions

- JSON is the required MVP machine-readable report format.
- Findings use the same schema across reports.
- Diagnostics are separate from findings.
- Timestamps are allowed only as report metadata.
- Relative paths are required.
- Deterministic JSON excludes optional scan timing metadata.

## Open Questions

None.

## Dependencies

- [Finding Model And Schema](../01-concepts/finding-model-and-schema.md)
- [CLI Contract And Exit Codes](cli-contract-and-exit-codes.md)
- [Scan Pipeline](../02-architecture/scan-pipeline.md)

## Future Considerations

Future report formats must not redefine the finding schema. SARIF can be added as a rendering of the same findings.
