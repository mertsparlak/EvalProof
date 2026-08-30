# EvalProof

Verify your LLM evaluation artifacts before you trust the results.

EvalProof is a local-first static preflight scanner for LLM evaluation artifacts. It detects contamination, duplication, reproducibility gaps, RAG answer leakage, unsafe context interpolation, and sensitive values before teams trust benchmark results or deploy LLM systems.

EvalProof is not an evaluation framework, benchmark runner, prompt optimizer, observability platform, LLMOps platform, or generic security scanner.

## Install

```powershell
pip install -e .
```

## First Scan

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
- `evaluation.metric_out_of_bounds`
- `rag.unreachable_context_id`
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

## CI

```powershell
evalproof scan . --json --output evalproof_report.json --fail-on high
```

Exit codes:

- `0`: scan completed and no finding met the failing severity
- `1`: scan completed and at least one finding met the failing severity
- `2`: invalid CLI usage
- `3`: invalid configuration
- `4`: scan root is unreadable or not found
- `5`: output path cannot be written
- `6`: unexpected internal error

## Documentation

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
