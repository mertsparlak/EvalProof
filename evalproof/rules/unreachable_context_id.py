"""Rule: rag.unreachable_context_id."""

from collections import defaultdict
from typing import Dict, List, Set

from evalproof.finding import Confidence, Finding, Location, Severity
from evalproof.rule_engine import Rule, ScanContext


RULE_ID = "rag.unreachable_context_id"
EVALUATION_ROLES = {"evaluation_dataset", "benchmark_dataset"}
RAG_ROLES = {"rag_document"}


class UnreachableContextIdRule(Rule):
    @property
    def id(self) -> str:
        return RULE_ID

    @property
    def title(self) -> str:
        return "Evaluation context ID is not reachable from the RAG corpus"

    @property
    def default_severity(self) -> str:
        return Severity.HIGH.value

    @property
    def description(self) -> str:
        return "Detect explicit evaluation context IDs that do not exist in discovered RAG artifacts."

    @property
    def artifact_roles(self) -> List[str]:
        return ["evaluation_dataset", "benchmark_dataset", "rag_document"]

    @property
    def tags(self) -> List[str]:
        return ["rag_integrity", "context_alignment", "reproducibility"]

    def evaluate(self, ctx: ScanContext) -> List[Finding]:
        rag_references = ctx.project_index.get_context_references(RAG_ROLES, include_lists=False, include_generic_id=True)
        if not rag_references:
            return []

        reachable_ids: Set[str] = {reference.value for _, reference in rag_references}
        rag_artifact_paths = sorted({row.artifact_path for row, _ in rag_references})
        searched_id_fields = sorted({reference.field_name for _, reference in rag_references})

        evaluation_references = ctx.project_index.get_context_references(EVALUATION_ROLES, include_lists=True)
        grouped_references: Dict[tuple[str, int], list] = defaultdict(list)
        for row, reference in evaluation_references:
            grouped_references[(row.artifact_path, row.row_num)].append((row, reference))

        findings: List[Finding] = []
        for (artifact_path, row_num), grouped in sorted(grouped_references.items()):
            missing_by_value = {}
            for _, reference in grouped:
                if reference.value not in reachable_ids:
                    missing_by_value.setdefault(reference.value, []).append(reference)

            if not missing_by_value:
                continue

            missing_references = [reference for references in missing_by_value.values() for reference in references]
            reference_fields = sorted({reference.field_name for reference in missing_references})
            missing_hashes = sorted({reference.value_hash for reference in missing_references})
            missing_count = len(missing_by_value)

            findings.append(
                Finding(
                    rule_id=self.id,
                    severity=self.default_severity,
                    confidence=Confidence.CONFIRMED.value,
                    title=self.title,
                    message=(
                        f"Evaluation sample in '{artifact_path}' (row {row_num}) references "
                        f"{missing_count} context ID(s) not found in the discovered RAG corpus."
                    ),
                    impact="Unreachable retrieval references make the evaluation context incomplete or unverifiable.",
                    recommendation="Restore the referenced RAG documents or regenerate the evaluation artifact with valid context IDs.",
                    locations=[Location(role="primary", path=artifact_path, row=row_num)],
                    evidence={
                        "evaluation_artifact": artifact_path,
                        "evaluation_row": row_num,
                        "reference_fields": reference_fields,
                        "missing_reference_count": missing_count,
                        "missing_reference_hashes": missing_hashes,
                        "rag_artifact_paths": rag_artifact_paths,
                        "searched_id_fields": searched_id_fields,
                    },
                )
            )

        return findings
