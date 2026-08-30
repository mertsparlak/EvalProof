"""Rule: dataset.partial_sample_id_coverage."""

from typing import List

from evalproof.finding import Confidence, DiagnosticCode, Finding, Location, Severity
from evalproof.project_index import SAMPLE_ID_FIELD_ALIASES, extract_scalar_field
from evalproof.rule_engine import Rule, ScanContext
from evalproof.rules._evidence import MAX_RELATED_EVIDENCE, cap_evidence_items


RULE_ID = "dataset.partial_sample_id_coverage"
INCOMPLETE_INDEX_CODES = {
    DiagnosticCode.ARTIFACT_PARSE_FAILED.value,
    DiagnosticCode.ARTIFACT_ROW_PARSE_FAILED.value,
    DiagnosticCode.ARTIFACT_ROW_LIMIT_REACHED.value,
    DiagnosticCode.ARTIFACT_FILE_SIZE_LIMIT_EXCEEDED.value,
}


class PartialSampleIdCoverageRule(Rule):
    @property
    def id(self) -> str:
        return RULE_ID

    @property
    def title(self) -> str:
        return "Partial sample ID coverage detected"

    @property
    def default_severity(self) -> str:
        return Severity.MEDIUM.value

    @property
    def description(self) -> str:
        return "Detects evaluation or benchmark artifacts where only some indexed rows have an explicit sample ID."

    @property
    def artifact_roles(self) -> List[str]:
        return ["evaluation_dataset", "benchmark_dataset"]

    @property
    def tags(self) -> List[str]:
        return ["dataset_integrity", "sample_identity", "evaluation_integrity"]

    def evaluate(self, ctx: ScanContext) -> List[Finding]:
        findings: List[Finding] = []
        for artifact in sorted(ctx.project_index.artifacts_by_path.values(), key=lambda item: item.path):
            if not {"evaluation_dataset", "benchmark_dataset"}.intersection(artifact.roles):
                continue
            if self._has_incomplete_index(ctx, artifact.path, artifact.diagnostics):
                continue

            rows = sorted(
                ctx.project_index.rows_by_artifact.get(artifact.path, []),
                key=lambda row: row.row_num,
            )
            if not rows:
                continue

            identified_rows = []
            missing_rows = []
            sample_id_fields = set()
            for row in rows:
                extracted = extract_scalar_field(row.row_data, SAMPLE_ID_FIELD_ALIASES)
                if extracted is None:
                    missing_rows.append(row)
                    continue
                field_name, _ = extracted
                sample_id_fields.add(field_name)
                identified_rows.append(row)

            if not identified_rows or not missing_rows:
                continue

            missing_locations, locations_truncated = cap_evidence_items(
                [{"path": artifact.path, "row": row.row_num} for row in missing_rows]
            )
            missing_hashes, hashes_truncated = cap_evidence_items(
                [row.row_hash for row in missing_rows]
            )
            evidence_truncated = locations_truncated or hashes_truncated
            findings.append(
                Finding(
                    rule_id=self.id,
                    severity=self.default_severity,
                    confidence=Confidence.CONFIRMED.value,
                    title=self.title,
                    message=(
                        f"Artifact '{artifact.path}' has sample IDs on {len(identified_rows)} of "
                        f"{len(rows)} indexed rows."
                    ),
                    impact=(
                        "Partial sample identity coverage prevents complete row-level alignment "
                        "between evaluation data and dependent result artifacts."
                    ),
                    recommendation=(
                        "Assign a stable sample ID to every evaluation row and regenerate dependent "
                        "result artifacts."
                    ),
                    locations=[
                        Location(role="primary", path=artifact.path, row=row.row_num)
                        for row in missing_rows[:MAX_RELATED_EVIDENCE]
                    ],
                    evidence={
                        "artifact_path": artifact.path,
                        "row_count": len(rows),
                        "identified_count": len(identified_rows),
                        "missing_id_count": len(missing_rows),
                        "coverage_ratio": round(len(identified_rows) / len(rows), 4),
                        "sample_id_fields": sorted(sample_id_fields),
                        "missing_row_locations": missing_locations,
                        "missing_row_hashes": missing_hashes,
                        "evidence_truncated": evidence_truncated,
                    },
                )
            )
        return findings

    @staticmethod
    def _has_incomplete_index(ctx: ScanContext, artifact_path: str, artifact_diagnostics) -> bool:
        diagnostics = list(artifact_diagnostics)
        diagnostics.extend(
            diagnostic
            for diagnostic in ctx.project_index.diagnostics
            if diagnostic.path == artifact_path
        )
        return any(diagnostic.code in INCOMPLETE_INDEX_CODES for diagnostic in diagnostics)
