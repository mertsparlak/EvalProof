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
- disabled rules
- severity overrides
- minimum failing severity
- scan limits

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
```

Top-level keys outside `include`, `exclude`, `artifacts`, `rules`, `ci`, `limits`, and `similarity` are invalid.

Schema field types:

- `include`: list of strings
- `exclude`: list of strings
- `artifacts`: list of objects with `path` string and `roles` list of artifact role strings
- `rules.disabled`: list of rule id strings
- `rules.severity`: object mapping rule id strings to severity strings
- `ci.fail_on`: severity string
- `limits.max_file_mb`: positive integer
- `limits.max_rows_per_artifact`: positive integer

Allowed severity strings are `critical`, `high`, `medium`, and `low`.

Invalid role strings, invalid severity strings, invalid rule ids for MVP rules, and wrong field types make the configuration invalid.

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

## Invalid Configuration

Invalid configuration is a fatal scan error and must produce a nonzero exit code as defined in [CLI Contract And Exit Codes](../05-cli-and-reports/cli-contract-and-exit-codes.md).

## Design Decisions

- Configuration is optional to preserve zero-setup scanning.
- The MVP config is intentionally small.
- Role overrides are required because heuristic artifact detection cannot be perfect.
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
