# Contamination Rules

## Question

Which contamination rules exist in the current scanner?

## Rule Set

EvalProof includes only the rules in this document.

## Rules

### `contamination.train_eval_overlap`

Detects exact normalized records that appear in both training datasets and evaluation or benchmark datasets.

Default severity: `critical`

Default confidence: `confirmed`

Required evidence:

- training artifact path and row where available
- evaluation or benchmark artifact path and row where available
- normalized record hash
- overlap count

Impact: evaluation results may be inflated because evaluation samples may have appeared in training data.

Recommendation: remove overlapping records from one split and regenerate dataset fingerprints.

### `contamination.train_eval_near_duplicate`

Detects near-duplicate records between training datasets and evaluation or benchmark datasets using the similarity engine defined in [Project Index](../02-architecture/project-index.md).

Default severity: `high`

Default confidence: `likely`

Default CI behavior: this rule can fail CI under the default `fail_on: high`.

Required evidence:

- training artifact path and row where available
- evaluation or benchmark artifact path and row where available
- Jaccard similarity score
- configured similarity threshold

Applicability: this rule uses `similarity.focus_roles` and `similarity.focus_fields` to avoid comparing static system instructions when structured chat-like rows are present.

Impact: evaluation results may be inflated because near-duplicate evaluation samples may have appeared in training data.

Recommendation: remove or rewrite near-duplicate records, then rerun the scan.

### `contamination.duplicate_eval_sample`

Detects duplicate normalized records within evaluation or benchmark datasets.

Default severity: `high`

Default confidence: `confirmed`

Required evidence:

- artifact path
- duplicate row locations where available
- normalized record hash
- duplicate count

Impact: duplicated samples can overweight repeated cases and distort metrics.

Recommendation: deduplicate the evaluation artifact or justify intentional weighting outside the MVP scanner.

### `contamination.duplicate_eval_near_duplicate`

Detects near-duplicate records within evaluation or benchmark datasets.

Default severity: `medium`

Default confidence: `likely`

Default CI behavior: this rule must not fail CI under the default `fail_on: high`.

Required evidence:

- artifact path
- related row locations where available
- Jaccard similarity score
- configured similarity threshold

Impact: near-duplicate samples can overweight repeated cases and distort metrics.

Recommendation: deduplicate or rewrite near-duplicate evaluation samples.

### `contamination.duplicate_train_sample`

Detects exact normalized duplicate records within training datasets.

Default severity: `medium`

Default confidence: `confirmed`

Default CI behavior: this rule must not fail CI under the default `fail_on: high`.

Required evidence:

- artifact path
- duplicate row locations where available
- normalized record hash
- duplicate count

Impact: duplicated training rows can waste training budget and increase memorization risk.

Recommendation: deduplicate the training artifact unless the weighting is intentional.

### `contamination.duplicate_train_near_duplicate`

Detects near-duplicate records within training datasets.

Default severity: `low`

Default confidence: `likely`

Default CI behavior: this rule must not fail CI under the default `fail_on: high`.

Required evidence:

- artifact path
- related row locations where available
- Jaccard similarity score
- configured similarity threshold

Impact: near-duplicate training rows can increase overfitting and memorization risk.

Recommendation: review near-duplicate training rows and deduplicate when they are accidental.

### `contamination.rag_answer_leakage`

Detects evaluation answers or gold labels that appear in RAG corpus artifacts using exact or normalized text containment.

Default severity: `high`

Default confidence: `likely`

Required evidence:

- evaluation artifact path and answer field when available
- RAG artifact path and location when available
- matched normalized text or redacted/hash representation if sensitive

Applicability: this rule may use only answer-like fields extracted by the project index. If no canonical answer field is available, the rule must not emit a finding for that row.

Matching behavior:

- normalize extracted answers and RAG text using plain text normalization from [Project Index](../02-architecture/project-index.md)
- emit a finding only when the normalized answer is an exact substring of normalized RAG text
- skip answers ignored by project-index answer extraction
- emit at most one finding per answer and RAG artifact pair, using the first deterministic match location when multiple locations exist

