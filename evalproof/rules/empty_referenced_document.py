"""Rule: rag.empty_referenced_document."""

from collections import defaultdict
from typing import Dict, List, Tuple

from evalproof.finding import Confidence, Finding, Location, Severity
from evalproof.project_index import extract_context_references
from evalproof.rule_engine import Rule, ScanContext


RULE_ID = "rag.empty_referenced_document"
EVALUATION_ROLES = {"evaluation_dataset", "benchmark_dataset"}
RAG_ROLES = {"rag_document"}
CONTENT_FIELD_ALIASES = ["text", "content", "document", "body", "chunk", "page_content"]


class EmptyReferencedDocumentRule(Rule):
    @property
    def id(self) -> str:
        return RULE_ID

    @property
    def title(self) -> str:
        return "Referenced RAG document is empty"

    @property
    def default_severity(self) -> str:
        return Severity.HIGH.value

    @property
    def description(self) -> str:
        return "Detects evaluation context references that resolve only to empty RAG records."

    @property
    def artifact_roles(self) -> List[str]:
        return ["evaluation_dataset", "benchmark_dataset", "rag_document"]

    @property
    def tags(self) -> List[str]:
        return ["rag_integrity", "context_alignment", "dataset_integrity"]

    def evaluate(self, ctx: ScanContext) -> List[Finding]:
        rag_rows_by_id: Dict[str, List[Tuple[object, object]]] = defaultdict(list)
        for artifact in sorted(ctx.project_index.artifacts_by_path.values(), key=lambda item: item.path):
            if not RAG_ROLES.intersection(artifact.roles):
                continue
            for row in ctx.project_index.rows_by_artifact.get(artifact.path, []):
                for reference in extract_context_references(
                    row.row_data,
                    include_lists=False,
                    include_generic_id=True,
                ):
                    rag_rows_by_id[reference.value].append((row, reference))

        if not rag_rows_by_id:
            return []

        evaluation_references = ctx.project_index.get_context_references(
            EVALUATION_ROLES,
            include_lists=True,
        )
        grouped: Dict[Tuple[str, int], List[object]] = defaultdict(list)
        for row, reference in evaluation_references:
            grouped[(row.artifact_path, row.row_num)].append(reference)

        findings: List[Finding] = []
        for (artifact_path, row_num), references in sorted(grouped.items()):
            empty_values = {}
            for reference in references:
                if reference.value in empty_values:
                    continue
                matches = rag_rows_by_id.get(reference.value, [])
                states = [self._content_state(row.row_data) for row, _ in matches]
                if matches and states and all(state == "empty" for state in states):
                    empty_values[reference.value] = matches

            if not empty_values:
                continue

            empty_matches_by_location = {
                (row.artifact_path, row.row_num): row
                for value in sorted(empty_values)
                for row, _ in empty_values[value]
            }
            empty_matches = [
                (row, None)
                for _, row in sorted(empty_matches_by_location.items())
            ]
            findings.append(
                Finding(
                    rule_id=self.id,
                    severity=self.default_severity,
                    confidence=Confidence.CONFIRMED.value,
                    title=self.title,
                    message=(
                        f"Evaluation sample in '{artifact_path}' (row {row_num}) references "
                        f"{len(empty_values)} RAG document(s) whose observed content is empty."
                    ),
                    impact="An explicitly referenced RAG document contributes no usable context, making the evaluation context incomplete or unverifiable.",
                    recommendation="Populate the referenced RAG record or regenerate the evaluation artifact with a valid context reference.",
                    locations=[
                        Location(role="primary", path=artifact_path, row=row_num),
                        *[
                            Location(role="related", path=row.artifact_path, row=row.row_num)
                            for row, _ in empty_matches
                        ],
                    ],
                    evidence={
                        "evaluation_artifact": artifact_path,
                        "evaluation_row": row_num,
                        "reference_fields": sorted({reference.field_name for reference in references if reference.value in empty_values}),
                        "empty_reference_count": len(empty_values),
                        "empty_reference_hashes": sorted(
                            {reference.value_hash for reference in references if reference.value in empty_values}
                        ),
                        "rag_artifact_paths": sorted({row.artifact_path for row, _ in empty_matches}),
                        "rag_row_locations": [
                            {"path": row.artifact_path, "row": row.row_num}
                            for row, _ in empty_matches
                        ],
                        "content_fields": sorted(
                            {
                                field
                                for row, _ in empty_matches
                                for field in CONTENT_FIELD_ALIASES
                                if isinstance(row.row_data, dict) and field in row.row_data
                            }
                        ),
                    },
                )
            )
        return findings

    @staticmethod
    def _content_state(row_data) -> str | None:
        if not isinstance(row_data, dict):
            return None
        present = [(field, row_data[field]) for field in CONTENT_FIELD_ALIASES if field in row_data]
        if not present:
            return None
        if any(isinstance(value, str) and value.strip() for _, value in present):
            return "nonempty"
        if all(value is None or (isinstance(value, str) and not value.strip()) for _, value in present):
            return "empty"
        return None
