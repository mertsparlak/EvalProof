"""Rule: rag.empty_or_corrupted_document."""

from typing import List

from evalproof.finding import Confidence, DiagnosticCode, Finding, Location, Severity
from evalproof.rule_engine import Rule, ScanContext
from evalproof.rules._evidence import MAX_RELATED_EVIDENCE, cap_evidence_items


RULE_ID = "rag.empty_or_corrupted_document"
EVALUATION_ROLES = {"evaluation_dataset", "benchmark_dataset"}
RAG_ROLES = {"rag_document"}
CONTENT_FIELD_ALIASES = ["text", "content", "document", "body", "chunk", "page_content"]
INCOMPLETE_INDEX_CODES = {
    DiagnosticCode.ARTIFACT_FILE_SIZE_LIMIT_EXCEEDED.value,
    DiagnosticCode.ARTIFACT_ROW_LIMIT_REACHED.value,
}
CORRUPTION_CODES = {
    DiagnosticCode.ARTIFACT_PARSE_FAILED.value,
    DiagnosticCode.ARTIFACT_ROW_PARSE_FAILED.value,
}


class EmptyOrCorruptedDocumentRule(Rule):
    @property
    def id(self) -> str:
        return RULE_ID

    @property
    def title(self) -> str:
        return "Empty or corrupted RAG document detected"

    @property
    def default_severity(self) -> str:
        return Severity.MEDIUM.value

    @property
    def description(self) -> str:
        return "Detects empty RAG artifacts or explicitly empty records in a scan that contains evaluation data."

    @property
    def artifact_roles(self) -> List[str]:
        return ["evaluation_dataset", "benchmark_dataset", "rag_document"]

    @property
    def tags(self) -> List[str]:
        return ["rag_integrity", "dataset_integrity", "evaluation_integrity"]

    def evaluate(self, ctx: ScanContext) -> List[Finding]:
        if not self._has_evaluation_artifact(ctx):
            return []

        findings: List[Finding] = []
        for artifact in sorted(ctx.project_index.artifacts_by_path.values(), key=lambda item: item.path):
            if not RAG_ROLES.intersection(artifact.roles):
                continue
            finding = self._finding_for_artifact(ctx, artifact)
            if finding is not None:
                findings.append(finding)
        return findings

    @staticmethod
    def _has_evaluation_artifact(ctx: ScanContext) -> bool:
        return any(
            EVALUATION_ROLES.intersection(artifact.roles)
            and "configuration" not in artifact.roles
            for artifact in ctx.project_index.artifacts_by_path.values()
        )

    def _finding_for_artifact(self, ctx: ScanContext, artifact):
        diagnostics = list(artifact.diagnostics)
        diagnostics.extend(
            diagnostic
            for diagnostic in ctx.project_index.diagnostics
            if diagnostic.path == artifact.path
        )
        diagnostic_codes = sorted({diagnostic.code for diagnostic in diagnostics})
        if any(code in INCOMPLETE_INDEX_CODES for code in diagnostic_codes):
            return None

        rows = sorted(
            ctx.project_index.rows_by_artifact.get(artifact.path, []),
            key=lambda row: row.row_num,
        )
        raw_text = artifact.read_text()
        state = None
        empty_rows = []
        content_fields = set()

        if not raw_text.strip():
            state = "empty"
        elif any(code in CORRUPTION_CODES for code in diagnostic_codes) and not rows:
            state = "corrupted"
        else:
            for row in rows:
                present = [
                    (field, row.row_data[field])
                    for field in CONTENT_FIELD_ALIASES
                    if isinstance(row.row_data, dict) and field in row.row_data
                ]
                if not present:
                    continue
                content_fields.update(field for field, _ in present)
                if all(value is None or (isinstance(value, str) and not value.strip()) for _, value in present):
                    empty_rows.append(row)
            if empty_rows:
                state = "empty"

        if state is None:
            return None

        row_locations, evidence_truncated = cap_evidence_items(
            [{"path": artifact.path, "row": row.row_num} for row in empty_rows]
        )
        row_hashes, hashes_truncated = cap_evidence_items([row.row_hash for row in empty_rows])
        evidence = {
            "artifact_path": artifact.path,
            "state": state,
            "empty_record_count": len(empty_rows),
            "row_count": len(rows),
            "observed_text_length": len(raw_text.strip()),
            "content_fields": sorted(content_fields),
            "row_locations": row_locations,
            "row_hashes": row_hashes,
            "diagnostic_codes": [code for code in diagnostic_codes if code in CORRUPTION_CODES],
            "evidence_truncated": evidence_truncated or hashes_truncated,
        }
        return Finding(
            rule_id=self.id,
            severity=self.default_severity,
            confidence=Confidence.CONFIRMED.value,
            title=self.title,
            message=f"RAG artifact '{artifact.path}' contains empty or corrupted document content.",
            impact="Empty or unreadable RAG content can make retrieval-grounded evaluation incomplete or untrustworthy.",
            recommendation="Remove the empty or corrupted document, restore its content, and regenerate the evaluation corpus.",
            locations=[
                Location(role="primary", path=artifact.path, row=row.row_num)
                for row in empty_rows[:MAX_RELATED_EVIDENCE]
            ] or [Location(role="primary", path=artifact.path)],
            evidence=evidence,
        )
