# Future Rule Candidates

## Question

Which rule candidates may be considered after the current scanner is stable, and which candidates should be rejected, merged, or deferred?

## Purpose

This document is a candidate backlog, not an implementation contract.

A rule listed here is not part of the current scanner until it is promoted into [Contamination Rules](contamination-rules.md) with complete evidence, severity, confidence, CI behavior, and tests. Promoted candidates may remain here as historical design records; the current contract is always the Contamination Rules document.

This document exists to prevent rule sprawl. EvalProof should remain known for trustworthy evaluation artifact findings, not broad lint noise.

## Promotion Criteria

A candidate may be promoted only when all of these are true:

- The finding directly affects whether evaluation artifacts can be trusted.
- The rule can run locally and offline.
- The rule has objective evidence a user can verify.
- The rule has clear false-positive boundaries.
- The recommendation is concrete and actionable.
- The rule does not duplicate an existing rule or diagnostic.
- Heuristic candidates do not fail default CI unless they become objective enough to be `confirmed` or strong `likely` findings.

## Candidate Status Values

- `promote`: strong candidate for a future rule after tests and implementation planning.
- `merge`: should be handled by an existing rule or diagnostic instead of becoming a new rule.
- `defer`: plausible, but not reliable enough yet or needs stronger artifact contracts.
- `reject`: outside EvalProof's trust boundary or too subjective/noisy.
- `implemented`: promoted into the current rule contract.

## Recommended Next Rule Batch

The evaluation trust-chain slice and `rag.unreachable_context_id` are implemented. Current rule status is maintained below as historical backlog information; the active contract remains [Contamination Rules](contamination-rules.md). Future promotion must continue to satisfy the objective-evidence and false-positive criteria in this document.

The following dataset rules were promoted in v1.10 or later and are now part of the active contract:

- `dataset.sample_id_collision`
- `dataset.empty_evaluation_input`
- `dataset.partial_sample_id_coverage` (promoted in v1.14)
- `dataset.schema_contract_violation` (promoted in v1.19)

The following RAG rules were promoted in v1.11 or later and are now part of the active contract:

- `rag.duplicate_chunk_in_corpus` (promoted in v1.15)
- `rag.empty_or_corrupted_document` (promoted in v1.15)
- `rag.empty_referenced_document`

## Dataset Integrity Candidates

### `dataset.schema_contract_violation`

Status: `implemented`

