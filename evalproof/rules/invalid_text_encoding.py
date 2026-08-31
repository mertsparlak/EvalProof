"""Report byte-level defects in declared text datasets."""

from evalproof.finding import Finding, Location
from evalproof.rule_engine import Rule


class InvalidTextEncodingRule(Rule):
    @property
    def id(self):
        return "dataset.invalid_text_encoding"

    @property
    def title(self):
        return "Dataset contains unsupported text bytes"

    @property
    def description(self):
        return "Detects invalid UTF-8 or actual NUL bytes in text datasets before record comparisons."

    @property
    def default_severity(self):
        return "medium"

    @property
    def artifact_roles(self):
        return ["training_dataset", "evaluation_dataset", "benchmark_dataset"]

    @property
    def tags(self):
        return ["dataset_integrity", "encoding"]

    def evaluate(self, ctx):
        findings = []
        for path, facts in sorted(ctx.project_index.encoding_issues.items()):
            defects = []
            if facts["invalid_utf8_range"] is not None:
                defects.append("invalid UTF-8")
            if facts["nul_byte_count"]:
                defects.append("NUL bytes")
            findings.append(Finding(
                rule_id=self.id, title=self.title, severity=self.default_severity,
                confidence="confirmed", message="Dataset contains " + " and ".join(defects) + "; text indexing was skipped.",
                impact="Reliable text parsing and record comparison are unavailable for this artifact.",
                recommendation="Verify the intended source encoding, export clean UTF-8 without unexpected NUL bytes, and rescan. Do not repair by guessing an encoding.",
                locations=[Location(role="primary", path=path)], evidence=dict(facts),
            ))
        return findings
