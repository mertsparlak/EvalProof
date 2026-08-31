"""Rule: contamination.rag_answer_leakage"""

import hashlib
from typing import List, Set, Tuple

from evalproof.finding import Finding, Location, Severity, Confidence
from evalproof.project_index import normalize_plain_text, extract_rag_content
from evalproof.rule_engine import Rule, ScanContext


class RagAnswerLeakageRule(Rule):
    @property
    def id(self) -> str:
        return "contamination.rag_answer_leakage"

    @property
    def title(self) -> str:
        return "RAG answer leakage detected"

    @property
    def default_severity(self) -> str:
        return Severity.HIGH.value

    @property
    def description(self) -> str:
        return "Detects evaluation answers or gold labels that appear in RAG corpus artifacts using exact or normalized text containment."

    @property
    def artifact_roles(self) -> List[str]:
        return ["evaluation_dataset", "benchmark_dataset", "rag_document"]

    @property
    def tags(self) -> List[str]:
        return ["contamination", "rag_leakage"]

    def evaluate(self, ctx: ScanContext) -> List[Finding]:
        findings: List[Finding] = []
        rag_arts = ctx.project_index.artifacts_by_role.get("rag_document", [])

        if not rag_arts or not ctx.project_index.answer_records:
            return findings

        # Cache normalized text for RAG artifacts
        rag_texts = []  # (path, normalized_text, related location)
        for rag_art in sorted(rag_arts, key=lambda a: a.path):
            if rag_art.format == "parquet":
                for row in ctx.project_index.rows_by_artifact.get(rag_art.path, []):
                    content = extract_rag_content(row.row_data)
                    if content:
                        field, text = content
                        rag_texts.append((rag_art.path, text, Location(role="related", path=rag_art.path, row=row.row_num, field=field)))
                continue
            raw_text = rag_art.read_text()
            norm_text = normalize_plain_text(raw_text)
            if norm_text:
                rag_texts.append((rag_art.path, norm_text, Location(role="related", path=rag_art.path)))

        # Track reported (answer_record_index, rag_path) pairs to emit at most 1 finding per pair
        reported: Set[Tuple[str, int, str]] = set()

        for ans_rec in ctx.project_index.answer_records:
            norm_ans = ans_rec.normalized_answer
            if not norm_ans:
                continue

            for rag_path, norm_rag, loc_related in rag_texts:
                if (ans_rec.artifact_path, ans_rec.row_num, rag_path) in reported:
                    continue

                if norm_ans in norm_rag:
                    reported.add((ans_rec.artifact_path, ans_rec.row_num, rag_path))

                    loc_primary = Location(role="primary", path=ans_rec.artifact_path, row=ans_rec.row_num, field=ans_rec.field_name)

                    finding = Finding(
                        rule_id=self.id,
                        severity=self.default_severity,
                        confidence=Confidence.LIKELY.value,
                        title=self.title,
                        message=f"Evaluation answer in '{ans_rec.artifact_path}' (row {ans_rec.row_num}, field '{ans_rec.field_name}') found in RAG document '{rag_path}'.",
                        impact="The system may answer by copying leaked gold answers from retrieval context.",
                        recommendation="Remove leaked answers from the RAG corpus, change the evaluation case, or mark the case as retrieval-grounded rather than independent.",
                        locations=[loc_primary, loc_related],
                        evidence={
                            "evaluation_artifact": ans_rec.artifact_path,
                            "evaluation_row": ans_rec.row_num,
                            "answer_field": ans_rec.field_name,
                            "rag_artifact": rag_path,
                            "matched_normalized_text": "sha256:" + hashlib.sha256(norm_ans.encode("utf-8")).hexdigest(),
                        },
                    )
                    findings.append(finding)

        return findings