The rule validates only schemas explicitly declared for exact training, evaluation, or benchmark artifacts. Schema inference, readiness scoring, and subjective quality judgments remain rejected. The active configuration and finding contracts are defined in [Configuration And Schema](../02-architecture/configuration-and-schema.md#explicit-dataset-schema-contracts) and [Contamination Rules](contamination-rules.md#datasetschema_contract_violation).

### `dataset.partial_sample_id_coverage`

Status: `implemented`

Problem: only a subset of indexed evaluation or benchmark rows exposes a stable sample ID, preventing complete sample-level result alignment.

The implementation contract, evidence bounds, abstention behavior, and false-positive boundaries are defined in [Contamination Rules](contamination-rules.md).

### `dataset.empty_or_malformed_record`

Status: `merge`

Reason: malformed rows are already represented as scan diagnostics, not contamination findings. Keeping parse failures as diagnostics preserves the separation defined in [JSON Report](../05-cli-and-reports/json-report.md).

Possible future shape: a different candidate, `dataset.malformed_record_rate`, may be considered if malformed rows exceed an objective configured threshold in an evaluation dataset.

Promotion requirements for future shape:

- artifact path
- malformed row count
- total attempted row count
- malformed percentage
- configured threshold

Default confidence: `confirmed`

Default severity if promoted: `high` only when the malformed rate crosses a high threshold; otherwise `medium`

Default CI behavior: fail only when severity is `high` or above

### `dataset.class_imbalance_anomaly`

Status: `defer`

Reason: a single label above 95 percent can be valid for some evaluations. This is a useful warning only when the artifact has a clear label field and enough rows to make the distribution meaningful.

Required evidence if promoted:

- artifact path
- label field
- dominant label redacted or hashed if sensitive
- dominant label count
- total labeled row count
- percentage
- configured threshold

Default confidence: `heuristic`

Default severity if promoted: `medium`

Default CI behavior: must not fail default CI

Promotion requirement: define minimum row count and accepted label-field aliases before implementation.

### `dataset.label_inconsistency`

Status: `implemented`

Problem: the same normalized prompt/input appears with different expected answers or labels inside evaluation or benchmark data.

Required evidence:

- artifact path or paths
- normalized prompt/input hash
- row locations
- answer or label field names
- redacted or hashed conflicting label values
- conflict count

Default confidence: `confirmed`

Default severity if promoted: `high`

Default CI behavior: can fail default CI

False-positive risks:

- multi-answer tasks where multiple references are valid
- prompts with unknown context fields that are not included in normalization

Promotion requirement: define canonical input fields and canonical target fields in the project index before implementation.

## Evaluation Integrity Candidates

### `evaluation.sample_alignment_mismatch`

Status: `implemented`

Problem: evaluation result rows do not align with the fingerprint-matched evaluation or benchmark dataset by count or explicit sample ID.

Required evidence:

- result artifact path
- matched dataset artifact path or paths
- dataset fingerprint
- dataset and result counts
- mismatch types
- limited missing, unexpected, or duplicate IDs when available

Default confidence: `confirmed`

Default severity if promoted: `high`

Default CI behavior: can fail default CI

Promotion requirement: use only fingerprint-associated artifacts; never use positional row matching as identity.

### `evaluation.metric_out_of_bounds`

Status: `implemented`

Problem: evaluation result artifacts contain known metric values outside an explicitly declared unit or numeric bounds contract.

Required evidence:

- result artifact path
- metric name
- metric value
- accepted bounds
- explicit unit or bounds evidence
- field path

Default confidence: `confirmed`

Default severity if promoted: `high`

Default CI behavior: can fail default CI

Promotion requirement: unknown metrics and values without explicit scale evidence must not emit findings.
### `evaluation.zero_variance_score`

Status: `defer`

Reason: all scores being 0.0 or 1.0 may indicate a broken evaluator, but can also be valid for tiny or easy datasets. This is not strong enough for default failing CI without sample-count constraints.

Required evidence if promoted:

- result artifact path
- score field
- repeated score value
- scored sample count
- minimum sample threshold

Default confidence: `heuristic`

Default severity if promoted: `medium`

Default CI behavior: must not fail default CI

Promotion requirement: define minimum sample count and supported result shapes.

### `evaluation.unmatched_evaluation_sample_count`

Status: `merge`

Reason: count mismatch is implemented as the `evaluation.sample_alignment_mismatch` evidence subtype. It must not become a second rule with overlapping result-to-dataset association logic.
## Prompt Integrity Candidates

### `prompt.unresolved_placeholder`

Status: `implemented`

The current implementation checks only string values in `prompt`, `question`, and `input` fields of `evaluation_dataset` and `benchmark_dataset` rows. Prompt template artifacts, training datasets, message lists, and free-text fields are excluded.

Required evidence:

- artifact path
- row and field location
- placeholder syntax class
- stable input hash
- detected placeholder count

Default confidence: `heuristic`

Default severity: `medium`

Default CI behavior: must not fail default CI

False-positive risks:

- intentionally literal braces in evaluation input values
- placeholder-like syntax that is not an unresolved template
- templating instructions in prompt authoring docs

The implementation deliberately reports this as heuristic because static scanning cannot prove whether a placeholder was rendered before model execution.

### `prompt.excessive_length_truncation_risk`

Status: `defer`

Reason: truncation risk depends on model context length, tokenizer, rendered variables, and provider behavior. A fixed 32,000-character threshold is useful as a warning but not objective enough for default CI.

Required evidence if promoted:

- prompt artifact path
- measured character length
- configured threshold
- optional model/context metadata if available

Default confidence: `heuristic`

Default severity if promoted: `medium`

Default CI behavior: must not fail default CI

Promotion requirement: keep it threshold-based and explicitly heuristic unless model context metadata is available locally.

### `prompt.system_role_misconfiguration`

Status: `defer`

Reason: detecting that a system instruction was accidentally sent as a user message requires intent inference unless the chat schema is explicit and the content has objective system-instruction markers.

Required evidence if promoted:

- artifact path
- row or message index
- observed role
- field path
- objective marker that indicates system-like content

Default confidence: `heuristic`

Default severity if promoted: `medium`

Default CI behavior: must not fail default CI

Promotion requirement: define a narrow detector that avoids judging prompt style.

## RAG Integrity Candidates

### `rag.chunk_id_collision`

Status: `implemented` in v1.20.

The approved slice checks explicit chunk_id only within one artifact. Parent
document aliases and cross-file comparisons are excluded to avoid conflating
independent namespaces. The extraction contract belongs to
[Project Index](../02-architecture/project-index.md#rag-chunk-identity-records);
the finding contract belongs to [Contamination Rules](contamination-rules.md#ragchunk_id_collision).
Cross-file collisions remain deferred pending an explicit corpus namespace contract.

### `rag.empty_or_corrupted_document`

Status: `implemented`

The candidate is implemented as `rag.empty_or_corrupted_document`. The current finding contract is defined in [Contamination Rules](contamination-rules.md).

Problem: RAG corpus artifacts referenced by evaluation are empty, whitespace-only, or unreadable enough to make retrieval-grounded evaluation untrustworthy.

Required evidence:

- RAG artifact path
- observed size or normalized text length
- corruption or parse diagnostic code when available

Default confidence: `confirmed`

Default severity if promoted: `medium`

Default CI behavior: must not fail default CI

Relationship to diagnostics: parse failures remain diagnostics; the implemented rule emits only for RAG artifacts in scans that contain an evaluation or benchmark artifact.

### `rag.duplicate_chunk_in_corpus`

Status: `implemented`

The exact-match slice is implemented. Near-duplicate RAG matching remains deferred because it requires stronger chunk-boundary and false-positive controls.

Problem: identical or near-identical chunks are indexed multiple times across RAG corpus documents, which can overweight retrieval evidence and distort RAG evaluation.

Required evidence:

- source RAG artifact path and chunk location
- duplicate RAG artifact path and chunk location
- normalized chunk hash or similarity score
- duplicate count

Default confidence: `confirmed` for exact duplicates; `likely` for near duplicates

Default severity if promoted: `medium`

Default CI behavior: should not fail default CI by default

Promotion requirement: define chunk boundaries. Without explicit chunks, use paragraph-level exact matching first.

### `rag.unreachable_context_id`

Status: `implemented`

The candidate is implemented as `rag.unreachable_context_id`. The current finding contract is defined in [Contamination Rules](contamination-rules.md), and the extraction contract is defined in [Project Index](../02-architecture/project-index.md). This section remains only as a promotion history record.
## Security And Safety Candidates

### `security.hardcoded_credential_exposure`

Status: `merge`

Reason: this should be an expansion of `contamination.sensitive_value_exposure`, not a separate security product pillar.

Candidate detector additions for the existing rule:

- OpenAI keys beginning with `sk-`
- AWS access keys beginning with `AKIA`
- GitHub tokens beginning with `ghp_`
- provider-specific tokens only when regex evidence is strong enough to avoid broad false positives

Required evidence stays the existing redacted-value contract.

Default confidence: `heuristic`

Default severity: keep `medium` unless a detector becomes highly specific and low-noise

Default CI behavior: must not fail default CI by default

### `security.unbounded_prompt_injection_payload`

Status: `reject`

Reason: this is too subjective as phrased and overlaps with `contamination.untrusted_context_interpolation`. EvalProof should not become a prompt-injection quality scanner.

Possible replacement: add narrow delimiter and interpolation checks to `contamination.untrusted_context_interpolation` only when the trigger remains objective.

### `security.raw_pii_exposure`

Status: `merge`

Reason: this belongs in `contamination.sensitive_value_exposure` as detector expansion.

Candidate detector additions for the existing rule:

- SSN-like values with strict formatting
- credit-card-like values only with Luhn validation
- private keys
- country-specific identifiers only when they can be detected with strong validation and documented false-positive limits

Required evidence stays redacted or hashed.

Default confidence: `heuristic`

Default severity: `medium`

Default CI behavior: must not fail default CI by default

Note: country-specific identifiers such as TCKN should not be added until locale-specific validation and false-positive behavior are documented.

## Provenance Contracts

v1.23 implements `provenance.required_metadata_missing`,
`provenance.manifest_fingerprint_mismatch`, and `provenance.local_source_unresolved`.
These are explicit declaration checks, not inferred dataset lineage or license
advice. Their source of truth is [Provenance Rules](contamination-rules.md#provenance-rules).

## Dataset Encoding Integrity

`dataset.invalid_text_encoding` is implemented in v1.22. Its bounded byte evidence
and dataset-only applicability live in
[Contamination Rules](contamination-rules.md#datasetinvalid_text_encoding).
This is not a broad suspicious-character heuristic or an encoding repair tool.

## Reproducibility Candidates

### `reproducibility.non_deterministic_temperature_setting`

Status: `merged`, implemented in v1.21 as
`reproducibility.nondeterministic_generation_without_seed`.

The narrower result-only advisory contract lives in
[Contamination Rules](contamination-rules.md#reproducibilitynondeterministic_generation_without_seed).
Intentional stochastic evaluations and providers without seed support remain
valid use cases; the rule reports missing recorded state, not a proven runtime
defect. No second rule or configuration-artifact variant is registered.

### `reproducibility.missing_model_version_pin`

Status: `defer`

Reason: whether a model id is pinned is provider-specific and changes over time. A static offline scanner can detect suspicious generic aliases, but cannot maintain a complete provider truth table without drift.

Required evidence if promoted:

- result or config artifact path
- model id field
- model id value
- local pattern that marks the id as floating or unpinned

Default confidence: `heuristic`

Default severity if promoted: `medium`

Default CI behavior: must not fail default CI

Promotion requirement: start with a small local denylist of obvious aliases and document that it is heuristic.

### `reproducibility.dataset_version_mismatch`

Status: `merge`

Reason: this is already covered by `contamination.fingerprint_mismatch` when both referenced and computed fingerprints are comparable.

Future work should improve the existing fingerprint rule rather than create a parallel dataset-version rule.

## Future Dynamic Attack Layer

Dynamic attack generation is not a static rule and is outside the current scanner.

In a future layer, training-data patterns may be used only to generate attack hypotheses. A model weakness must not be inferred from dataset content alone. A weakness finding would require executing generated prompts against a target model and preserving the observed model output as evidence.

That layer requires separate contracts for:

- target model runner
- attack prompt generator
- execution budget
- sandbox and security boundaries
- model version and seed reproducibility
- response judge or scorer
- attack evidence format
- model-call errors and rate-limit handling

It must not run during the offline static scan, must not be required by default,
and must never be coupled to the static `Rule` interface. A separate architecture
review is required before implementing any execution or evidence model.

### Research Design Review After Static Qualification

Status: design recorded, not implemented and not a scheduled product version.
The versioned delivery boundary is maintained in [Roadmap](../../ROADMAP.md).
No runner, generator, scorer, model dependency, new CLI command or automatic
network access is authorized by this research note.

The research question is whether dataset-informed test generation finds additional
reproducible target-model failures compared with a fixed test-template baseline
under the same execution budget. A small local generator is a candidate, not a
proven requirement. Training data is incomplete evidence of learned behavior:
pretraining, tuning, runtime instructions and retrieval also influence outputs.
Dataset statistics alone cannot answer that question.

1. Freeze the task contract and failure assertions before generating prompts.
   Record dataset fingerprint and exact selection rules; separate generation
   material from a held-out assessment pool. Deduplicate generated tests against
   that pool. Do not select evaluation criteria after seeing model failures.
2. Start with deterministic templates as the control. Compare a small local
   generator under matched target-call and token budgets; generator cost is
   reported separately. Do not download weights or transmit source records
   automatically. Model choice requires its own hardware and license assessment.
3. Use a separate execution harness rather than building provider orchestration
   into EvalProof. Inspect already separates named model roles and sandboxed tools;
   see [model roles](https://inspect.aisi.org.uk/models.html#model-roles) and
   [sandboxing](https://inspect.aisi.org.uk/sandboxing.html). Prefer evaluating an
   existing harness integration before designing a bespoke runner.
4. Require an explicitly authorized target and positive per-run request, token,
   wall-time and concurrency limits before any execution; the unconfigured budget
   is zero. Count retries against the request budget, default automatic retries to
   zero, and never retry after exhaustion. Authentication/configuration failures
   terminate the run; rate limits/timeouts are execution errors, not model failures.
5. Disable tools, filesystem mutation and arbitrary network access for the first
   experiment. Allow only the named target endpoint when remote execution is
   explicitly approved. Source records and retrieved documents remain untrusted
   data, not authorization to execute their instructions. No attack against third
   parties, production users or systems outside the declared target boundary.
6. Separate generator, target and judge identities. Use executable objective
   assertions where the task supports them. Otherwise preserve judge uncertainty
   and obtain blinded human adjudication of claimed failures. A generator judging
   its own prompts is not independent validation. A refusal is neither universally
   a success nor a failure; the declared task contract determines the outcome.
7. Store hypothesis and observation records outside scan/profile schemas. A
   hypothesis links dataset/selection fingerprints, generating method, prompt
   fingerprint and intended assertion, but has no confirmed weakness verdict.
   An observation links that hypothesis to target identity, generation settings,
   request/response fingerprints, outcome, judge version and evidence references.
   Execution errors, unjudged responses and inconclusive judgments stay distinct.
8. Keep raw prompts/responses in access-controlled local experiment artifacts,
   never ordinary EvalProof reports or automatic uploads. Shared summaries use
   hashes and bounded metadata. A hash alone is not a witness: verification
   requires authorized access to the underlying response and the failure criterion.
   Record target/generator/judge versions, seeds, settings and runner version;
   an opaque floating provider model identity limits replay guarantees even with
   the same seed. Replays retain attempts rather than overwriting prior evidence.
9. Report planned, attempted, completed, judged, failed, inconclusive and errored
   counts separately. Failure fractions use judged completed attempts with that
   denominator stated, never silently count failed requests as model successes.
   Compare incremental adjudicated failures, false positives, duplicate-test rate,
   reproducibility and total cost against the fixed-template control.

Promotion requires a predeclared experiment on at least two authorized target
models with held-out cases, reproducible evidence and a useful improvement over
the control. No numeric benefit or model superiority is claimed without results.
If the generator adds cost without additional valid failures, retain the simpler
control and do not ship a model-assisted product layer. The next action for this
track would be a separately approved, budgeted experiment, not a static rule.

## Rejected Or Deferred Themes

The following themes should not become rules without a new design review:

- broad dataset quality scoring
- subjective prompt quality scoring
- general repository-wide security scanning
- provider-specific model policy checks that require network freshness
- dynamic evaluation execution

These are constrained by [Design Principles](../00-product/design-principles.md) and [Non-Goals](../00-product/non-goals.md).

## Calibration Record

A local calibration run on public datasets used up to 1,000 rows per artifact. This record contains no raw dataset values and does not expand the active rule contract.

- The phone detector produced a confirmed false positive on an arithmetic-shaped `######-####` value. The detector boundary was tightened to require formatted phone groups; the behavior is covered by regression tests.
- Same-artifact near-duplicate candidates in SQuAD-like and TruthfulQA-like shapes were caused by different explicit contexts or targets. The project index now carries only a redacted discriminator hash, and the evaluation near-duplicate rule abstains when those hashes differ.
- Exact duplicate content, duplicate sample identities, empty evaluation inputs, conflicting labels, empty RAG documents, and exact duplicate RAG records remained independently verifiable in the calibration sample.
- Near-duplicate findings without explicit context or target fields remain advisory `likely` findings. Static similarity still cannot infer whether a contrast pair was intentionally authored.
## Design Decisions

- New rules must be promoted deliberately; this document does not expand scanner scope by itself.
- Diagnostics remain separate from findings unless a trust-impacting rule has objective evidence.
- Security candidates are supporting contamination/trust checks, not a separate scanner product.
- Heuristic candidates must not fail default CI.
- The first new-rule batch should prioritize objective evidence over coverage breadth.
- Sample alignment is the canonical evaluation-result correspondence rule; count mismatch is not a separate rule.
- Explicit metric scale is required before metric bounds findings can be trusted.

## Open Questions

None.

## Dependencies

- [Design Principles](../00-product/design-principles.md)
- [Non-Goals](../00-product/non-goals.md)
- [Evidence Requirements](evidence-requirements.md)
- [Contamination Rules](contamination-rules.md)
- [Project Index](../02-architecture/project-index.md)

## Future Considerations

When a candidate is promoted, move the final rule contract into [Contamination Rules](contamination-rules.md) or its future replacement, then add rule-level positive and negative tests before implementation.