Impact: the system may answer by copying leaked gold answers from retrieval context.

Recommendation: remove leaked answers from the RAG corpus, change the evaluation case, or mark the case as retrieval-grounded rather than independent.

### `contamination.missing_repro_metadata`

Detects evaluation result artifacts missing required reproducibility metadata.

Default severity: `high`

Default confidence: `confirmed`

Required evidence:

- result artifact path
- missing metadata fields

Required MVP metadata fields:

- model id
- generation parameters
- prompt fingerprint or prompt version
- dataset fingerprint or dataset version
- metric name
- metric definition or threshold
- timestamp

Canonical metadata extraction is defined in [Project Index](../02-architecture/project-index.md). Fields that cannot be mapped through the MVP canonical metadata contract are treated as missing.

Impact: the result cannot be reliably reproduced or compared later.

Recommendation: add the missing metadata to the result artifact or regenerate the result with metadata capture enabled.

### `contamination.fingerprint_mismatch`

Detects when a referenced prompt or dataset fingerprint does not match any available comparable artifact.

Default severity: `high`

Default confidence: `confirmed`

Required evidence:

- result artifact path
- referenced fingerprint
- candidate artifact paths
- artifact type

A matching artifact is determined by the computed fingerprint rules in [Project Index](../02-architecture/project-index.md). Matching artifacts are treated as one content-equivalent group. If no artifact matches, this rule emits one result-centered finding. It must not emit one mismatch finding per unrelated candidate artifact.

Impact: the result may not correspond to the available prompt or dataset artifact.

Recommendation: update references, restore the correct artifact version, or regenerate the result.

### `evaluation.sample_alignment_mismatch`

Detects count or explicit sample-ID mismatches between an evaluation result and its fingerprint-matched evaluation or benchmark dataset.

Default severity: `high`

Default confidence: `confirmed`

Required evidence:

- result artifact path
- matched dataset artifact path
- matched dataset artifact paths
- dataset fingerprint
- dataset and result counts
- mismatch types
- limited missing, unexpected, or duplicate IDs when available

Applicability:

- the result must reference a dataset fingerprint matching one or more evaluation or benchmark artifacts
- both artifacts must expose observable row collections
- sample ID comparison runs only when every row on both sides exposes an ID alias
- positional row matching and order differences are not findings

MVP sample ID aliases are `id`, `sample_id`, `example_id`, `record_id`, and `case_id`.

Impact: reported metrics may have been computed over a different or incomplete set of evaluation samples.

Recommendation: regenerate the result with the fingerprint-matched dataset and preserve stable sample IDs.

### `dataset.label_inconsistency`

Detects different target values assigned to the same normalized evaluation or benchmark input and context.

Default severity: `high`

Default confidence: `confirmed`

Required evidence:

- artifact paths
- normalized input hash
- input field
- target fields
- conflicting target count
- hashed target values
- row locations

Canonical input aliases are `prompt`, `question`, and `input`. Canonical target aliases are the answer aliases defined by [Project Index](../02-architecture/project-index.md). Context-bearing fields are included in the identity when present so examples with different contexts are not incorrectly grouped.

Impact: conflicting targets make benchmark labels ambiguous and reduce confidence in evaluation results.

Recommendation: resolve the annotation conflict or include the missing context that distinguishes the examples.

### `evaluation.metric_out_of_bounds`

Detects known evaluation metrics whose numeric values violate an explicit unit or bounds contract.

Default severity: `high`

Default confidence: `confirmed`

Required evidence:

- result artifact path
- metric name
- observed value
- accepted bounds
- explicit unit or bounds evidence
- metric field path

The rule checks only the known metric names and explicit scale records defined by [Project Index](../02-architecture/project-index.md). Unknown metrics and values without a unit or numeric bounds do not produce findings.

Impact: the evaluation result contains a mathematically invalid metric value and cannot be trusted as reported.

