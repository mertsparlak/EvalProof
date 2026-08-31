"""Rule: contamination.untrusted_context_interpolation"""

import hashlib
import re
from typing import List, Set

from evalproof.finding import Finding, Location, Severity, Confidence
from evalproof.rule_engine import Rule, ScanContext


TARGET_PLACEHOLDERS: Set[str] = {
    "context",
    "retrieved_context",
    "documents",
    "docs",
    "chunks",
    "sources",
    "retrieval_results",
}

DELIMITER_MARKERS: List[str] = [
    "```",
    "<context>",
    "</context>",
    "<documents>",
    "</documents>",
    "BEGIN CONTEXT",
    "END CONTEXT",
    "BEGIN DOCUMENTS",
    "END DOCUMENTS",
]


class UntrustedContextInterpolationRule(Rule):
    @property
    def id(self) -> str:
        return "contamination.untrusted_context_interpolation"

    @property
    def title(self) -> str:
        return "Untrusted context interpolation without delimiters"

    @property
    def default_severity(self) -> str:
        return Severity.MEDIUM.value

    @property
    def description(self) -> str:
        return "Detects prompt templates that insert retrieved or user-provided context without clear delimiters in evaluation-related prompts."

    @property
    def artifact_roles(self) -> List[str]:
        return ["prompt_template"]

    @property
    def tags(self) -> List[str]:
        return ["contamination", "prompt_interpolation"]

    def evaluate(self, ctx: ScanContext) -> List[Finding]:
        findings: List[Finding] = []
        prompt_arts = ctx.project_index.artifacts_by_role.get("prompt_template", [])

        # Regex patterns for {name}, {{ name }}, ${name}, <name>
        pattern = re.compile(
            r"(?:\{\{\s*([a-zA-Z0-9_]+)\s*\}\}|\{([a-zA-Z0-9_]+)\}|\$\{([a-zA-Z0-9_]+)\}|<([a-zA-Z0-9_]+)>)"
        )

        for art in prompt_arts:
            text = art.read_text()
            lines = text.replace("\r\n", "\n").replace("\r", "\n").split("\n")

            for line_idx, line in enumerate(lines, start=1):
                matches = pattern.finditer(line)
                for match in matches:
                    var_name = next(g for g in match.groups() if g is not None)
                    if var_name.lower() in TARGET_PLACEHOLDERS:
                        # Check surrounding 3 lines before and 3 lines after
                        start_window = max(0, line_idx - 1 - 3)
                        end_window = min(len(lines), line_idx - 1 + 4)
                        window_lines = lines[start_window:end_window]
                        window_text = "\n".join(window_lines)

                        has_delimiter = any(delim in window_text for delim in DELIMITER_MARKERS)

                        if not has_delimiter:
                            loc = Location(role="primary", path=art.path, line=line_idx)
                            snippet = "sha256:" + hashlib.sha256(line.strip().encode("utf-8")).hexdigest()
                            finding = Finding(
                                rule_id=self.id,
                                severity=self.default_severity,
                                confidence=Confidence.HEURISTIC.value,
                                title=self.title,
                                message=f"Placeholder '{var_name}' at line {line_idx} in '{art.path}' interpolated without surrounding context delimiters.",
                                impact="Untrusted context can interfere with instructions and compromise evaluation validity.",
                                recommendation="Wrap untrusted context in explicit delimiters and instruct the model to treat it as data.",
                                locations=[loc],
                                evidence={
                                    "prompt_artifact": art.path,
                                    "variable_name": var_name,
                                    "line_number": line_idx,
                                    "snippet": snippet,
                                },
                            )
                            findings.append(finding)

        return findings
