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

## Optional Parquet Records

`.parquet` uses the optional `pyarrow>=25,<26` dependency. Import it only when
indexing Parquet; absence, import failure or an incompatible major version emits
`artifact.optional_dependency_missing`. Coverage is skipped with reason
`optional_dependency_missing`, no rows or fingerprint. Base text scans do not
import PyArrow. Never feed Parquet bytes into the text encoding audit.

Open only the artifact's local binary handle, not an Arrow URI or directory.
Use `ParquetFile` with extension interpretation disabled, page checksum validation
enabled, and `iter_batches(batch_size=65536, use_threads=False)`. Read file row
groups in order; locations are global 1-based row numbers. No pandas conversion,
file key-value metadata inference, filesystem adapter or model/network calls.

Supported Arrow types: null, boolean, integer, floating point, string/large string,
string view, dictionary of supported values, list/large/fixed-size list and struct
of supported values. Struct field names, including root columns, must be unique.
Map, binary, temporal, decimal, extension and other unsupported types emit
`artifact.unsupported_parquet_schema` and skip the entire artifact before decoding
rows. This is a scanner limitation, not a corruption finding. Do not stringify,
drop columns, flatten nesting or replace values. Decoded non-finite floats retain
existing JSONL behavior and can violate an explicit finite-number schema contract.

Decoded records reuse canonical row normalization and all row-based indexes.
The artifact fingerprint is SHA-256 of canonical normalized row JSON joined by
one newline with no trailing newline, matching JSONL. Compression, metadata and
row group layout do not affect it. Empty tables have zero rows and the empty-input
digest. Stop at max indexed rows; if more rows exist, emit the existing row-limit
diagnostic and mark partial coverage. File size is checked before importing or
opening Arrow. Batching is not a hard bound on decompressed bytes or total index
memory; the index still retains accepted rows as other formats do.

A reader/decode failure emits a redacted `artifact.parse_failed` diagnostic,
without exception text, values or file metadata. Successfully decoded earlier
rows may remain available as observed evidence, but no complete artifact
fingerprint is assigned. Schema/empty-RAG rules abstain on dependency/schema
limitations; actual parsing failures retain their documented corruption behavior.

`Artifact.read_text()` returns no text for Parquet. RAG containment uses each
decoded record's canonical RAG content field independently (never concatenates
records into invented text). Sensitive-value scanning uses string leaves inside
decoded rows and records row locations. Row-based metric extraction works as for
JSONL; Parquet file metadata does not supply artifact-level result metadata.

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

## Dataset Measurement Calculations