Recommendation: correct the metric computation or declare the correct unit and bounds before publishing the result.

### `rag.unreachable_context_id`

Detects explicit evaluation or benchmark context references that are absent from the discovered RAG artifact IDs.

Default severity: `high`

Default confidence: `confirmed`

Default CI behavior: this rule can fail CI under the default `fail_on: high` policy.

Applicability:

- evaluation rows use the explicit context reference fields defined by [Project Index](../02-architecture/project-index.md)
- RAG rows use the explicit scalar ID fields defined by [Project Index](../02-architecture/project-index.md)
- only top-level structured fields are inspected
- file names, free-text content, nested metadata, and inferred IDs are ignored
- a missing RAG artifact or RAG artifact without explicit IDs produces no finding

The rule supports scalar evaluation references and explicit evaluation ID lists. IDs are trimmed, remain case-sensitive, and are compared as normalized scalar values. Evaluation sample IDs in the `id` field are not treated as context references.

Required evidence:

- evaluation artifact path and row
- reference field names
- count of missing references
- stable hashes of missing references
- searched RAG artifact paths
- searched RAG ID fields

Raw context ID values must not be written to evidence, messages, or recommendations.

Impact: unreachable retrieval references make evaluation context incomplete or unverifiable.

Recommendation: restore the referenced RAG documents or regenerate the evaluation artifact with valid context IDs.

### `contamination.untrusted_context_interpolation`

Detects prompt templates that appear to insert retrieved or user-provided context without clear delimiters in evaluation-related prompts.

Default severity: `medium`

Default confidence: `heuristic`

Default CI behavior: this rule must not fail CI under the MVP default `fail_on: high`.

Required evidence:

- prompt artifact path
- variable or placeholder name
- nearby redacted snippet

Applicability: this rule applies only to prompt artifacts that are evaluation-related by role, path, or explicit configuration. It must not scan arbitrary application prompts as a general prompt-quality rule.

MVP detection pattern:

- detect placeholders named `context`, `retrieved_context`, `documents`, `docs`, `chunks`, `sources`, or `retrieval_results`
- supported placeholder syntaxes are `{name}`, `{{ name }}`, `${name}`, and `<name>`
- emit a finding only when no delimiter marker appears within three lines before the placeholder and three lines after the placeholder

Delimiter markers are:

- triple backticks
- `<context>` and `</context>`
- `<documents>` and `</documents>`
- `BEGIN CONTEXT`
- `END CONTEXT`
- `BEGIN DOCUMENTS`
- `END DOCUMENTS`

Impact: untrusted context can interfere with instructions and compromise evaluation validity.

Recommendation: wrap untrusted context in explicit delimiters and instruct the model to treat it as data.

### `contamination.sensitive_value_exposure`

Detects secret-like or PII-like values inside evaluation artifacts.

Default severity: `medium`

Default confidence: `heuristic`

Default CI behavior: this rule must not fail CI under the MVP default `fail_on: high`.

Required evidence:

- artifact path
- location
- detector type
- redacted value or stable hash

Applicability: this rule applies only to evaluation artifacts and artifacts directly referenced by evaluation artifacts. It must not become a repository-wide general secret scanner.

MVP detector types:

- `email`: text matching a conventional email address pattern
- `phone`: text matching a phone-like pattern with at least 10 digits after removing separators
- `api_key`: text containing `api_key`, `apikey`, `secret`, `token`, or `password` followed by `=`, `:`, or whitespace and then at least 12 non-whitespace characters
- `private_key`: text containing `BEGIN PRIVATE KEY`

Evidence must redact matched values. Redaction format is `<detector_type>:sha256:<sha256 of matched value>`.

Impact: sensitive data can make evaluation artifacts unsafe to share, store, or use in CI.

Recommendation: remove or redact the value and replace it with a safe fixture.

### `prompt.unresolved_placeholder`

Detects template-like placeholder patterns left in rendered evaluation or benchmark input fields.

Default severity: `medium`

