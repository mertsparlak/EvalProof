# EvalProof Versioned Product Roadmap

## Purpose

Which approved milestone is next, what does it deliver, and what evidence permits completion?

This is the execution roadmap approved on 2026-08-31. Milestone names are not
package versions. This file tracks scope, dependencies and release gates.
Rule contracts live in [Contamination Rules](docs/03-rule-design/contamination-rules.md);
configuration belongs to [Configuration And Schema](docs/02-architecture/configuration-and-schema.md).
A planned version is not an implemented or published release.

## Status

| Milestone | Target package | Status | Deliverable |
| --- | --- | --- | --- |
| v1.19 | 0.1.0 | Completed | Explicit dataset schema validation |
| v1.20 | 0.2.0 | Completed | Artifact-local explicit RAG chunk identity |
| v1.21 | 0.2.1 | Completed | Generation reproducibility |
| v1.22 | 0.2.2 | Completed | Dataset encoding integrity |
| v1.23 | 0.3.0 | Completed | Dataset provenance contracts |
| v1.24 | 0.4.0 | Completed | Optional Parquet support |
| v1.25 | 0.5.0 | Completed | Measurement and profile contract |
| v1.26 | 0.6.0 | Planned | Dataset profiling measurements |
| v1.27 | 1.0.0 | Gated | Public release qualification |
| v1.28+ | 1.x | Gated | Integrations and conditional adapters |

## v1.20: RAG Chunk Identity

The user approved the conservative identity correction on 2026-08-31.
Parent document IDs are not chunk identities. Cross-file collision detection is
deferred until an explicit shared corpus namespace contract is approved.

- Add `rag.chunk_id_collision`, high/confirmed, default CI failing.
- Use only explicit top-level chunk_id and existing top-level RAG content aliases.
- Compare within each artifact, never across files or via id/doc_id/source_id aliases.
- Emit one finding per artifact/ID linked to multiple distinct non-empty content hashes.
- Same-ID/same-content duplicates, missing/nested IDs, empty-only content and
  incomplete artifacts are not collisions under this conservative slice.
- Project Index owns extraction; rules do not read files.
- Evidence contains only hashes, bounded row/field locations, counts and truncation.
- Gate: positive, negative, empty-content, cross-file abstention, determinism and redaction tests.
- Commit: `feat(v1.20): detect RAG chunk identity collisions`.

Verified on 2026-08-31: 202 tests passed on local Python 3.14, including the
24-rule accuracy matrix, collision abstention/redaction and traversal determinism.
A clean-source wheel installed outside the repository passed help, rule listing,
clean/contaminated scans and invalid-usage exit checks. Runtime, distribution and
scan report versions agree on 0.2.0; scan schema remains 1.0.
The smoke audit also corrected successful help returning exit 2 and restricted
package discovery to product modules so tests/build directories are not shipped.
The existing local pytest cache warning remains non-blocking. No remote CI run
or publication is claimed; v1.21 onward remains planned or gated.

## v1.21: Generation Reproducibility

- Add `reproducibility.nondeterministic_generation_without_seed`.
- Only evaluation results with an explicit generation parameter object apply.
- Reuse generation_parameters/generation_params/parameters/params metadata aliases.
- A finite numeric temperature greater than zero without a non-null/non-blank seed
  produces medium/likely advice, not a default CI failure.
- Boolean/string temperatures, absent config and temperature zero are ignored.
- Preserve the observed parameter location; do not infer provider capabilities.
- Merge the older temperature candidate into this ID instead of adding two rules.
- Commit: `feat(v1.21): detect unseeded stochastic evaluation runs`.

### Implementation Plan And Strategy Review

1. Preserve canonical result metadata selection while retaining its exact source
   field in Project Index. No recursive parameter search or provider adapter.
2. Test all four aliases and five source levels, conflicting aliases, missing/null/
   blank/present seeds, invalid temperatures, non-result roles and parse failure.
3. Add one advisory finding per result artifact, reusing selected metadata only.
   Evidence carries field paths, finite temperature and seed absence state; no
   arbitrary parameter values, prompts, credentials or provided seeds.
