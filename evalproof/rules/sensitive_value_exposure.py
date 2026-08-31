"""Rule: contamination.sensitive_value_exposure"""

import hashlib
import re
from typing import Any, Dict, List

from evalproof.finding import Confidence, Finding, Location, Severity
from evalproof.rule_engine import Rule, ScanContext
from evalproof.rules._evidence import cap_evidence_items

EMAIL_REGEX = re.compile(r"\b[a-zA-Z0-9._%+-]+@[a-zA-Z0-9.-]+\.[a-zA-Z]{2,}\b")
# Require separators between the three phone groups.  The previous optional
# country-prefix form could consume the first digits of arithmetic values such
# as ``60000-5000`` and classify them as phone numbers.
PHONE_REGEX = re.compile(
    r"\b(?:\+\d{1,3}[-.\s])?\(?\d{3}\)?[-.\s]\d{3}[-.\s]\d{4}\b"
)
API_KEY_REGEX = re.compile(r"\b(?:api_key|apikey|secret|token|password)\s*[:=]\s*([^\s]{12,})", re.IGNORECASE)
PRIVATE_KEY_MARKER = "BEGIN PRIVATE KEY"


def redact_value(detector_type: str, val: str) -> str:
    digest = hashlib.sha256(val.encode("utf-8")).hexdigest()
    return f"<{detector_type}>:sha256:{digest}"


def _string_leaves(value):
    if isinstance(value, str):
        yield value
    elif isinstance(value, dict):
        for key in sorted(value):
            yield from _string_leaves(value[key])
    elif isinstance(value, list):
        for child in value:
            yield from _string_leaves(child)


def _text_positions(art, index):
    if art.format == "parquet":
        for row in index.rows_by_artifact.get(art.path, []):
            for text in _string_leaves(row.row_data):
                for line in text.splitlines():
                    yield row.row_num, line
    else:
        lines = art.read_text().replace("\r\n", "\n").replace("\r", "\n").split("\n")
        yield from enumerate(lines, start=1)


class SensitiveValueExposureRule(Rule):
    @property
    def id(self) -> str:
        return "contamination.sensitive_value_exposure"

    @property
    def title(self) -> str:
        return "Sensitive value exposure in evaluation artifact"

    @property
    def default_severity(self) -> str:
        return Severity.MEDIUM.value

    @property
    def description(self) -> str:
        return "Detects secret-like or PII-like values inside evaluation artifacts."

    @property
    def artifact_roles(self) -> List[str]:
        return ["evaluation_dataset", "evaluation_result", "benchmark_dataset", "prompt_template", "rag_document"]

    @property
    def tags(self) -> List[str]:
        return ["contamination", "sensitive_exposure"]

    def evaluate(self, ctx: ScanContext) -> List[Finding]:
        findings: List[Finding] = []
        eval_roles = set(self.artifact_roles)
        target_arts = [a for a in ctx.artifacts.values() if any(r in eval_roles for r in a.roles)]

        for art in sorted(target_arts, key=lambda item: item.path):
            matches: Dict[str, Dict[str, Any]] = {}
            position_key = "row" if art.format == "parquet" else "line"

            def add_match(detector_type: str, line_number: int, value: str) -> None:
                group = matches.setdefault(detector_type, {"count": 0, "lines": set(), "redacted": set()})
                group["count"] += 1
                group["lines"].add(line_number)
                group["redacted"].add(redact_value(detector_type, value))

            for line_idx, line in _text_positions(art, ctx.project_index):
                if PRIVATE_KEY_MARKER in line:
                    add_match("private_key", line_idx, PRIVATE_KEY_MARKER)
                for match in API_KEY_REGEX.finditer(line):
                    add_match("api_key", line_idx, match.group(1))
                for match in EMAIL_REGEX.finditer(line):
                    add_match("email", line_idx, match.group(0))
                for match in PHONE_REGEX.finditer(line):
                    phone_val = match.group(0)
                    if len(re.sub(r"\D", "", phone_val)) >= 10:
                        add_match("phone", line_idx, phone_val)

            for detector_type in sorted(matches):
                group = matches[detector_type]
                all_locations = [{position_key: line} for line in sorted(group["lines"])]
                all_redacted = sorted(group["redacted"])
                sample_locations, locations_truncated = cap_evidence_items(all_locations)
                redacted_values, values_truncated = cap_evidence_items(all_redacted)
                evidence_truncated = locations_truncated or values_truncated
                findings.append(
                    Finding(
                        rule_id=self.id,
                        severity=self.default_severity,
                        confidence=Confidence.HEURISTIC.value,
                        title=self.title,
                        message=(
                            f"{group['count']} {detector_type} exposure(s) detected in "
                            f"evaluation artifact '{art.path}'."
                        ),
                        impact="Sensitive data can make evaluation artifacts unsafe to share, store, or use in CI.",
                        recommendation="Remove or redact the values and replace them with safe fixtures.",
                        locations=[Location(role="primary", path=art.path, **all_locations[0])],
                        evidence={
                            "artifact_path": art.path,
                            "detector_type": detector_type,
                            "exposure_count": group["count"],
                            "distinct_value_count": len(all_redacted),
                            "sample_locations": sample_locations,
                            "redacted_values": redacted_values,
                            "evidence_truncated": evidence_truncated,
                        },
                    )
                )

        return findings