Default confidence: `heuristic`

Default CI behavior: this rule must not fail CI under the MVP default `fail_on: high`.

Applicability:

- `evaluation_dataset` and `benchmark_dataset` artifacts only
- string values in the canonical `prompt`, `question`, and `input` fields only
- `prompt_template` artifacts, training datasets, message lists, nested context, and free-text files are excluded

Supported placeholder patterns are `{variable}`, `{{ variable }}`, and `${variable}`. The rule reports one finding per affected artifact row and input field, grouping all detected patterns in that field.

Required evidence:

- artifact path
- row and field location
- placeholder syntax classes
- stable hash of the normalized input
- detected placeholder count

Raw input values and placeholder names must not be written to evidence.

This is a heuristic rule because static scanning cannot prove whether a placeholder-like value was rendered before model execution.

Impact: an evaluation may use an unresolved template value instead of the intended rendered input, reducing trust in the result.

Recommendation: render the evaluation input before scanning and verify that template variables are populated.

### `dataset.sample_id_collision`

Detects one explicit sample ID assigned to multiple rows within the same evaluation or benchmark artifact.

Default severity: `high`

Default confidence: `confirmed`

Default CI behavior: this rule can fail CI under the default `fail_on: high`.

Applicability:

- `evaluation_dataset` and `benchmark_dataset` artifacts only
- the artifact must expose scalar values through the sample ID aliases defined in [Project Index](../02-architecture/project-index.md)
- IDs are trimmed and case-sensitive
- comparisons are scoped to one artifact; IDs from separate artifacts are not assumed to share a namespace
- booleans and empty values are ignored

Required evidence:

- artifact path
- sample ID field names
- stable sample ID hash
- row locations
- row hashes
- duplicate count
- distinct content count

Raw sample IDs and row contents must not be written to evidence, messages, or recommendations.

Impact: duplicate identities make sample-level results ambiguous and can duplicate or overwrite evaluation results.

Recommendation: assign one stable, unique sample ID to each evaluation row and regenerate dependent result artifacts.

### `dataset.empty_evaluation_input`

Detects evaluation or benchmark rows where all present canonical input fields are explicitly empty.

Default severity: `high`

Default confidence: `confirmed`

Default CI behavior: this rule can fail CI under the default `fail_on: high`.

Applicability:

- `evaluation_dataset` and `benchmark_dataset` artifacts only
- canonical fields are `prompt`, `question`, and `input`
- at least one canonical field must be present
- all present canonical fields must be `null`, empty, or whitespace-only strings
- rows containing a `messages` field are excluded because message-list schemas are outside this rule's contract
- unsupported input value types and rows without canonical input fields are ignored

The rule emits one finding per artifact and includes at most 20 row locations in evidence. The total affected row count is always included.

Required evidence:

- artifact path
- affected row count
- input field names
- limited row locations
- row hashes
- whether evidence locations were truncated

Raw input values must not be written to evidence, messages, or recommendations.

Impact: empty evaluation inputs do not exercise the intended model behavior and can make reported metrics untrustworthy.

Recommendation: populate each evaluation row with a non-empty canonical input or use an explicitly supported message-based schema.

## Design Decisions

- The rule set is intentionally focused on evaluation trust.
- Exact deterministic contamination rules have higher priority than near-duplicate, prompt, or security checks.
- Near-duplicate rules are similarity-based, evidence-backed findings with explicit Jaccard scores and configured thresholds.
- Heuristic rules are included only when they directly affect evaluation trust.
- Rules outside this document are not part of the MVP.

## Open Questions

None.

## Dependencies

- [Evaluation Contamination](../01-concepts/evaluation-contamination.md)
- [Finding Model And Schema](../01-concepts/finding-model-and-schema.md)
- [Project Index](../02-architecture/project-index.md)
- [Evidence Requirements](evidence-requirements.md)

## Future Considerations

SARIF-specific rule metadata, framework-specific result parsers, and dynamic red-team checks are outside the current scope.