4. Add positive, seeded-negative and no-parameters abstention accuracy fixtures;
   verify traversal determinism, rule listing, default exit 0 and explicit medium
   threshold exit 1. Update package/runtime/CI version to 0.2.1.
5. Run the complete suite, review changed contracts and commit locally.

Review outcome: a missing seed proves missing recorded metadata, not actual model
non-determinism. The message is therefore advisory and never promises that adding
a seed makes execution deterministic. A provided non-blank value suppresses this
rule even if malformed; seed validation is outside this milestone. Existing
metadata alias precedence remains authoritative, avoiding conflicting views of
the same result between reproducibility rules.

Verification on 2026-08-31: 254 tests passed on Python 3.14, including 52 focused
generation tests and a 25-rule accuracy matrix. Default/explicit CI thresholds,
redaction, source locations and deterministic fingerprints are covered. Package,
runtime and report versions are 0.2.1. The local pytest cache warning remains.

## v1.22: Dataset Encoding Integrity

- Add `dataset.invalid_text_encoding` for training/evaluation/benchmark datasets.
- Detect invalid UTF-8 and NUL bytes; accept and strip a UTF-8 BOM before parsing.
- Core records deterministic diagnostics; damaged dataset bytes are not indexed
  through replacement decoding. The scan continues on other artifacts.
- One medium/confirmed finding per affected artifact, bounded offsets/counts and
  artifact byte hash, no raw bytes.
- Do not add broad suspicious-character or malicious-intent heuristics.
- Malformed record rates remain measurements; parse diagnostics and explicit schema
  violations already own the underlying failures.
- Commit: `feat(v1.22): detect invalid dataset encodings`.

### Implementation Plan And Strategy Review

1. Audit dataset bytes after the existing file-size gate, before parsing. Use
   Python's strict UTF-8 decoder; record the first invalid range and bounded NUL
   offsets without inventing a total invalid-sequence count.
2. Expose redacted encoding facts in Project Index. Emit one encoding diagnostic
   even with the rule disabled; distinguish a skipped artifact from a clean one.
3. Add a medium/confirmed rule consuming only those facts, no file access or raw
   bytes. Keep its physical-byte hash separate from semantic dataset fingerprints.
4. Test malformed/truncated UTF-8, actual NUL, valid multilingual text, BOM across
   formats, escaped NUL, limits, unrelated roles, evidence bounds and determinism.
5. Add the accuracy case, listing, report documentation and 0.2.2 version updates;
   run the full suite and commit locally.

Review outcome: replacement decoding is unsafe for identity comparisons because
distinct invalid bytes can collapse to the same character. Skip damaged dataset
indexing rather than manufacture trustworthy row hashes. NUL is valid Unicode,
so describe it as an unsupported text-dataset byte, not invalid UTF-8 or malicious
content. No binary-encoding autodetection, automatic repair or source writes.

Verification on 2026-08-31: 281 tests passed on Python 3.14, including 27 focused
encoding tests and the 26-rule accuracy matrix. BOM equivalence, physical byte
offsets, bounded evidence, skip coverage and rule-independent diagnostics passed.
Package/runtime/report versions are 0.2.2; the known pytest cache warning remains.

## v1.23: Provenance Contracts

- Add optional `artifacts[].provenance`, not a separate manifest discovery system.
- Fields: required, version, fingerprint, source(type/ref/revision),
  generator(name/version), license.
- Required fields are explicit; no provenance declaration means no provenance finding.
- Add manifest_fingerprint_mismatch (high/confirmed),
  required_metadata_missing (medium/confirmed), and local_source_unresolved
  (high/confirmed), all under the provenance namespace.
- Local source references are root-relative and may not escape the scan root.
- Never fetch remote sources or interpret licenses legally.
- Hash/redact source and generator values in evidence.
- Commit: `feat(v1.23): verify dataset provenance contracts`.

### Implementation Plan And Strategy Review

1. Define an optional typed per-dataset provenance contract. Strictly validate
   unknown keys, required leaf names, scalar types and SHA-256 syntax. Do not
   infer provenance from filenames or mandate fields the user did not require.
