"""Detect artifact-local collisions of explicit RAG chunk IDs."""

from collections import defaultdict
from typing import List

from evalproof.finding import Confidence, Finding, Location, Severity
from evalproof.project_index import RagChunkRecord
from evalproof.rule_engine import Rule, ScanContext
from evalproof.rules._evidence import MAX_RELATED_EVIDENCE


class ChunkIdCollisionRule(Rule):
    @property
    def id(self) -> str:
        return "rag.chunk_id_collision"

    @property
    def title(self) -> str:
        return "RAG chunk ID maps to conflicting content"

    @property
    def description(self) -> str:
        return "Detects one explicit chunk_id assigned to different contents within the same RAG artifact."

    @property
    def default_severity(self) -> str:
        return Severity.HIGH.value

    @property
    def artifact_roles(self) -> List[str]:
        return ["rag_document"]

    @property
    def tags(self) -> List[str]:
        return ["rag_integrity", "chunk_identity", "dataset_integrity"]

    def evaluate(self, ctx: ScanContext) -> List[Finding]:
        groups = defaultdict(list)
        for record in ctx.project_index.get_rag_chunk_records():
            groups[(record.artifact_path, record.chunk_id_hash)].append(record)

        findings = []
        for (path, chunk_id_hash), records in sorted(groups.items()):
            records.sort(key=lambda record: (record.row_num, record.content_field, record.row_hash))
            representatives = {}
            for record in records:
                representatives.setdefault(record.content_hash, record)
            if len(representatives) < 2:
                continue

            # Reserve evidence for distinct contents before filling with repeated rows.
            samples = list(representatives.values())[:MAX_RELATED_EVIDENCE]
            sampled_rows = {record.row_num for record in samples}
            for record in records:
                if len(samples) == MAX_RELATED_EVIDENCE:
                    break
                if record.row_num not in sampled_rows:
                    samples.append(record)
                    sampled_rows.add(record.row_num)
            samples.sort(key=lambda record: (record.row_num, record.content_field))
            evidence_records = [self._sample(record) for record in samples]

            findings.append(Finding(
                rule_id=self.id,
                severity=self.default_severity,
                confidence=Confidence.CONFIRMED.value,
                title=self.title,
                message=(
                    f"One explicit chunk_id in '{path}' maps to "
                    f"{len(representatives)} distinct normalized contents across {len(records)} records."
                ),
                impact=(
                    "Content lookup by this chunk ID is ambiguous within the artifact; "
                    "retrieval or evaluation references may resolve to unintended content."
                ),
                recommendation=(
                    "Assign distinct chunk IDs to different contents within this artifact, "
                    "or remove outdated records and regenerate dependent references."
                ),
                locations=[
                    Location(
                        role="primary" if index == 0 else "related",
                        path=path,
                        row=record.row_num,
                        field=record.content_field,
                    )
                    for index, record in enumerate(samples)
                ],
                evidence={
                    "artifact_path": path,
                    "chunk_id_field": "chunk_id",
                    "chunk_id_hash": chunk_id_hash,
                    "record_count": len(records),
                    "distinct_content_count": len(representatives),
                    "sample_records": evidence_records,
                    "evidence_truncated": len(samples) < len(records),
                },
            ))
        return findings

    @staticmethod
    def _sample(record: RagChunkRecord) -> dict:
        return {
            "row": record.row_num,
            "field": record.content_field,
            "row_hash": record.row_hash,
            "content_hash": record.content_hash,
        }
