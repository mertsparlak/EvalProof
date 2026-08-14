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

## Recommended Next Rule Batch

The first new-rule slice is the evaluation trust chain:

1. `evaluation.sample_alignment_mismatch`
2. `dataset.label_inconsistency`
3. `evaluation.metric_out_of_bounds`

The sample alignment rule replaces the narrower `evaluation.unmatched_evaluation_sample_count` candidate. Count mismatch is one evidence subtype of sample alignment, alongside missing, unexpected, or duplicate explicit IDs.

These rules are promoted only after the shared Project Index contracts are implemented and each rule has positive, negative, evidence, and determinism tests.
## Dataset Integrity Candidates

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

Status: `promote`

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

Status: `promote`

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

Status: `promote`

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

Status: `promote`

Problem: evaluation prompt templates or rendered evaluation inputs still contain unresolved placeholders such as `{user_input}`, `{{ prompt }}`, or `${question}`.

Required evidence:

- prompt or evaluation artifact path
- line, row, or field location
- placeholder name
- placeholder syntax
- nearby snippet

Default confidence: `likely`

Default severity if promoted: `medium`

Default CI behavior: should not fail default CI unless later promoted to `high` for rendered evaluation inputs

False-positive risks:

- documentation examples
- intentionally literal braces
- templating instructions in prompt authoring docs

Promotion requirement: scope the rule to prompt templates and evaluation artifacts only.

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

### `rag.empty_or_corrupted_document`

Status: `promote`

Problem: RAG corpus artifacts referenced by evaluation are empty, whitespace-only, or unreadable enough to make retrieval-grounded evaluation untrustworthy.

Required evidence:

- RAG artifact path
- observed size or normalized text length
- corruption or parse diagnostic code when available

Default confidence: `confirmed`

Default severity if promoted: `medium`

Default CI behavior: should not fail default CI unless the document is explicitly referenced by evaluation artifacts

Relationship to diagnostics: parse failures remain diagnostics; this rule may emit only when the artifact role is RAG corpus and the empty/corrupted document affects evaluation trust.

### `rag.duplicate_chunk_in_corpus`

Status: `promote`

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

Status: `promote`

Problem: evaluation samples reference a `doc_id`, `context_id`, `source_id`, or similar retrieval context id that cannot be found in the RAG corpus artifacts.

Required evidence:

- evaluation artifact path and row
- referenced context id field
- referenced context id value or stable hash
- searched RAG id fields

Default confidence: `confirmed`

Default severity if promoted: `high`

Default CI behavior: can fail default CI

Promotion requirement: define canonical context-id aliases for evaluation rows and RAG documents.

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

## Reproducibility Candidates

### `reproducibility.non_deterministic_temperature_setting`

Status: `promote`

Problem: evaluation result or config artifacts specify stochastic generation settings without a seed or reproducibility control.

Required evidence:

- result or config artifact path
- temperature field and value
- missing seed field
- optional generation parameter object path

Default confidence: `likely`

Default severity if promoted: `medium`

Default CI behavior: should not fail default CI by default

False-positive risks:

- evaluations intentionally measuring stochastic behavior
- providers where seed is unavailable or unsupported

Promotion requirement: emit only when the artifact is evaluation-related and temperature is greater than 0.0.

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

## Rejected Or Deferred Themes

The following themes should not become rules without a new design review:

- broad dataset quality scoring
- subjective prompt quality scoring
- general repository-wide security scanning
- provider-specific model policy checks that require network freshness
- dynamic evaluation execution

These are constrained by [Design Principles](../00-product/design-principles.md) and [Non-Goals](../00-product/non-goals.md).

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