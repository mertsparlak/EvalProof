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
- Similarity index entries for row-based artifacts when similarity is enabled.
- Deterministic artifact coverage metadata for reporting.

## Artifact Coverage

The index exposes report-safe coverage metadata for every discovered artifact. Coverage describes what core indexed; it does not claim that every rule found a violation or that a role heuristic was semantically correct.

Each coverage record contains:

- `path`, `format`, `roles`, and `role_source`.
- `index_status`: `indexed`, `partial`, or `skipped`.
- `index_reasons`: deterministic reasons for the status.
- `rows_indexed`, or `null` for non-row artifacts.
- `rows_rejected` for malformed row records.
- `truncated` when the configured row limit stopped indexing.
- computed `fingerprint`, or `null` when unavailable.
- `diagnostic_codes` associated with the artifact.
- `role_matched_rule_ids`, meaning active rules whose declared roles intersect the artifact roles.

Coverage records are sorted by repository-relative POSIX path. A file-size limit or full parse failure produces `skipped`; row parse failures or row limits produce `partial` when a usable fingerprint remains. An artifact without row content but with a valid text or structured fingerprint is `indexed`.

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

## Evaluation Result Rows And Sample IDs

Evaluation result rows use the same row extraction rules as structured dataset artifacts. Result rows are read from a root array or the first matching `examples`, `samples`, `records`, `rows`, `data`, or `items` array.

The canonical sample ID aliases are:

- `id`
- `sample_id`
- `example_id`
- `record_id`
- `case_id`

A sample alignment rule may compare IDs only when every row on both sides exposes one of these scalar fields. Result order is never treated as identity.

A result is associated with dataset artifacts for alignment only when its `dataset_fingerprint` matches the computed fingerprint of one or more evaluation or benchmark artifacts. If no matching artifact exists, fingerprint mismatch owns the finding and alignment emits nothing.

## Explicit Metric Records

The index extracts metric records only from evaluation result artifacts.

Supported metric names are:

- `accuracy`
- `accuracy_percent`
- `exact_match`
- `f1`
- `precision`
- `recall`
- `bleu`
- `rouge`
- `loss`
- `perplexity`
- `pass_rate`
- `success_rate`
- `win_rate`

A metric is indexable only when it has a numeric value and either:

- a numeric two-element `bounds` or `metric_bounds` field; or
- a supported `unit` or `metric_unit`: `fraction`, `percent`, or `nonnegative`.

Unit-derived bounds are [0, 1], [0, 100], and [0, +infinity] respectively. Unknown metric names and metrics without explicit scale evidence are ignored.

## Explicit RAG Context References

The index extracts context references only from top-level structured row fields.

Evaluation and benchmark rows support these scalar fields:

- `doc_id`
- `document_id`
- `context_id`
- `source_id`
- `chunk_id`

They also support these list fields:

- `doc_ids`
- `document_ids`
- `context_ids`
- `source_ids`
- `chunk_ids`
- `retrieved_context_ids`

RAG document rows support the scalar fields above plus `id`. RAG list fields are not used as corpus identifiers in the MVP.

For referenced-document integrity, RAG rows may expose content through the scalar fields `text`, `content`, `document`, `body`, `chunk`, or `page_content`. Nested content and free-text document IDs are not used.

Context identifiers are trimmed, remain case-sensitive, and accept only non-empty strings or finite numeric scalar values. Booleans, nested objects, nested metadata, filenames, and free-text matches are ignored. The generic `id` field is a RAG document identifier only; an evaluation row's `id` remains a sample identifier.

Each extracted reference also has a stable SHA-256 hash for evidence that must not expose the raw identifier.

## Dataset Encoding Facts

After the file-size gate, inspect original bytes of training/evaluation/benchmark
artifacts (excluding configuration roles). File-size-skipped artifacts have no
encoding facts. A row limit does not limit this byte audit: all accepted bytes
are inspected. Supported text formats and explicitly configured plain text use
the same audit. Binary formats are outside this contract.

