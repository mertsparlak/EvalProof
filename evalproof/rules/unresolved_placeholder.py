"""Rule: prompt.unresolved_placeholder."""

import hashlib
import re
from typing import List, Optional, Tuple

from evalproof.finding import Confidence, Finding, Location, Severity
from evalproof.project_index import normalize_plain_text
from evalproof.rule_engine import Rule, ScanContext


INPUT_FIELD_ALIASES = ["prompt", "question", "input"]
PLACEHOLDER_PATTERN = re.compile(
    r"\{\{\s*([A-Za-z_][A-Za-z0-9_]*)\s*\}\}"
    r"|\$\{\s*([A-Za-z_][A-Za-z0-9_]*)\s*\}"
    r"|(?<!\{)\{([A-Za-z_][A-Za-z0-9_]*)\}(?!\})"
)


def _input_field(row_data: object) -> Optional[Tuple[str, str]]:
    if not isinstance(row_data, dict):
        return None

    for field_name in INPUT_FIELD_ALIASES:
        value = row_data.get(field_name)
        if isinstance(value, str) and value.strip():
            return field_name, value
    return None


def _syntax_class(raw_match: str) -> str:
    if raw_match.startswith("{{"):
        return "double_brace"
    if raw_match.startswith("${"):
        return "dollar_brace"
    return "single_brace"


class UnresolvedPlaceholderRule(Rule):
    @property
    def id(self) -> str:
        return "prompt.unresolved_placeholder"

    @property
    def title(self) -> str:
        return "Placeholder pattern remains in evaluation input"

    @property
    def default_severity(self) -> str:
        return Severity.MEDIUM.value

    @property
    def description(self) -> str:
        return "Detects template-like placeholder patterns left in rendered evaluation or benchmark input fields."

    @property
    def artifact_roles(self) -> List[str]:
        return ["evaluation_dataset", "benchmark_dataset"]

    @property
    def tags(self) -> List[str]:
        return ["prompt_integrity", "evaluation_integrity"]

    def evaluate(self, ctx: ScanContext) -> List[Finding]:
        findings: List[Finding] = []

        for artifact in sorted(
            ctx.project_index.artifacts_by_path.values(),
            key=lambda item: item.path,
        ):
            if not {"evaluation_dataset", "benchmark_dataset"}.intersection(artifact.roles):
                continue

            for row in ctx.project_index.rows_by_artifact.get(artifact.path, []):
                input_field = _input_field(row.row_data)
                if input_field is None:
                    continue

                field_name, input_value = input_field
                matches = list(PLACEHOLDER_PATTERN.finditer(input_value))
                if not matches:
                    continue

                normalized_input = normalize_plain_text(input_value)
                input_hash = hashlib.sha256(normalized_input.encode("utf-8")).hexdigest()
                syntax_classes = sorted({_syntax_class(match.group(0)) for match in matches})

                findings.append(
                    Finding(
                        rule_id=self.id,
                        severity=self.default_severity,
                        confidence=Confidence.HEURISTIC.value,
                        title=self.title,
                        message=(
                            f"Detected {len(matches)} placeholder pattern(s) in "
                            f"field '{field_name}' at row {row.row_num}."
                        ),
                        impact=(
                            "The evaluation may use an unresolved template value instead of "
                            "the intended rendered input, reducing trust in the result."
                        ),
                        recommendation=(
                            "Render the evaluation input before scanning and verify that "
                            "template variables are populated."
                        ),
                        locations=[
                            Location(
                                role="primary",
                                path=artifact.path,
                                row=row.row_num,
                                field=field_name,
                            )
                        ],
                        evidence={
                            "artifact_path": artifact.path,
                            "row": row.row_num,
                            "field": field_name,
                            "input_hash": f"sha256:{input_hash}",
                            "syntax_classes": syntax_classes,
                            "detected_count": len(matches),
                        },
                    )
                )

        return findings