2. Validate declared dataset targets before discovery using the existing explicit
   contract path policy. Reject absolute, traversal, drive/UNC and symlink-escaping
   local source references before inspecting their targets. Remote refs stay opaque.
3. Give Project Index an explicit optional scan root for local-source metadata
   checks. Index redacted source existence facts; rules never access the filesystem.
   Sources may be excluded from discovery; only regular-file presence is checked.
4. Implement required_metadata_missing, manifest_fingerprint_mismatch and
   local_source_unresolved independently. Fingerprints compare existing semantic
   fingerprints only on complete indexes, never a partial prefix or byte hash.
5. Test no-contract abstention, required fields, matching/mismatching hashes,
   partial/encoding-damaged data, missing/directory sources, traversal/symlink
   rejection, permission errors, remote no-network behavior and redaction.
6. Extend accuracy matrix/listing, update package to 0.3.0, run full tests, review
   the contracts and commit locally. No publishing.

Review outcome: a local source that cannot be inspected is not proven missing.
Permission/I/O failures produce a diagnostic and abstention; only missing or
non-file targets produce confirmed findings. License is an opaque recorded value,
not a legal judgment. A missing source.ref is not an unresolved path; it is only
missing metadata when explicitly required. Provenance is a declaration to check,
not independent proof that the claimed source actually generated the dataset.

Prerequisite found during the v1.23 full-suite review: similarity shingle hashing
used process-randomized `hash()` and unsorted set sampling. Four hash seeds
produced four signatures on identical text. Replace those with stable hash-ranked
sampling and test full reports across subprocess seeds before closing v1.23.
This correctness fix can change near-duplicate candidate selection relative to
older runs; exact Jaccard scoring and thresholds are unchanged. Release calibration
must use the corrected implementation, not treat historical green tests as proof.

Verification on 2026-08-31: 330 tests passed on Python 3.14, including 47 provenance
tests, the 29-rule accuracy matrix and cross-process scan/signature determinism.
Root-escape resolution and permission failures use deterministic filesystem mocks;
this does not claim a live Windows symlink privilege test. A clean 0.3.0 wheel
contains only product modules and distribution metadata. Runtime/distribution/
report versions agree. The existing pytest cache warning remains non-blocking.

## v1.24: Optional Parquet

