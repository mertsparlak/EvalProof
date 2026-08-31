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
    "version": "0.6.0"
  },
  "scan": {
    "root": ".",
    "started_at": "2026-01-01T00:00:00Z",
    "completed_at": "2026-01-01T00:00:01Z",
    "config_path": "evalproof.yaml",
    "rules": {
      "mode": "selected",
      "ids": ["contamination.train_eval_overlap"]
    },
    "artifacts": [
      {
        "path": "data/eval.jsonl",
        "format": "jsonl",
        "roles": ["evaluation_dataset"],
        "role_source": "config",
        "index_status": "indexed",
        "index_reasons": ["complete"],
        "rows_indexed": 100,
        "rows_rejected": 0,
        "truncated": false,
        "fingerprint": "sha256:...",
        "diagnostic_codes": [],
        "role_matched_rule_ids": ["contamination.train_eval_overlap"]
      }
    ]
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

The `scan.rules` metadata records the actual rule scope of the scan:

- `mode` is `all` when no CLI allowlist was provided, or `selected` when `--rules` was used.
- `ids` is the deterministic, sorted list of rules that actually executed after configuration-disabled rules were removed.

The rule scope is additive report metadata. Existing top-level fields, finding objects, diagnostics, exit codes, and `schema_version` remain unchanged.

The `scan.artifacts` list is additive report metadata. It is sorted by relative POSIX path and records artifact coverage, role provenance, indexing status, and active role-matched rules. `role_matched_rule_ids` describes role applicability only; it does not claim that the rule emitted or would emit a finding.

Coverage values are defined by [Project Index](../02-architecture/project-index.md). The scanner must not report an artifact as fully indexed when file-size, parse, or row-limit behavior prevents complete indexing.

## Finding Objects

Each finding object must match [Finding Model And Schema](../01-concepts/finding-model-and-schema.md).

Rule-specific evidence may aggregate many underlying matches to keep reports usable. Such evidence must preserve complete match counts, use deterministic bounded samples, and set `evidence_truncated: true` when related evidence is omitted. This is an additive rule-evidence convention and does not change the top-level JSON schema or finding object shape.

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

Parser diagnostics must not copy parser exception messages or source-line excerpts
into message/details. They retain the artifact path, available row location and
format/code; JSONL details.error is the exception class name only. This protects
both scan and profile reports from parser errors that quote sensitive source data.

MVP diagnostic codes:

- `artifact.parse_failed`
- `artifact.invalid_text_encoding`
- `artifact.provenance_source_unreadable`
- `artifact.optional_dependency_missing`
- `artifact.unsupported_parquet_schema`

- `artifact.row_parse_failed`
- `artifact.row_limit_reached`
- `artifact.file_size_limit_exceeded`
- `artifact.unsupported_extension`
- `config.invalid`
- `rule.recoverable_error`
- `artifact.role_conflict`

The optional Parquet diagnostics are warnings and indicate scanner limitations,
not corrupt records. Coverage is `skipped` with `optional_dependency_missing` or
`unsupported_parquet_schema` in `index_reasons`; no complete fingerprint is
invented. [Project Index](../02-architecture/project-index.md#optional-parquet-records)
owns reader behavior. These codes do not change the report schema version.

## Determinism

For unchanged inputs and configuration:

- finding order must be stable
- finding fingerprints must be stable
- summary counts must be stable
- diagnostic ordering must be stable when diagnostics are based on scanned files
- active rule mode and active rule IDs must be stable

Report metadata timestamps may differ between runs. The deterministic JSON contract applies to findings, diagnostics, summary counts, ordering, and schema shape, excluding optional scan timing metadata.

## Paths

Paths in JSON reports must be relative to the scan root.

Absolute paths must not appear in findings, diagnostics, or fingerprints.

## Profile Report

The separate profile envelope has exactly these top-level fields:

- `schema_version`: "1.0", independently versioned from scan.
- `report_type`: "profile", required to distinguish this report family.
- `tool`: name "evalproof" and runtime package version.
- `profile`: object with root ".", started_at, completed_at (UTC ISO-8601),
  config_path (relative or null), and artifacts (dataset-only index coverage).
- `summary`: artifacts_profiled and measurements_total, both nonnegative integers.
- `measurements`: Measurement objects defined in
  [Measurement Contract](../01-concepts/finding-model-and-schema.md#measurement-contract).
- `diagnostics`: existing Diagnostic objects, never findings or measurements.

The `profile.artifacts` entries use the scan coverage shape except that
`role_matched_rule_ids` is omitted because rules do not run. Order is path ascending.
Measurements sort by artifact_path, measurement_id, canonical scope JSON and
fingerprint. Diagnostics use the existing deterministic diagnostic ordering.
No severity summary, findings array, rule scope or CI status appears in profile.
Root-relative paths and evidence privacy requirements apply equally to profiles.

v1.25 established this envelope without calculators. From v1.26, measurements
contain the approved calculations owned by
[Project Index](../02-architecture/project-index.md#dataset-measurement-calculations).
An empty measurements list must never be described as passing quality checks.
Excluding profile started_at/completed_at, identical inputs/configuration and
calculation methods must produce identical reports. The scan envelope remains
unchanged, without report_type or measurements additions.

## Design Decisions

- JSON is the required MVP machine-readable report format.
- Findings use the same schema across reports.
- High-volume rule evidence is aggregated and bounded without hiding complete match counts.
- Diagnostics are separate from findings.
- Timestamps are allowed only as report metadata.
- Relative paths are required.
- Deterministic JSON excludes optional scan timing metadata.
- Active rule scope is recorded so an empty selected scan cannot be mistaken for a full clean scan.
- Artifact coverage is recorded so a clean result can be distinguished from an incomplete or ambiguously classified scan.

## Open Questions

None.

## Dependencies

- [Finding Model And Schema](../01-concepts/finding-model-and-schema.md)
- [CLI Contract And Exit Codes](cli-contract-and-exit-codes.md)
- [Scan Pipeline](../02-architecture/scan-pipeline.md)

## Future Considerations

Future report formats must not redefine the finding schema. SARIF can be added as a rendering of the same findings.
