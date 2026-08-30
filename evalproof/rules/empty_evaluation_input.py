"""Rule: dataset.empty_evaluation_input."""

from collections import defaultdict
from typing import Dict, List, Tuple

from evalproof.finding import Confidence, Finding, Location, Severity
from evalproof.project_index import INPUT_FIELD_ALIASES
from evalproof.rule_engine import Rule, ScanContext


RULE_ID = "dataset.empty_evaluation_input"
MAX_EVIDENCE_ROWS = 20


class EmptyEvaluationInputRule(Rule):
    @property
    def id(self) -> str:
        return RULE_ID

    @property
    def title(self) -> str:
        return "Empty evaluation input detected"

    @property
    def default_severity(self) -> str:
        return Severity.HIGH.value

    @property
    def description(self) -> str:
        return "Detects evaluation rows whose explicit canonical input fields are all empty."

    @property
    def artifact_roles(self) -> List[str]:
        return ["evaluation_dataset", "benchmark_dataset"]

    @property
    def tags(self) -> List[str]:
        return ["dataset_integrity", "input_integrity", "evaluation_integrity"]

    def evaluate(self, ctx: ScanContext) -> List[Finding]:
        grouped: Dict[str, List[Tuple[int, str, List[str]]]] = defaultdict(list)
        for artifact in sorted(ctx.project_index.artifacts_by_path.values(), key=lambda item: item.path):
            if not {"evaluation_dataset", "benchmark_dataset"}.intersection(artifact.roles):
                continue
            for row in ctx.project_index.rows_by_artifact.get(artifact.path, []):
                empty_fields = self._empty_input_fields(row.row_data)
                if empty_fields:
                    grouped[artifact.path].append((row.row_num, row.row_hash, empty_fields))

        findings: List[Finding] = []
        for artifact_path, rows in sorted(grouped.items()):
            evidence_rows = rows[:MAX_EVIDENCE_ROWS]
            findings.append(
                Finding(
                    rule_id=self.id,
                    severity=self.default_severity,
                    confidence=Confidence.CONFIRMED.value,
                    title=self.title,
                    message=f"Artifact '{artifact_path}' contains {len(rows)} rows with empty evaluation inputs.",
                    impact="Empty evaluation inputs do not exercise the intended model behavior and can make reported metrics untrustworthy.",
                    recommendation="Populate each evaluation row with a non-empty canonical input or use an explicitly supported message-based schema.",
                    locations=[
                        Location(role="primary", path=artifact_path, row=row_num)
                        for row_num, _, _ in evidence_rows
                    ],
                    evidence={
                        "artifact_path": artifact_path,
                        "affected_count": len(rows),
                        "input_fields": sorted({field for _, _, fields in rows for field in fields}),
                        "row_locations": [
                            {"path": artifact_path, "row": row_num}
                            for row_num, _, _ in evidence_rows
                        ],
                        "row_hashes": [row_hash for _, row_hash, _ in evidence_rows],
                        "evidence_truncated": len(rows) > MAX_EVIDENCE_ROWS,
                    },
                )
            )
        return findings

    @staticmethod
    def _empty_input_fields(row_data) -> List[str]:
        if not isinstance(row_data, dict) or "messages" in row_data:
            return []
        present = [(field, row_data[field]) for field in INPUT_FIELD_ALIASES if field in row_data]
        if not present:
            return []
        if any(
            not (value is None or (isinstance(value, str) and not value.strip()))
            for _, value in present
        ):
            return []
        return [field for field, _ in present]