`encoding_issues[path]` exists only for invalid UTF-8 or actual NUL bytes and holds:
`artifact_path`, `byte_hash` (SHA-256 of original bytes), `byte_count`,
`invalid_utf8_range` (null or `{offset, length}` for the first strict decoder
error), `nul_byte_count` (complete count), `sample_nul_offsets` (first 20), and
`nul_offsets_truncated`. Offsets are zero-based physical byte positions including
any BOM. The first error range is not a count of every invalid UTF-8 sequence.
Literal U+FFFD and escaped JSON `\u0000` are not physical encoding defects.

Core emits one warning diagnostic `artifact.invalid_text_encoding` per affected
artifact with these redacted facts as details, regardless of rule selection.
Do not parse or index that artifact, or assign it a semantic fingerprint.
Coverage is `skipped` with reason `invalid_text_encoding`; no row count is claimed.
The scan continues on the other artifacts. This avoids replacement characters
creating false identities. A single leading UTF-8 BOM is accepted and stripped
before parsing healthy text; semantic fingerprints otherwise follow existing
normalization. The byte hash is not interchangeable with a dataset fingerprint.

## Provenance Source Facts

`ProjectIndex(config, scan_root=None)` accepts an explicit scan root when local
provenance references need filesystem metadata. CLI always supplies it. A caller
with an applicable local source contract must supply it; omission is a programming
error, not permission to infer a root from artifact paths. Rules do not use it.

`provenance_sources[path]` records `source_ref_hash` (SHA-256 of normalized UTF-8
ref) and `status`: `present`, `missing`, `not_file`, or `unreadable`. Check only
explicit nonempty local refs on discovered provenance-bearing artifacts. Repeat
root-boundary validation at inspection, then use filesystem metadata, not reads.
Do not add referenced sources to discovery or inspect remote references.
Missing/not-file statuses are objective facts. Permission or other I/O errors
produce `artifact.provenance_source_unreadable` warning and unreadable status,
without raw paths or OS exception text. Rules abstain on that status.

Provenance fingerprint comparison uses existing semantic artifact fingerprints
only with complete coverage (`indexed`). Skipped/partial artifacts supply no
comparison claim. Required metadata checks use the validated declaration itself
and do not depend on successful content parsing.

## Generation Metadata Locations

Result metadata selection checks the root object followed by `metadata`, `eval`,
`evaluation`, `run` (one level only). Within each source, canonical alias order
applies. The first non-null value wins, including a value of the wrong type;
no later alias overrides it. This preserves existing metadata selection.

`eval_metadata_locations[path][canonical_name]` retains that selected field path
(for example `metadata.generation_params`). `eval_metadata` keeps the selected
values. Both maps reset on every index build. JSON/YAML/TOML root objects support
this contract; JSONL/CSV rows and root arrays do not declare artifact-level
generation parameters. Row limits do not invalidate metadata already parsed from
the complete root object. Parse failures have no usable metadata.

## RAG Chunk Identity Records

`get_rag_chunk_records()` exposes redacted identity/content records from indexed
`rag_document` artifacts. It excludes configuration artifacts and artifacts with
parse, row-parse, row-limit or file-size diagnostics. No evaluation artifact is
required; a RAG artifact can be checked independently.

Only an explicit top-level `chunk_id` is a chunk identity. General `id`,
`doc_id`, `document_id`, `context_id` and `source_id` fields are not substitutes:
they may identify a parent document shared by multiple chunks.

Chunk IDs use the context identifier normalization above: trim strings, preserve
case, accept finite numeric scalars through their deterministic string form, and
reject booleans, empty values, objects and arrays. Integer 7 and string "7" are
equivalent; float 7.0 and string "7.0" are equivalent but distinct from "7".