- Add `evalproof[parquet]` with `pyarrow>=25,<26`; base install stays lightweight.
- Missing extra produces an optional-dependency diagnostic, not a crash.
- Support dataset/result/RAG roles and existing limits.
- Read deterministic batches of 65,536 rows with global 1-based row numbers.
- Fingerprint canonical row contents, not compression-dependent physical file bytes.
- Preserve row semantics for schema, overlap, identity, RAG and profiling.
- Gate: base/extra clean wheel installs, missing-extra tests and format equivalence.
- Commit: `feat(v1.24): add optional parquet dataset scanning`.
- References: [Arrow compatibility](https://arrow.apache.org/docs/python/install.html),
  [batch API](https://arrow.apache.org/docs/python/generated/pyarrow.parquet.ParquetFile.html).

### Implementation Plan And Strategy Review

1. Add an optional `parquet` extra and extension/role/schema/provenance support.
   Load PyArrow lazily only for Parquet. Missing or incompatible PyArrow produces
   a dependency diagnostic, never a dataset-corruption finding.
2. Read local binary handles with deterministic batches. Reject unsupported or
   ambiguous Arrow schemas without coercion; keep binary bytes out of text APIs.
3. Index supported rows through the existing row/hash/similarity/answer/metric
   machinery. Preserve JSONL-equivalent fingerprints across compression and row
   group layout, with global row positions and existing size/row limits.
4. Adapt existing RAG and sensitive-value rules to logical records, not binary
   bytes. Keep Parquet locations row-based. Prevent schema/empty-RAG findings when
   the reader is unavailable or its schema unsupported. Hash answer-match evidence
   instead of exposing raw gold answers when reporting containment.
5. Test format equivalence, supported types, unsupported schema abstention,
   corruption, missing extra, limits, row-group boundaries, existing rule behavior,
   report redaction and cross-process determinism. Generate all Parquet fixtures
   locally in temporary directories; no public dataset downloads.
6. Verify base and extra non-editable wheel installs outside the repository, run
   the full suite with PyArrow 25.x, update CI to test the extra, and commit locally.

Review outcome: Parquet support must not invent text semantics for binary/temporal
values or confuse scanner limitations with data defects. Only the existing
JSON-like record model is supported initially; unsupported types get explicit
coverage diagnostics. File-size limits apply to physical bytes and batch size to
rows, not a hard decompressed-memory budget. No URI/dataset-directory reader,
remote filesystem, arbitrary metadata interpretation or new public plugin API.
PyArrow 25.0.1 and Python 3.14 compatibility were verified against official docs;
testing uses a temporary environment, leaving the user's PyArrow 23.0.1 unchanged.

Integration tests also exposed raw sample IDs in existing alignment evidence.
Together with RAG answer snippets, these violate the privacy boundary. Preserve
the evidence keys but hash their values for all formats; finding fingerprints
can change as a result. This is a privacy correction, not a new detector.

Missing-reader tests also proved a false-absence risk: a skipped RAG artifact may
contain the referenced ID, and a skipped dataset may match the result fingerprint.
These rules now abstain on incomplete candidate groups; sample alignment requires
both participating indexes to be complete. Observed positive evidence is retained.

Verification on 2026-08-31: 373 tests passed with PyArrow 25.0.1 on Python 3.14;
342 passed and the optional-format module was skipped in a clean no-PyArrow
environment. Generated fixtures cover compression equivalence, 65,536-row batch
boundaries, row limits, reader errors, schema rejection, existing rules, redaction
and cross-process determinism. Both base and extra 0.4.0 wheels installed offline
into separate temporary environments and passed outside-checkout CLI smoke tests.
The wheel contains only 46 product/distribution files, including the reader and
license. CI now includes extra and installed-wheel checks; no remote run, public
dataset calibration, push or publication is claimed by this milestone.

## v1.25: Separate Profile Contract

- Add `evalproof profile <path>` with config/json/output/no-color options.
- Never execute rules or emit Findings. Rules/fail-on options are invalid usage.
- Successful profiling returns 0; usage/config/root/output/internal errors use 2/3/4/5/6.
- Default report file: evalproof_profile.json.
- Separate profile envelope: schema_version, report_type=profile, tool, profile,
  summary, measurements, diagnostics. Scan report schema 1.0 is unchanged.
- Measurement fields: measurement_id, artifact_id, artifact_path, scope, value,
  unit, population_count, coverage, parameters, method, evidence, fingerprint.
- No measurement severity, confidence, impact or recommendation.
- Commit: `feat(v1.25): add deterministic dataset profiling contract`.

### Implementation Plan And Strategy Review

1. Freeze Measurement as an internal typed record separate from Finding. Define
   stable identity, scope, coverage, finite JSON values and deterministic hashing
   in the existing model document, without an external plugin or SDK API.
2. Add profile command/options and a separate report envelope. Reuse config,
   discovery and Project Index; select dataset roles only and disable similarity
   computation in an internal config copy. Never execute rules or severity policy.
3. Preserve CLI error categories and offline behavior. Successfully profiling
   partial/unavailable data returns 0 with explicit coverage diagnostics, not a
   clean-dataset verdict. Ignore rule/CI settings after structural config validation.
4. Exclude the generated profile report by default. In profile, always exclude
   its resolved output path before discovery is indexed, so repeated invocations
   cannot measure their own output even with custom include/exclude patterns.
5. Test CLI invalid options/error precedence, empty and malformed inputs, no rule/
   similarity execution, finite values, stable fingerprints, timestamp-only report
   differences, traversal order and source immutability. Keep scan schema unchanged.
6. Align package to 0.5.0, extend installed-wheel smoke, verify full base/extra
   suites and commit locally. v1.25 produces an empty measurements list; v1.26
   supplies the calculators without changing this envelope.

Review outcome: profiling must not become a second rule engine or silently run
near-duplicate computation. Dataset roles are selected explicitly/heuristically by
the existing artifact policy; no role inference from content is added. Profile
schema 1.0 has its own namespace identified by report_type, not a change to scan
schema 1.0. Empty measurements in this contract milestone are not quality evidence.

Verification on 2026-08-31: 400 tests passed with the optional reader; 369 passed
and the optional-format module was skipped in the base environment. The 27 new
profile tests cover command isolation, error categories, finite measurement
construction, path safety, ordering, output self-exclusion and process determinism.
Non-editable base/extra 0.5.0 wheels passed scan and profile smoke outside the
checkout. No new rule or measurement calculator is claimed by this milestone.

## v1.26: Dataset Measurements

- Measure row counts, rejected-record rate, exact-duplicate rate, sample ID coverage,
  canonical field coverage, input character lengths and artifact fingerprints.
- Duplicate count is the sum of group_size minus one.
- Rejected rate uses observed indexed plus rejected rows, with partial coverage
  when the row limit prevents a complete observation.
- Length statistics use nearest-rank p50/p95 and min/max; no token estimate.
- Existing canonical input aliases remain the default; no inferred nested/chat shapes.
- Optional per-artifact profile settings specify text_fields and categorical_fields.
- Categorical entries declare name and expose_values (false by default).
- Default category evidence is hashed. Raw scalar values require explicit opt-in.
- Never turn a distribution into a finding, quality judgment or CI failure.
- Commit: `feat(v1.26): add evidence-safe dataset measurements`.

## v1.27: Release Qualification

No new features. Do not set package version 1.0.0 until all gates have evidence:

1. Every rule has positive, negative and abstention accuracy fixtures.
2. Confirmed findings calibrated on at least ten distinct public datasets.
3. Scan/profile determinism excluding timestamps.
4. JSON/JSONL/CSV/YAML/TOML/optional-Parquet format matrix.
5. Clean base and extra wheel installations outside the repository.
6. Python 3.11, 3.12, 3.13 and 3.14 CI matrix.
7. 100k-row synthetic CI smoke and recorded larger local dataset checks.
8. No unresolved confirmed false positive.
9. Documentation, help, listing and report contracts match runtime behavior.

Commit only after qualification: `chore(v1.27): qualify EvalProof 1.0 release`.
Publishing or pushing is a separate explicit user action.

## Conditional Post-1.0 Work

v1.28: read explicitly linked local Hugging Face card YAML metadata without network
access. Metadata can support provenance/profiling, not legal or quality verdicts.
Its detailed integration contract must be reviewed before implementation.

SchemaAdapter design opens only when two rules duplicate schema-family extraction,
or at least 20 percent of calibration datasets cannot use core measurements because
of unsupported shapes. Start internal; candidate families are OpenAI messages,
instruction/input/output and chosen/rejected preferences. No external API yet.

Model-assisted work is a separate research track, not a version commitment.
After static contracts stabilize, design target runner, prompt generation budget,
model/seed provenance, judging, sandboxing, rate limits and a separate hypothesis/result
schema. Never add it to the static Rule interface or default scan.

## Permanent Boundaries

No universal quality/trust/readiness score, inferred class-imbalance failure, subjective
prompt score, AI-text verdict, generic toxicity/bias verdict, dataset-only model
vulnerability claim, evaluation runner, observability platform, general security
scanner or legal interpretation.

## Delivery Policy

Implement milestones in order. Use test-first development, full pytest verification
and a separate local commit per milestone. Update status only from observed evidence.
Do not push, publish, download public data into the repository or skip a failed gate.
Changed contracts are documented in their owning documents, not duplicated here.

## Design Decisions

- Findings and measurements have separate execution and reporting contracts.
- Training and evaluation trust is the product boundary.
- Milestone and package numbering are separate and explicit.
- Optional format dependencies preserve a small offline base package.
- Post-1.0 architecture work is conditional, not a hidden implementation commitment.

## Open Questions

None for the approved execution order. Conditional work requires its own design gate.

## Dependencies

- [Positioning](docs/00-product/positioning.md)
- [Rule contracts](docs/03-rule-design/contamination-rules.md)
- [Configuration](docs/02-architecture/configuration-and-schema.md)
- [Candidate history](docs/03-rule-design/future-rule-candidates.md)

## Future Considerations

Only the conditional post-1.0 track above is approved for further design, not automatic implementation.
