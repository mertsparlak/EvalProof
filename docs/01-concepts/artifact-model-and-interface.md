# Artifact Model And Interface

## Question

What is an artifact, and how does core expose it to rules?

## Definition

An artifact is a file or file-derived unit that may affect LLM evaluation trust.

Files become artifacts through detection. Rules must inspect artifacts through core interfaces rather than reading raw files independently.

## Artifact Fields

Every artifact must expose:

- `id`: deterministic artifact identifier.
- `path`: repository-relative path.
- `format`: detected file format.
- `roles`: zero or more artifact roles.
- `role_source`: `config` or `heuristic`.
- `metadata`: structured metadata discovered during detection.
- `content`: access handle for text, rows, or structured data.

## Artifact ID

The artifact id is:

```text
sha256:<sha256 of repository-relative POSIX path>
```

The path input must:

- be relative to the scan root
- use `/` as the separator on every operating system
- preserve path case
- not include a leading `./`

The artifact id is based on path only. Content changes are represented by artifact fingerprints in [Project Index](../02-architecture/project-index.md).

## Supported Formats

MVP formats are defined in [MVP Scope](../00-product/mvp-scope.md).

Format detection must be deterministic and based on file extension, parse result, or explicit configuration.

MVP extension mapping:

- JSON: `.json`
- JSONL: `.jsonl`, `.ndjson`
- CSV: `.csv`
- YAML: `.yaml`, `.yml`
- TOML: `.toml`
- Markdown: `.md`, `.markdown`
- plain text: `.txt`, `.text`

