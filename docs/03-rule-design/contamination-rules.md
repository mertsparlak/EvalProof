# Contamination Rules

## Question

Which contamination rules exist in the MVP?

## Rule Set

The MVP includes only the rules in this document.

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

Detects mismatch between referenced prompt or dataset fingerprints and available artifact fingerprints when both sides provide comparable values.

Default severity: `high`

Default confidence: `confirmed`

Required evidence:

- result or config artifact path
- referenced fingerprint
- computed or declared artifact fingerprint
- related artifact path

Artifact fingerprint computation is defined in [Project Index](../02-architecture/project-index.md). This rule must not emit a finding when either side lacks a comparable fingerprint.

Impact: the result may not correspond to the available prompt or dataset artifact.

Recommendation: update references, restore the correct artifact version, or regenerate the result.

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

## Design Decisions

- The MVP rule set is intentionally small.
- Exact deterministic contamination rules have higher priority than heuristic prompt or security checks.
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

Near-duplicate contamination, SARIF-specific rule metadata, framework-specific result parsers, and dynamic red-team checks are outside MVP.
