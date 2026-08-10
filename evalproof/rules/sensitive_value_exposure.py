"""Rule: contamination.sensitive_value_exposure"""

hashlib = __import__("hashlib")
import re
from typing import List, Set, Tuple

from evalproof.finding import Finding, Location, Severity, Confidence
from evalproof.rule_engine import Rule, ScanContext


EMAIL_REGEX = re.compile(r"\b[a-zA-Z0-9._%+-]+@[a-zA-Z0-9.-]+\.[a-zA-Z]{2,}\b")
PHONE_REGEX = re.compile(r"\b(?:\+?\d{1,3}[-.\s]?)?\(?\d{3}\)?[-.\s]?\d{3}[-.\s]?\d{4}\b")
API_KEY_REGEX = re.compile(r"\b(?:api_key|apikey|secret|token|password)\s*[:=]\s*([^\s]{12,})", re.IGNORECASE)
PRIVATE_KEY_MARKER = "BEGIN PRIVATE KEY"


def redact_value(detector_type: str, val: str) -> str:
    digest = hashlib.sha256(val.encode("utf-8")).hexdigest()
    return f"<{detector_type}>:sha256:{digest}"


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

        for art in target_arts:
            text = art.read_text()
            lines = text.splitlines()

            for line_idx, line in enumerate(lines, start=1):
                # 1. Private key
                if PRIVATE_KEY_MARKER in line:
                    redacted = redact_value("private_key", PRIVATE_KEY_MARKER)
                    loc = Location(role="primary", path=art.path, line=line_idx)
                    findings.append(
                        Finding(
                            rule_id=self.id,
                            severity=self.default_severity,
                            confidence=Confidence.HEURISTIC.value,
                            title=self.title,
                            message=f"Private key detected at line {line_idx} in evaluation artifact '{art.path}'.",
                            impact="Sensitive data can make evaluation artifacts unsafe to share, store, or use in CI.",
                            recommendation="Remove or redact the value and replace it with a safe fixture.",
                            locations=[loc],
                            evidence={
                                "artifact_path": art.path,
                                "line_number": line_idx,
                                "detector_type": "private_key",
                                "redacted_value": redacted,
                            },
                        )
                    )

                # 2. API key / Secret / Token
                for match in API_KEY_REGEX.finditer(line):
                    secret_val = match.group(1)
                    redacted = redact_value("api_key", secret_val)
                    loc = Location(role="primary", path=art.path, line=line_idx)
                    findings.append(
                        Finding(
                            rule_id=self.id,
                            severity=self.default_severity,
                            confidence=Confidence.HEURISTIC.value,
                            title=self.title,
                            message=f"API key or secret-like value detected at line {line_idx} in evaluation artifact '{art.path}'.",
                            impact="Sensitive data can make evaluation artifacts unsafe to share, store, or use in CI.",
                            recommendation="Remove or redact the value and replace it with a safe fixture.",
                            locations=[loc],
                            evidence={
                                "artifact_path": art.path,
                                "line_number": line_idx,
                                "detector_type": "api_key",
                                "redacted_value": redacted,
                            },
                        )
                    )

                # 3. Email
                for match in EMAIL_REGEX.finditer(line):
                    email_val = match.group(0)
                    redacted = redact_value("email", email_val)
                    loc = Location(role="primary", path=art.path, line=line_idx)
                    findings.append(
                        Finding(
                            rule_id=self.id,
                            severity=self.default_severity,
                            confidence=Confidence.HEURISTIC.value,
                            title=self.title,
                            message=f"Email address detected at line {line_idx} in evaluation artifact '{art.path}'.",
                            impact="Sensitive data can make evaluation artifacts unsafe to share, store, or use in CI.",
                            recommendation="Remove or redact the value and replace it with a safe fixture.",
                            locations=[loc],
                            evidence={
                                "artifact_path": art.path,
                                "line_number": line_idx,
                                "detector_type": "email",
                                "redacted_value": redacted,
                            },
                        )
                    )

                # 4. Phone
                for match in PHONE_REGEX.finditer(line):
                    phone_val = match.group(0)
                    digits = re.sub(r"\D", "", phone_val)
                    if len(digits) >= 10:
                        redacted = redact_value("phone", phone_val)
                        loc = Location(role="primary", path=art.path, line=line_idx)
                        findings.append(
                            Finding(
                                rule_id=self.id,
                                severity=self.default_severity,
                                confidence=Confidence.HEURISTIC.value,
                                title=self.title,
                                message=f"Phone-like number detected at line {line_idx} in evaluation artifact '{art.path}'.",
                                impact="Sensitive data can make evaluation artifacts unsafe to share, store, or use in CI.",
                                recommendation="Remove or redact the value and replace it with a safe fixture.",
                                locations=[loc],
                                evidence={
                                    "artifact_path": art.path,
                                    "line_number": line_idx,
                                    "detector_type": "phone",
                                    "redacted_value": redacted,
                                },
                            )
                        )

        return findings
