# Project Index

## Question

What shared project-level knowledge do rules query?

## Purpose

The project index stores derived, deterministic facts about artifacts so cross-artifact contamination rules do not each re-parse and re-hash the same content.

## MVP Index Data

The MVP project index must provide:

- Artifacts by role.
- Artifacts by path.
- Normalized record hashes for dataset-like artifacts.
- Duplicate record groups within evaluation and benchmark artifacts.
- Cross-role overlap candidates between training, evaluation, and benchmark datasets.
- Text fingerprints for prompt templates and RAG documents where available.
- Evaluation result metadata fields discovered from structured result artifacts.

## Canonical Evaluation Result Metadata

The project index is the source of truth for mapping evaluation result metadata into canonical fields.

The MVP canonical fields are:

- `model_id`
- `generation_parameters`
- `prompt_fingerprint`
- `prompt_version`
- `dataset_fingerprint`
- `dataset_version`
- `metric_name`
- `metric_definition`
- `metric_threshold`
- `timestamp`

The MVP must use conservative alias mapping only. Accepted aliases:

- `model_id`: `model`, `model_id`, `model_name`
- `generation_parameters`: `generation_parameters`, `generation_params`, `parameters`, `params`
- `prompt_fingerprint`: `prompt_fingerprint`, `prompt_hash`, `prompt_sha256`
- `prompt_version`: `prompt_version`, `prompt_id`
- `dataset_fingerprint`: `dataset_fingerprint`, `dataset_hash`, `dataset_sha256`
- `dataset_version`: `dataset_version`, `dataset_id`
- `metric_name`: `metric`, `metric_name`
- `metric_definition`: `metric_definition`, `metric_description`
- `metric_threshold`: `threshold`, `pass_threshold`, `metric_threshold`
- `timestamp`: `timestamp`, `created_at`, `evaluated_at`

Nested metadata may be read from top-level objects named `metadata`, `eval`, `evaluation`, or `run`. If a field cannot be mapped through these aliases, it is treated as missing.

## Normalization

Normalization must be deterministic and conservative.

For row-based artifacts, the MVP normalization must:

- Parse structured rows when possible.
- Produce a stable JSON serialized representation with deterministic key ordering.
- Trim surrounding whitespace in string fields.
- Preserve semantic content rather than applying aggressive fuzzy matching.

The MVP must not use embeddings or model-based similarity.

Canonical JSON serialization:

- UTF-8 encoded text.
- Object keys sorted lexicographically by Unicode code point.
- No insignificant whitespace.
- Arrays preserve order.
- Strings preserve case and internal whitespace, except surrounding whitespace is trimmed for row normalization.
- Numbers preserve parsed numeric value using the platform JSON serializer's shortest round-trippable representation.
- Booleans and null use JSON literals.
- Unicode text is not case-folded.

JSONL normalization:

- each non-empty line is parsed as one JSON value
- malformed lines produce a diagnostic for the artifact and are excluded from row indexes
- normalized rows preserve source row numbers

JSON row extraction:

- if the root value is an array, each array item is one row
- if the root value is an object with an `examples`, `samples`, `records`, `rows`, `data`, or `items` array field, each array item in the first matching field is one row
- otherwise the JSON artifact is structured content but not row-based
- extracted rows preserve one-based row numbers based on array position

CSV normalization:

- the first row is treated as a header row
- header names are trimmed
- each following row is normalized as an object keyed by header name
- rows with the wrong field count produce a diagnostic and are excluded from row indexes

Plain text normalization for containment checks:

- line endings normalize to `\n`
- leading and trailing whitespace is trimmed
- internal consecutive whitespace collapses to a single ASCII space
- case is preserved

## Answer Field Extraction

The project index is the source of truth for extracting answer-like values from evaluation and benchmark rows.

The MVP answer field aliases are:

- `answer`
- `expected`
- `expected_answer`
- `gold`
- `gold_answer`
- `label`
- `reference`
- `reference_answer`

If none of these fields exist in a structured row, RAG answer leakage rules must not use that row.

Extracted answer values are converted to strings. Empty values, values shorter than 16 characters after plain text normalization, and trivial labels are ignored.

Trivial labels are:

- `yes`
- `no`
- `true`
- `false`
- single letters
- single digits

## Hashing

The index must store hashes of normalized content rather than relying on raw content for comparisons.

Hashes must be deterministic and stable across machines.

## Artifact Fingerprints

Artifact fingerprints are `sha256` hashes over normalized artifact content.

MVP fingerprint inputs:

- JSON, YAML, and TOML: parsed structured content serialized with canonical JSON serialization.
- JSONL: normalized rows in file order, joined with newline separators.
- CSV: parsed rows using header names, serialized with canonical JSON serialization per row and joined with newline separators.
- Markdown and plain text: original text with line endings normalized to `\n`.

If an artifact cannot be parsed according to its detected format, no computed fingerprint is available for that artifact and the scanner must emit a diagnostic rather than inventing a fingerprint.

## Role Awareness

The index must respect artifact roles from [Artifact Model And Interface](../01-concepts/artifact-model-and-interface.md).

Role overrides from configuration must be applied before index construction.

## Limits

The index must support scan limits from [Configuration And Schema](configuration-and-schema.md), including file size and row count limits.

MVP limit behavior:

- Files larger than `limits.max_file_mb` are skipped and produce a deterministic diagnostic.
- Row-based artifacts stop indexing after `limits.max_rows_per_artifact` rows and produce a deterministic diagnostic.
- Rules must not emit findings that require skipped content.
- Diagnostics must identify the artifact path, limit name, configured limit, and observed size or row count when available.

## Design Decisions

- Cross-artifact contamination checks use a shared project index.
- MVP normalization is exact and conservative.
- The MVP avoids fuzzy matching, embeddings, and model inference.
- Index data is derived from artifacts, not raw filesystem reads inside rules.

## Open Questions

None.

## Dependencies

- [Artifact Model And Interface](../01-concepts/artifact-model-and-interface.md)
- [Configuration And Schema](configuration-and-schema.md)
- [Contamination Rules](../03-rule-design/contamination-rules.md)

## Future Considerations

In EvalProof v1.1, the `SimilarityIndex` was added as a reusable, additive extension to the `ProjectIndex` for deterministic near-duplicate candidate discovery using MinHash and LSH. Embedding-based or model-assisted similarity checks remain deferred unless explicitly required by future specifications.
