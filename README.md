# EvalProof

Verify your LLM datasets and evaluation artifacts before you trust the results.

EvalProof is a local-first static preflight scanner for LLM datasets and evaluation artifacts. It detects contamination, duplicate identities, explicit schema violations, reproducibility gaps, RAG trust failures, unsafe context interpolation, and sensitive values before teams train models or trust benchmark results.

EvalProof is not an evaluation framework, benchmark runner, prompt optimizer, observability platform, LLMOps platform, or generic security scanner.

## Install

Install from a source checkout:

```powershell
python -m pip install .
```

For local Parquet datasets, install the optional reader:

```powershell
python -m pip install ".[parquet]"
```

The base package does not require PyArrow. Without the extra, discovered Parquet
files are reported as skipped with an optional-dependency diagnostic. The reader
supports JSON-like columns, nested lists and structs; binary, temporal, decimal,
map and ambiguous schemas are skipped without coercion. See the
[Parquet contract](docs/02-architecture/project-index.md#optional-parquet-records).

Parquet fingerprints depend on decoded records, not compression or file metadata.
Batching limits decoding batches, not total index memory or decompressed bytes.

For local development with editable imports:

```powershell
python -m pip install -e .
```

## First Scan

### Dataset Profile Contract

```powershell
evalproof profile . --json --output evalproof_profile.json
```

The profile command reports observed row counts, rejected and duplicate rates,
sample ID and canonical field coverage, input character lengths and dataset
fingerprints. It never executes trust rules or applies CI severity thresholds.
Partial and skipped inputs remain explicit; an exit code of 0 means processing
completed, not that dataset quality passed a check.

Optional per-artifact fields can be declared in evalproof.yaml:

```yaml
artifacts:
  - path: train.jsonl
    roles: [training_dataset]
    profile:
      text_fields: [prompt]
      categorical_fields:
        - name: label
          expose_values: false
```

Category values are hashed by default. Only explicit expose_values: true includes
raw scalar categories in the report; this does not enable raw prompt or ID
evidence elsewhere. See the [measurement definitions](docs/02-architecture/project-index.md#dataset-measurement-calculations)
for denominators, unsupported shapes and empty values.

### Local Dataset Card

An explicitly linked local Hugging Face card can supply license-presence metadata
to the existing provenance check, without network access:

```yaml
artifacts:
  - path: train.jsonl
    roles: [training_dataset]
    provenance:
      required: [license]
      card: README.md
```

Only YAML front matter is inspected by the card reader. An explicit
`provenance.license` wins over the card. Unreadable or unsupported cards produce a
diagnostic rather than a missing-license assertion. This verifies recorded metadata,
not license suitability or dataset quality. See the
[card contract](docs/02-architecture/configuration-and-schema.md#explicit-local-dataset-card).

### Trust Scan

```powershell
evalproof scan .
```

Default behavior:

- scans the target folder
- prints a terminal summary
- writes `evalproof_report.json` into the scanned folder
- exits with `1` if any finding meets or exceeds the configured `fail_on` severity

Machine-readable output:

```powershell
evalproof scan . --json
```

Custom report path:

```powershell
evalproof scan . --json --output reports/evalproof_report.json
```

See the built-in rules and their short explanations before scanning:

```powershell
evalproof rules
```

Run only selected rules when a focused preflight is needed:

```powershell
evalproof scan . --rules contamination.train_eval_overlap,prompt.unresolved_placeholder
```

Without `--rules`, all registered rules run except rules disabled in `evalproof.yaml`. Rule selection is recorded in the JSON report.

The JSON report also records which artifacts were indexed, which roles came from configuration or heuristics, and whether any artifact was only partially indexed.

## Input Shape Boundary

EvalProof applies rules to the canonical fields and artifact roles documented in [Project Index](docs/02-architecture/project-index.md). Provider-specific nested schemas are not inferred automatically. Normalize them into the canonical input and target fields before scanning, or use explicit artifact role overrides in evalproof.yaml.

For dataset.label_inconsistency, canonical target fields may contain a scalar or a list of scalar values. List order and repeated values are normalized deterministically. Nested target objects remain outside the current contract.

## What It Detects

Exact contamination:

- `contamination.train_eval_overlap`
- `contamination.duplicate_eval_sample`
- `contamination.duplicate_train_sample`

Near-duplicate contamination:

- `contamination.train_eval_near_duplicate`
- `contamination.duplicate_eval_near_duplicate`
- `contamination.duplicate_train_near_duplicate`

Trust and safety checks:

- `contamination.rag_answer_leakage`
- `contamination.sensitive_value_exposure`
- `contamination.missing_repro_metadata`
- `contamination.fingerprint_mismatch`
- `contamination.untrusted_context_interpolation`
- `evaluation.sample_alignment_mismatch`
- `dataset.label_inconsistency`
- `dataset.sample_id_collision`
- `dataset.empty_evaluation_input`
- `dataset.schema_contract_violation`
- `dataset.partial_sample_id_coverage`
- `evaluation.metric_out_of_bounds`
- `rag.unreachable_context_id`
- `rag.chunk_id_collision` (explicit chunk_id within one RAG artifact only)
- `dataset.invalid_text_encoding` (invalid UTF-8 or actual NUL bytes; damaged datasets are not indexed)
- `provenance.required_metadata_missing` (only explicitly required metadata)
- `provenance.manifest_fingerprint_mismatch` (declared versus complete semantic fingerprint)
- `provenance.local_source_unresolved` (declared local source is missing or not a file)
- `reproducibility.nondeterministic_generation_without_seed` (advisory check on recorded evaluation parameters)
- `rag.duplicate_chunk_in_corpus`
- `rag.empty_or_corrupted_document`
- `rag.empty_referenced_document`
- `prompt.unresolved_placeholder` (heuristic; does not fail default CI)

## Configuration

EvalProof works without configuration. Add `evalproof.yaml` at the scan root only when defaults are not enough.

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
        sample_id:
          type: string
          nullable: true
  - path: "data/eval.jsonl"
    roles: ["evaluation_dataset"]

rules:
  disabled:
    - "contamination.untrusted_context_interpolation"
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
  focus_roles: ["user"]
  focus_fields: ["prompt", "input", "query", "user", "user_message"]
```

Schema validation is opt-in and applies only to exact configured training, evaluation, or benchmark dataset paths. EvalProof does not infer schemas, coerce values, or turn schema compliance into a dataset quality score. See [Configuration And Schema](docs/02-architecture/configuration-and-schema.md#explicit-dataset-schema-contracts) for the complete contract.

## CI

```powershell
evalproof scan . --json --output evalproof_report.json --fail-on high
```

GitHub Actions can use the same installed CLI contract:

```yaml
- uses: actions/checkout@v4
- uses: actions/setup-python@v5
  with:
    python-version: "3.13"
- run: python -m pip install .
- run: evalproof scan . --json --output "$RUNNER_TEMP/evalproof_report.json" --fail-on high
```

EvalProof does not require a custom GitHub Action. The workflow installs the package and evaluates the CLI exit code.

Exit codes:

- `0`: scan completed and no finding met the failing severity
- `1`: scan completed and at least one finding met the failing severity
- `2`: invalid CLI usage
- `3`: invalid configuration
- `4`: scan root is unreadable or not found
- `5`: output path cannot be written
- `6`: unexpected internal error

## Documentation

Versioned delivery status and release gates: [Roadmap](ROADMAP.md).

Design source of truth:

- [Positioning](docs/00-product/positioning.md)
- [Non-Goals](docs/00-product/non-goals.md)
- [Design Principles](docs/00-product/design-principles.md)
- [MVP Scope](docs/00-product/mvp-scope.md)
- [Contamination Rules](docs/03-rule-design/contamination-rules.md)
- [Configuration And Schema](docs/02-architecture/configuration-and-schema.md)
- [CLI Contract And Exit Codes](docs/05-cli-and-reports/cli-contract-and-exit-codes.md)
- [JSON Report](docs/05-cli-and-reports/json-report.md)

## Development

```powershell
python -m pytest -q
```