Post-MVP optional format: Parquet `.parquet`; its reader contract is defined under
[Optional Parquet](#optional-parquet).

Files with unsupported extensions are not candidate artifacts unless configuration assigns an artifact role. If a configured artifact has an unsupported extension, it is treated as plain text and receives a diagnostic with code `artifact.unsupported_extension`.

## Artifact Roles

Allowed MVP roles:

- `training_dataset`
- `evaluation_dataset`
- `benchmark_dataset`
- `evaluation_result`
- `prompt_template`
- `rag_document`
- `configuration`
- `unknown`

An artifact may have multiple roles. Configuration overrides take precedence over heuristic role detection.

`role_source` is `config` when roles came from an explicit artifact override. It is `heuristic` when roles came from path and filename detection, including the `unknown` fallback.

## Role Detection Heuristics

Role detection precedence:

1. Explicit role overrides from configuration.
2. Filename and directory heuristics.
3. `unknown`.

Configuration overrides replace heuristic roles for the configured path.

An artifact override may also declare a schema contract for a structured training, evaluation, or benchmark dataset. The contract belongs to configuration rather than the artifact model: core does not infer schemas, and artifacts without an explicit contract remain valid scan inputs. The exact configuration syntax and validation rules are defined only in [Configuration And Schema](../02-architecture/configuration-and-schema.md).

Heuristic detection uses lowercase repository-relative POSIX paths.

`training_dataset`:

- path contains `/train/`, `/training/`, or `/finetune/`
- filename contains `train`, `training`, or `finetune`
- supported format is JSON, JSONL, CSV, YAML, or TOML

`evaluation_dataset`:

- path contains `/eval/`, `/evals/`, `/evaluation/`, `/test/`, or `/tests/`
- filename contains `eval`, `evaluation`, `test`, `golden`, or `expected`
- supported format is JSON, JSONL, CSV, YAML, or TOML

`benchmark_dataset`:

- path contains `/benchmark/`, `/benchmarks/`, or `/leaderboard/`
- filename contains `benchmark`, `bench`, or `leaderboard`
- supported format is JSON, JSONL, CSV, YAML, or TOML

`evaluation_result`:

- path contains `/result/`, `/results/`, `/report/`, `/reports/`, `/run/`, or `/runs/`
- filename contains `result`, `results`, `scores`, `metrics`, `baseline`, or `run`
- supported format is JSON, JSONL, CSV, YAML, or TOML

`prompt_template`:

- path contains `/prompt/`, `/prompts/`, `/template/`, or `/templates/`
- filename contains `prompt`, `template`, `system`, or `instruction`
- supported format is Markdown, plain text, JSON, YAML, or TOML

`rag_document`:

- path contains `/rag/`, `/retrieval/`, `/corpus/`, `/knowledge/`, `/kb/`, `/docs/`, or `/documents/`
- filename contains `corpus`, `knowledge`, `retrieval`, `context`, or `source`
- supported format is Markdown, plain text, JSON, JSONL, CSV, YAML, or TOML

`configuration`:

- filename is `evalproof.yaml`, `evalproof.yml`, `config.yaml`, `config.yml`, `config.json`, `settings.yaml`, `settings.yml`, or `settings.json`
- supported format is JSON, YAML, or TOML

Known configuration filenames above receive only `configuration`: their exact
filename match takes precedence over path fragments such as `eval`, `train`,
or `results`. This prevents the scanner's own configuration from becoming a
dataset or result artifact. Explicit artifact overrides still take precedence
and may intentionally assign other roles to these filenames.

Other artifacts may receive multiple heuristic roles if multiple rules match. For example, `eval/results/baseline.json` may be both `evaluation_dataset` and `evaluation_result`; rules decide applicability from artifact role and readable content.

If heuristic detection assigns `training_dataset` together with `evaluation_dataset` or `benchmark_dataset`, core emits an `artifact.role_conflict` warning diagnostic. The artifact remains available to rules, but cross-split rules must never compare the same artifact path with itself. Explicit multi-role configuration is treated as intentional and does not emit this diagnostic.

## Content Access

Rules need different content shapes. Core exposes text content for prompt,
Markdown and plain-text artifacts; row iteration for JSONL, CSV and Parquet;
and structured object access for JSON, YAML and TOML. Rules reuse indexed rows
instead of opening an independent binary reader.

### Optional Parquet

The `.parquet` extension is a structured row format when `evalproof[parquet]` is
installed. Dataset, evaluation-result and RAG filename/role heuristics apply as
for JSONL. It also supports explicit schema/provenance dataset contracts.
Raw Parquet bytes are never a text representation: text access returns an empty
string, while row access is supplied by
[Optional Parquet Records](../02-architecture/project-index.md#optional-parquet-records).
Text-only prompt interpolation is not extended to binary artifacts.

## Text Encoding Access

The artifact byte accessor returns original file bytes. Text access accepts one
leading UTF-8 BOM and normalizes line endings as before. Dataset byte validation
occurs in Project Index before parsing; its evidence and skip behavior are owned
by [Dataset Encoding Facts](../02-architecture/project-index.md#dataset-encoding-facts).
Rules must not decode bytes independently. Non-dataset text access retains the
existing replacement-decoding behavior; this milestone does not audit binary
formats or infer a file's intended alternate encoding.

## Parse Failures

Malformed supported files are still artifacts when their path and role are discoverable.

The scanner must not crash the full scan because one artifact cannot be parsed. Parse failures must be represented as deterministic scan diagnostics, not findings. Rules must not emit contamination findings from malformed content unless they can inspect enough valid artifact content to satisfy [Evidence Requirements](../03-rule-design/evidence-requirements.md).

## Interface Rules

Rules must not:

- Walk the filesystem.
- Re-detect artifact roles.
- Parse raw files independently unless the artifact content interface delegates parsing to them explicitly.
- Depend on absolute local paths.

Rules may:

- Query artifact roles.
- Read content through artifact access methods.
- Query project-level indexes described in [Project Index](../02-architecture/project-index.md).
- Read validated explicit contracts from scan configuration when a rule's contract requires them.

## Design Decisions

- Artifacts separate file discovery from rule logic.
- Artifact roles are explicit and overrideable.
- Artifacts may expose streaming row access to avoid loading large datasets.
- Parse errors are represented as scan data rather than fatal process errors.
- Dataset schemas are opt-in configuration contracts and are never inferred by artifact discovery.

## Open Questions

None.

## Dependencies

- [MVP Scope](../00-product/mvp-scope.md)
- [Project Index](../02-architecture/project-index.md)
- [Scan Pipeline](../02-architecture/scan-pipeline.md)
- [Configuration And Schema](../02-architecture/configuration-and-schema.md)

## Future Considerations

PDF and other binary formats remain outside the supported artifact contract.
