# Configuration And Schema

## Question

How does MVP configuration work?

## Configuration File

The MVP configuration file is `evalproof.yaml` at the scan root unless the CLI specifies another path.

Configuration is optional. Defaults must allow `evalproof scan .` to run without setup.

## Supported Configuration

The MVP supports:

- include patterns
- exclude patterns
- artifact role overrides
- optional schema contracts for explicitly configured dataset artifacts
- disabled rules
- severity overrides
- minimum failing severity
- scan limits
- similarity settings for near-duplicate rules

No other configuration is required for MVP.

## Schema

```yaml
include:
  - "**/*"
exclude:
  - ".git/**"
  - "node_modules/**"
  - ".venv/**"

artifacts:
  - path: "data/train.jsonl"
    roles: ["training_dataset"]
    schema:
      required: ["messages"]
      fields:
        messages:
          type: array
          nullable: false
        sample_id:
          type: string
          nullable: true
  - path: "data/eval.jsonl"
    roles: ["evaluation_dataset"]

rules:
  disabled:
    - "contamination.rag_answer_leakage"
  severity:
    contamination.train_eval_overlap: critical

ci:
  fail_on: high

limits:
  max_file_mb: 100
  max_rows_per_artifact: 250000

similarity:
  enabled: true
  shingle_size: 3
  num_hashes: 64
  bands: 16
  threshold: 0.85
  focus_roles:
    - user
  focus_fields:
    - prompt
    - input
    - query
    - user
    - user_message
```

Top-level keys outside `include`, `exclude`, `artifacts`, `rules`, `ci`, `limits`, and `similarity` are invalid.

Schema field types:

- `include`: list of strings
- `exclude`: list of strings
- `artifacts`: list of objects with `path` string, `roles` list of artifact role strings, and optional `schema` object
- `rules.disabled`: list of rule id strings
- `rules.severity`: object mapping rule id strings to severity strings
- `ci.fail_on`: severity string
- `limits.max_file_mb`: positive integer
- `limits.max_rows_per_artifact`: positive integer
- `similarity.enabled`: boolean
- `similarity.shingle_size`: positive integer
- `similarity.num_hashes`: positive integer
- `similarity.bands`: positive integer
- `similarity.threshold`: number between `0.0` and `1.0`
- `similarity.focus_roles`: list of strings
- `similarity.focus_fields`: list of strings

Allowed severity strings are `critical`, `high`, `medium`, and `low`.

Invalid role strings, invalid severity strings, invalid rule ids for MVP rules, and wrong field types make the configuration invalid.

## Explicit Dataset Schema Contracts

`artifacts[].schema` declares the record structure the user expects for one exact dataset artifact. It is opt-in: EvalProof does not infer a schema and does not apply this contract to artifacts without `schema`.

A schema-bearing artifact must satisfy all of these conditions:

- `roles` is non-empty and contains only `training_dataset`, `evaluation_dataset`, or `benchmark_dataset`.
- `path` has a structured extension: `.json`, `.jsonl`, `.ndjson`, `.csv`, `.yaml`, `.yml`, or `.toml`.
- `path` resolves to a regular file inside the scan root.
- `path` is matched by `include` and is not matched by `exclude`.
- No other artifact entry has the same normalized path.

Schema-bearing path validation occurs after configuration loading and before artifact discovery. Any violation is invalid configuration and exits with code `3`; a declared contract must never be silently skipped.

The `schema` object accepts only:

- `fields`: required non-empty object mapping field names to field contracts.
- `required`: optional list of field names; default `[]`.

Each field name must be a non-empty top-level key. Dots, brackets, and nested field paths are invalid. Each field contract accepts only:

- `type`: required; one of `string`, `integer`, `number`, `boolean`, `object`, or `array`.
- `nullable`: optional boolean; default `false`.

Every name in `required` must be unique and must also exist in `fields`. Declared fields that are not required may be absent. Additional record fields are allowed. Values are never coerced: for example, the string `"42"` does not satisfy `integer`, and booleans do not satisfy `integer` or `number`. A `number` must be finite. For CSV artifacts, every declared field type must be `string` because the MVP CSV reader does not infer scalar types.

Contract enforcement and evidence behavior are defined in [`dataset.schema_contract_violation`](../03-rule-design/contamination-rules.md#datasetschema_contract_violation).

## Similarity Defaults

Default `similarity.enabled` is `true`.

Default `similarity.shingle_size` is `3`.

Default `similarity.num_hashes` is `64`.

Default `similarity.bands` is `16`.

Default `similarity.threshold` is `0.85`.

Default `similarity.focus_roles` is `["user"]`.

Default `similarity.focus_fields` is `["prompt", "input", "query", "user", "user_message"]`.

The similarity configuration applies only to near-duplicate rules. Exact-overlap rules do not use MinHash or LSH.

## Defaults

Default includes:

- all supported files under the scan root

Default excludes:

- `.git/**`
- `node_modules/**`
- `.venv/**`
- `venv/**`
- `__pycache__/**`
- `dist/**`
- `build/**`
- `.next/**`
- `.cache/**`
- `target/**`
- `coverage/**`

Default `ci.fail_on` is `high`.

## Pattern Semantics

Include and exclude patterns use repository-relative POSIX-style glob paths with `/` separators, regardless of operating system.

Exclude patterns take precedence over include patterns.

## Precedence

Configuration precedence:

1. CLI options.
2. Configuration file.
3. Built-in defaults.

Artifact role overrides from configuration replace heuristic roles for the specified path.

Artifact paths are normalized to repository-relative POSIX form by replacing `\` with `/` and removing one leading `./`. Artifact entries use exact paths, not glob patterns. Duplicate normalized artifact paths are invalid even when neither entry declares a schema.

## Invalid Configuration

Invalid configuration is a fatal scan error and must produce a nonzero exit code as defined in [CLI Contract And Exit Codes](../05-cli-and-reports/cli-contract-and-exit-codes.md).

## Design Decisions

- Configuration is optional to preserve zero-setup scanning.
- The MVP config is intentionally small.
- Role overrides are required because heuristic artifact detection cannot be perfect.
- Explicit schema contracts are attached to exact dataset artifacts so validation never depends on role or schema inference.
- A declared schema path that discovery would skip is invalid configuration rather than a silent partial scan.
- Severity overrides are supported because teams differ in risk tolerance.
- Suppressions are outside MVP.

## Open Questions

None.

## Dependencies

- [Scan Pipeline](scan-pipeline.md)
- [Artifact Model And Interface](../01-concepts/artifact-model-and-interface.md)
- [Rule Engine](rule-engine.md)
- [CLI Contract And Exit Codes](../05-cli-and-reports/cli-contract-and-exit-codes.md)

## Future Considerations

Future versions may add suppressions, baselines, profiles, and policy packs after MVP behavior is stable.

