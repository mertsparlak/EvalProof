"""Rule: rag.duplicate_chunk_in_corpus."""

from collections import defaultdict
import hashlib
from typing import Dict, List, Tuple

from evalproof.finding import Confidence, DiagnosticCode, Finding, Location, Severity
from evalproof.project_index import extract_rag_content
from evalproof.rule_engine import Rule, ScanContext
from evalproof.rules._evidence import MAX_RELATED_EVIDENCE, cap_evidence_items


RULE_ID = "rag.duplicate_chunk_in_corpus"
EVALUATION_ROLES = {"evaluation_dataset", "benchmark_dataset"}
RAG_ROLES = {"rag_document"}
INCOMPLETE_INDEX_CODES = {
    DiagnosticCode.ARTIFACT_PARSE_FAILED.value,
    DiagnosticCode.ARTIFACT_ROW_PARSE_FAILED.value,
    DiagnosticCode.ARTIFACT_ROW_LIMIT_REACHED.value,
    DiagnosticCode.ARTIFACT_FILE_SIZE_LIMIT_EXCEEDED.value,
}


class DuplicateChunkInCorpusRule(Rule):
    @property
    def id(self) -> str:
        return RULE_ID

    @property
    def title(self) -> str:
        return "Duplicate RAG chunk detected"

    @property
    def default_severity(self) -> str:
        return Severity.MEDIUM.value

    @property
    def description(self) -> str:
        return "Detects normalized exact duplicate chunks or document records in a RAG corpus."

    @property
    def artifact_roles(self) -> List[str]:
        return ["evaluation_dataset", "benchmark_dataset", "rag_document"]

    @property
    def tags(self) -> List[str]:
        return ["rag_integrity", "retrieval_integrity", "dataset_integrity"]

    def evaluate(self, ctx: ScanContext) -> List[Finding]:
        if not self._has_evaluation_artifact(ctx):
            return []

        groups: Dict[str, List[Tuple[str, int, str, str]]] = defaultdict(list)
        for artifact in sorted(ctx.project_index.artifacts_by_path.values(), key=lambda item: item.path):
            if not RAG_ROLES.intersection(artifact.roles):
                continue
            if self._has_incomplete_index(ctx, artifact.path, artifact.diagnostics):
                continue
            rows = sorted(
                ctx.project_index.rows_by_artifact.get(artifact.path, []),
                key=lambda row: row.row_num,
            )
            for row in rows:
                extracted = self._extract_content(row.row_data)
                if extracted is None:
                    continue
                field_name, normalized_content = extracted
                groups[normalized_content].append(
                    (artifact.path, row.row_num, field_name, row.row_hash)
                )

        findings: List[Finding] = []
        ordered_groups = sorted(
            groups.items(),
            key=lambda item: (
                hashlib.sha256(item[0].encode("utf-8")).hexdigest(),
                item[0],
            ),
        )
        for normalized_content, rows in ordered_groups:
            rows = sorted(rows, key=lambda item: (item[0], item[1], item[2], item[3]))
            if len(rows) < 2:
                continue
            findings.append(self._build_finding(normalized_content, rows))
        return findings

    def _build_finding(self, normalized_content: str, rows):
        content_hash = f"sha256:{hashlib.sha256(normalized_content.encode('utf-8')).hexdigest()}"
        row_locations, locations_truncated = cap_evidence_items(
            [{"path": path, "row": row_num, "field": field_name} for path, row_num, field_name, _ in rows]
        )
        row_hashes, hashes_truncated = cap_evidence_items([row_hash for _, _, _, row_hash in rows])
        evidence = {
            "artifact_paths": sorted({path for path, _, _, _ in rows}),
            "content_fields": sorted({field_name for _, _, field_name, _ in rows}),
            "normalized_chunk_hash": content_hash,
            "duplicate_count": len(rows),
            "duplicate_artifact_count": len({path for path, _, _, _ in rows}),
            "row_locations": row_locations,
            "row_hashes": row_hashes,
            "evidence_truncated": locations_truncated or hashes_truncated,
        }
        return Finding(
            rule_id=self.id,
            severity=self.default_severity,
            confidence=Confidence.CONFIRMED.value,
            title=self.title,
            message=f"RAG corpus contains {len(rows)} exact duplicate document or chunk records.",
            impact="Duplicate retrieval content can overweight the same evidence and distort retrieval-grounded evaluation.",
            recommendation="Deduplicate the RAG corpus records and regenerate the index before evaluating retrieval behavior.",
            locations=[
                Location(
                    role="primary" if index == 0 else "related",
                    path=path,
                    row=row_num,
                    field=field_name,
                )
                for index, (path, row_num, field_name, _) in enumerate(rows[:MAX_RELATED_EVIDENCE])
            ],
            evidence=evidence,
        )

    @staticmethod
    def _has_evaluation_artifact(ctx: ScanContext) -> bool:
        return any(
            EVALUATION_ROLES.intersection(artifact.roles)
            and "configuration" not in artifact.roles
            for artifact in ctx.project_index.artifacts_by_path.values()
        )

    @staticmethod
    def _has_incomplete_index(ctx: ScanContext, artifact_path: str, artifact_diagnostics) -> bool:
        diagnostics = list(artifact_diagnostics)
        diagnostics.extend(
            diagnostic
            for diagnostic in ctx.project_index.diagnostics
            if diagnostic.path == artifact_path
        )
        return any(diagnostic.code in INCOMPLETE_INDEX_CODES for diagnostic in diagnostics)

    @staticmethod
    def _extract_content(row_data):
        return extract_rag_content(row_data)