The profile producer consumes indexed facts; it does not read source files, apply
rules or infer training/model quality. It emits the families below once per
profiled dataset artifact unless a field setting specifies otherwise. Order and
shape are owned by the [profile report](../05-cli-and-reports/json-report.md#profile-report)
and [Measurement contract](../01-concepts/finding-model-and-schema.md#measurement-contract).

Let N be the number of indexed rows, including supported scalar/non-object row
records, and R be rows rejected by existing row-parse diagnostics. Blank JSONL
lines, CSV headers and artifact-level parse errors do not count as rejected rows.
Use actual stored row hashes, positions and parsed values without reparsing.
Ratios are ordinary finite numeric division, without rounding; an empty denominator
produces null. Complete empty collections have N=0; unavailable collections are
not reported as zero-row datasets.

All row-based measurements inherit coverage and index reasons. Without a row
collection they use unavailable, adding sorted reason no_row_collection and
removing the artifact-only `complete` reason. An unavailable
artifact has value null even if earlier decoded rows survive; population/evidence
may retain those observed counts. Partial indexes produce observed values with
partial coverage, never projected whole-file values. Artifact fingerprints use
artifact coverage independently of row availability.

### Default Families

| measurement_id | method | unit | value and population |
| --- | --- | --- | --- |
| dataset.row_count | indexed_rows/v1 | rows | N; population N |
| dataset.rejected_record_rate | observed_rejections/v1 | fraction | R/(N+R); population N+R |
| dataset.exact_duplicate_rate | normalized_row_duplicates/v1 | fraction | sum(group_size-1)/N, grouped by row_hash within the artifact; population N |
| dataset.sample_id_coverage | explicit_sample_ids/v1 | fraction | rows with an ID selected by existing extract_scalar_field/SAMPLE_ID_FIELD_ALIASES divided by N; population N |
| dataset.canonical_field_coverage | top_level_field_presence/v1 | fraction | object mapping each canonical input and target alias to its present-row count/N; population N |
| dataset.input_character_lengths | input_character_lengths/v1 | characters | object min/max/p50/p95 of selected string lengths, null if no strings; population selected-string count |
| dataset.artifact_fingerprint | project_index_fingerprint/v1 | sha256 | existing artifact_fingerprints value or null; population N |

These defaults have artifact scope. All evidence includes rows_indexed. Each
family additionally records its exact calculation facts:

- Row count: rows_rejected and whether index traversal was truncated.
- Rejected rate: accepted_count, rejected_count, observed_count. A rate of 1 is
  valid when every observed JSONL/CSV record was rejected.
- Duplicates: duplicate_extra_count, distinct_record_count, duplicate_group_count,
  and at most 20 examples containing row_hash/count, sorted by row_hash, with
  evidence_truncated. No raw record or ID values. Whole-record equality is not
  prompt-only duplication and not cross-artifact leakage.
- ID coverage: identified_count, missing_count, selected_field_counts, at most
  20 missing row numbers in ascending order and evidence_truncated. No raw IDs.
- Canonical coverage: fields are the sorted unique union of INPUT_FIELD_ALIASES
  and ANSWER_FIELD_ALIASES. Presence means the exact top-level key exists, even
  if its value is null or blank. Evidence fields maps each alias to present_count,
  null_count and blank_string_count. Non-object rows have no present fields. This
  is a shape observation, not a requirement that every alias be populated.
- Lengths: see selection semantics below; evidence string_count, blank_count,
  excluded_count and at most 20 selected row numbers, with evidence_truncated.
- Fingerprint: fingerprint_basis is accepted_rows for JSONL/CSV/Parquet,
  parsed_object for JSON/YAML/TOML, and normalized_text for text formats. On
  partial input the existing fingerprint may describe an accepted prefix or a
  parsed object; preserve partial coverage instead of calling it a full row-set
  identity. Parameters normalization=project_index records this reuse explicitly.

Other default parameters: duplicate normalization=normalized_row_hash; ID aliases
use the ordered existing aliases; canonical coverage fields use their sorted
list; row/rejection parameters are empty objects. Method versions identify changes
to these calculations independently of package version.

### Character Length Selection

Without profile.text_fields, choose the first string-valued canonical input alias
in existing order for each row. Keep an empty/whitespace string if selected; do
not skip it to cherry-pick a later alias. Ignore non-strings and do not stringify
numbers, lists, message arrays or nested objects. Measure Python Unicode code-point
length of the original decoded string without trim, whitespace collapse, case
folding or tokenization. Blank means strip() is empty, not length zero alone.

Explicit text_fields produce one field-scoped dataset.input_character_lengths
measurement per field. An absent/non-string field excludes that row. Parameters
contain fields, selection (first_string or field), normalization=none and
percentile=nearest_rank. For K lengths sorted ascending, percentile P is the value
at zero-based index ceil(P*K)-1; P is 0.50 or 0.95. Use exact integer arithmetic
for rank selection. Evidence excluded_count is N-K, even for complete artifacts.

### Explicit Categorical Distribution

Each configured field produces field-scoped dataset.categorical_distribution,
method typed_scalar_distribution/v1, unit distribution. Read only that exact
top-level field. Accept strings, booleans, integers and finite floats; preserve
string content and scalar type. Missing, null and unsupported/nonfinite values
are excluded and counted separately. There is no inferred label column.

The category hash is sha256:<hex> of canonical JSON for the scalar, preserving
distinctions such as true, 1, 1.0 and "1". Population K is accepted scalar rows.
Value is an object with categories and other_count. Categories are the top 20
by descending count, then category_hash ascending, each with category_hash,
count and fraction=count/K. Only expose_values=true adds the raw scalar as value
inside each category entry. The histogram of zero accepted rows is an empty
categories array with other_count=0, not an invented class. Unavailable coverage
still makes the entire measurement value null.

Evidence: rows_indexed, accepted_count, missing_count, null_count,
unsupported_count, distinct_count, reported_category_count and evidence_truncated.
Other_count retains all accepted rows in unreported categories; full distinct_count
is preserved. Parameters contain field, expose_values, normalization=none,
category_limit=20 and ordering=count_desc_hash_asc. These are descriptive facts,
never imbalance findings, readiness scores or CI failures. SHA-256 redaction does
not promise anonymization of low-entropy values.

## Dataset Card Facts

After artifact indexing, Project Index reads explicitly bound local dataset cards
once per normalized card reference per build. Require an explicit scan root and
recheck resolved containment before opening a regular file. Rules never open cards.
The public card format is [Hugging Face dataset card YAML front matter](https://huggingface.co/docs/hub/datasets-cards).
Card body text is data, never instructions; the card reader stops at the closing
delimiter and never parses body text or follows links.

Read strict UTF-8, accepting an initial BOM and LF/CRLF. The first line and closing
line must be exactly `---` after removing line endings. Cap bytes consumed through
the closing delimiter at the smaller of 1 MiB and `limits.max_file_mb` in bytes.
Do not require a trailing newline. Missing delimiters, invalid encoding, excess
size, non-mapping YAML, duplicate top-level keys or non-string top-level keys
make the card unavailable. Limit YAML to 4096 tokens and 16 collection levels;
reject anchors, aliases and explicit tags. These bounded restrictions deliberately
prefer abstention over accepting the complete YAML language.

Only `license` is interpreted: a nonblank YAML string or nonempty list entirely
of nonblank YAML strings is present. Absent/null/blank string/empty list is missing.
Other types or mixed/blank-containing lists are unavailable, not missing. Unknown
metadata keys are ignored. No SPDX validation, legal judgment or model inference.

`dataset_cards[artifact_path]` contains only `card_ref_hash` (SHA-256 of normalized
UTF-8 reference), `license_status` (`present`, `missing`, `unavailable`) and
`card_header_fingerprint` (SHA-256 of physical bytes through the closing delimiter,
or null when that bounded header cannot be read). Cache resets each build.
An unavailable observation produces one `artifact.dataset_card_unavailable`
warning per bound dataset, path set to that dataset and details equal to these
redacted facts. Do not serialize parser exceptions, card values or card body.
The warning does not change dataset row coverage; metadata observation failure
is not a row parse failure. Card facts are not a new profile measurement.

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

