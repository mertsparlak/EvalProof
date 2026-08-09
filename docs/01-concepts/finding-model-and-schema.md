# Finding Model And Schema

## Question

What is a finding, and what exact schema must every rule emit?

## Definition

A finding is a standardized, evidence-backed statement that a rule detected a trust issue in evaluation artifacts.

Findings are the product contract. Rules create findings. Reports render findings.

## Required Fields

Every finding must contain:

- `rule_id`: stable rule identifier.
- `severity`: impact level.
- `confidence`: certainty level based on evidence.
- `title`: short human-readable summary.
- `message`: concise explanation of what was found.
- `impact`: why the issue affects evaluation trust.
- `recommendation`: concrete action the user can take.
- `evidence`: structured evidence supporting the finding.
- `locations`: one or more artifact locations.
- `fingerprint`: deterministic identifier for the finding.

## Severity

Allowed severities:

- `critical`: likely invalidates evaluation trust.
- `high`: materially threatens trust and should be fixed before relying on results.
- `medium`: may affect trust or reproducibility and should be reviewed.
- `low`: informational trust issue with limited immediate impact.

Rules define default severity. Configuration may override severity as defined in [Configuration And Schema](../02-architecture/configuration-and-schema.md).

## Confidence

Allowed confidence values:

- `confirmed`: direct deterministic evidence proves the issue.
- `likely`: strong deterministic evidence exists, but interpretation depends on artifact role or metadata.
- `heuristic`: evidence is pattern-based and may require review.

The MVP should prefer `confirmed` and `likely`. `heuristic` findings must be used sparingly.

## Locations

A finding may involve multiple locations. Cross-artifact contamination findings must include all relevant locations when available.

Example location roles:

- `primary`
- `related`
- `source`
- `target`

Locations may include:

- path
- line
- column
- row
- JSON pointer
- field name

Fields that are unknown must be omitted rather than guessed.

## Evidence

Evidence must be structured and rule-specific. It must contain enough data for a user to verify the issue without rerunning the scanner.

Evidence requirements are defined in [Evidence Requirements](../03-rule-design/evidence-requirements.md).

## Fingerprint

The fingerprint must be deterministic for the same finding across repeated scans.

The MVP finding fingerprint is:

```text
sha256:<sha256 of canonical finding fingerprint payload>
```

The canonical finding fingerprint payload is a JSON object serialized with deterministic key ordering and no extra whitespace. It contains:

- `rule_id`
- `severity`
- `confidence`
- `locations`
- `evidence`

`locations` must include only stable location fields: `role`, `path`, `line`, `column`, `row`, `json_pointer`, and `field`.

`evidence` must include only stable evidence fields. It must not include timestamps, elapsed time, absolute paths, raw secret values, or display-only snippets when a stable hash is available.

It must not include timestamps, traversal order, absolute machine-specific paths, random IDs, or report formatting.

## Design Decisions

- Findings are the central output contract.
- Every finding must include evidence, impact, and recommendation.
- Cross-artifact findings support multiple locations.
- Confidence is explicit because not every static finding has the same certainty.
- Fingerprints are required for future baselines and deterministic reports, even though baseline mode is outside MVP.

## Open Questions

None.

## Dependencies

- [Design Principles](../00-product/design-principles.md)
- [Evidence Requirements](../03-rule-design/evidence-requirements.md)
- [JSON Report](../05-cli-and-reports/json-report.md)
- [Configuration And Schema](../02-architecture/configuration-and-schema.md)

## Future Considerations

Future report formats must render this schema rather than define their own finding shape.