Content extraction is shared with exact RAG duplicate detection through
`extract_rag_content()`. In order, inspect `text`, `content`, `document`,
`body`, `chunk`, `page_content`; choose the first non-empty string. Normalize
line endings and whitespace using `normalize_plain_text`, preserving case.
Unsupported/nested content is ignored, not inferred.

Each record contains `artifact_path`, `row_num`, `row_hash`,
`chunk_id_hash`, `content_field`, `content_hash`. Chunk ID and content hashes are
SHA-256 of normalized UTF-8 values; `row_hash` is the existing indexed row hash.
Raw IDs and content are not carried by this interface.
Records are ordered by artifact path and row. Querying does not mutate the index.

The artifact path is part of the identity namespace; no shared corpus namespace
is inferred. Finding grouping and evidence limits belong to
[`rag.chunk_id_collision`](../03-rule-design/contamination-rules.md#ragchunk_id_collision).

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

For `dataset.label_inconsistency`, the same canonical aliases may contain either one scalar target or a list of scalar targets. List values are trimmed, deduplicated, sorted deterministically, and compared as a target set. A scalar and a single-value list with the same normalized value are equivalent. Empty values, booleans, and nested target objects are ignored by this rule. This list handling does not broaden scalar-only RAG answer extraction.

## Hashing

The index must store hashes of normalized content rather than relying on raw content for comparisons.

Hashes must be deterministic and stable across machines.

## Canonical Evaluation Input Fields

The canonical scalar input aliases are `prompt`, `question`, and `input`. Rules that inspect evaluation inputs must use this shared alias set. A missing canonical field is not itself a finding; rules must not infer an input from unsupported message-list or nested schemas.

## Similarity Index

Near-duplicate rules use a deterministic MinHash + LSH similarity index.

The similarity index:

- extracts comparison text from row-based artifacts
- focuses on configured `similarity.focus_roles` for chat-style `messages` rows
- falls back to configured `similarity.focus_fields`
- falls back to canonical structured row text only when no focused text exists
- computes character shingles using `similarity.shingle_size`
- computes MinHash signatures using `similarity.num_hashes`
- groups candidates using `similarity.bands`
- confirms candidate pairs using exact Jaccard similarity over shingle sets
- emits findings only when Jaccard similarity is greater than or equal to `similarity.threshold`

The similarity index is evidence-generating but approximate in candidate selection. Final findings must include exact Jaccard similarity so users can verify why the finding fired.

Shingle hashing must not depend on Python's process hash seed. Use the first four
bytes of SHA-256 over UTF-8, interpreted big-endian and masked to 31 bits. Sort
those hash values and retain the lowest 50 for signature computation. This keeps
the existing bounded sample but makes both sample membership and hashes stable.
LSH bucket keys are the band index and signature-value tuple, not a process hash.
Exact Jaccard still uses complete shingle sets. Candidate recall is approximate;
determinism does not imply exhaustive discovery. Cross-process tests must vary
`PYTHONHASHSEED`; same-process repeated scans alone do not prove this contract.

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
- Near-duplicate checks use deterministic MinHash + LSH plus exact Jaccard confirmation.
- The scanner avoids embeddings and model inference.
- Index data is derived from artifacts, not raw filesystem reads inside rules.
- Result-to-dataset association requires a matching computed dataset fingerprint.
- Sample identity is explicit-ID based; positional row matching is not a trust signal.
- Metric bounds are checked only when the result declares an explicit scale.
- RAG context references are extracted from explicit top-level fields and compared without case folding.

## Open Questions

None.

## Dependencies

- [Artifact Model And Interface](../01-concepts/artifact-model-and-interface.md)
- [Configuration And Schema](configuration-and-schema.md)
- [Contamination Rules](../03-rule-design/contamination-rules.md)

## Future Considerations

In EvalProof v1.1, the `SimilarityIndex` was added as a reusable, additive extension to the `ProjectIndex` for deterministic near-duplicate candidate discovery using MinHash and LSH. Embedding-based or model-assisted similarity checks remain deferred unless explicitly required by future specifications.

